from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.common.logger import get_logger
from src.config.screening_config import AtlasScreeningConfig, load_screening_config
from src.data_collector.collector import (
    collect_financial_data,
    collect_ohlcv_data,
    data_collector,
)
from src.data_collector.master import MasterManager
import src.feature_engine  # 特徴量クラスをインポートしてレジストリに登録させる
from src.feature_engine.manager import calculate_features
from src.indicator_calculator.calculator import IndicatorCalculator
from src.model.data_models import (
    AnalysisResultModel,
    FeatureSetModel,
    FinancialModel,
    PatternSetModel,
    ScoreResultModel,
    StockMasterModel,
)
import src.pattern_detector  # パターンクラスをインポートしてレジストリに登録させる
from src.pattern_detector.manager import detect_patterns
from src.presentation.presenter import Presenter
from src.ranking.generator import RankingGenerator
import src.score_engine  # スコアクラスをインポートしてレジストリに登録させる
from src.score_engine.manager import calculate_scores
from src.screener.pre_screener import PreScreener
from src.screener.screener import Screener

logger = get_logger(__name__)


def run_full_pipeline(
    symbols: Optional[List[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    fiscal_year: Optional[int] = None,
    as_of_date: Optional[date] = None,
    config_path: Optional[Union[str, Path]] = None,
    output_dir: Optional[Union[str, Path]] = None,
    export_reports: bool = True,
    apply_liquidity_filter: Optional[bool] = None,
    use_pre_screening: bool = False,
) -> Dict[str, Any]:
    """
    Project Atlas 全パイプラインを実行する。
    1. YAML設定ロード
    2. マスタ・財務スナップショットに基づく事前スクリーニング（symbols 未指定時または use_pre_screening=True 時）
    3. OHLCV・財務データ収集、流動性チェック、テクニカル指標・特徴量・パターン検出
    4. 戦略スコア計算（S002_StrategyScore）
    5. スクリーニング・総合＆戦略別ランキング生成
    6. CLI表示および JSON / Markdown レポート出力
    """
    config: AtlasScreeningConfig = load_screening_config(config_path=config_path)

    effective_end = end_date or as_of_date or date.today()
    effective_start = start_date or (effective_end - timedelta(days=365))
    effective_fiscal_year = (
        fiscal_year
        if fiscal_year is not None
        else (as_of_date or effective_end).year
    )

    master_manager = MasterManager()
    master_stocks = master_manager.load_master()
    master_map: Dict[str, StockMasterModel] = {s.symbol: s for s in master_stocks}

    pre_screener = PreScreener()
    if symbols is None:
        financial_snapshot = data_collector.load_financial_snapshot(
            fiscal_year=effective_fiscal_year,
            as_of_date=as_of_date,
        )
        filtered_stocks = pre_screener.filter_universe(
            master_stocks,
            financial_snapshot,
            criteria=config.pre_screening,
        )
        target_symbols = [s.symbol for s in filtered_stocks]
        should_check_liquidity = (
            True if apply_liquidity_filter is None else apply_liquidity_filter
        )
    else:
        if use_pre_screening and master_stocks:
            symbol_set = set(symbols)
            subset_masters = [
                s for s in master_stocks if s.symbol in symbol_set or s.code in symbol_set
            ]
            financial_snapshot = data_collector.load_financial_snapshot(
                fiscal_year=effective_fiscal_year,
                as_of_date=as_of_date,
            )
            filtered_stocks = pre_screener.filter_universe(
                subset_masters,
                financial_snapshot,
                criteria=config.pre_screening,
            )
            target_symbols = [s.symbol for s in filtered_stocks]
        else:
            target_symbols = list(symbols)
        should_check_liquidity = (
            bool(apply_liquidity_filter)
            if apply_liquidity_filter is not None
            else False
        )

    print(f"=== Project Atlas 全パイプライン実行 ({len(target_symbols)}銘柄) ===")

    calculator = IndicatorCalculator()
    all_feature_sets: List[FeatureSetModel] = []
    all_pattern_sets: List[PatternSetModel] = []
    all_score_results: List[ScoreResultModel] = []
    financial_map: Dict[str, FinancialModel] = {}
    processed_symbols: List[str] = []

    for symbol in target_symbols:
        print(f"\n--- [{symbol}] 処理開始 ---")
        try:
            # 1. OHLCVデータ収集
            if as_of_date is not None:
                ohlcv_data = collect_ohlcv_data(
                    symbol, effective_start, effective_end, as_of_date=as_of_date
                )
            else:
                ohlcv_data = collect_ohlcv_data(symbol, effective_start, effective_end)
            print(f"  OHLCVデータ取得件数: {len(ohlcv_data)} 件")
            if not ohlcv_data:
                print(f"  警告: {symbol} のOHLCVデータが存在しないためスキップします。")
                continue

            # 流動性フィルタ（有効時）
            if should_check_liquidity and not pre_screener.check_liquidity(
                ohlcv_data,
                as_of_date=as_of_date,
                criteria=config.pre_screening,
            ):
                print(f"  スキップ: {symbol} は流動性基準を満たしませんでした。")
                continue

            # 2. 財務データ収集
            if as_of_date is not None:
                financial_data = collect_financial_data(
                    symbol,
                    fiscal_year=effective_fiscal_year,
                    as_of_date=as_of_date,
                )
            else:
                financial_data = collect_financial_data(symbol, effective_fiscal_year)

            if financial_data:
                financial_map[symbol] = financial_data
                print(
                    f"  財務データ取得成功: 決算日={financial_data.fiscal_date}, ROE={financial_data.roe}%"
                )
            else:
                print(f"  警告: {symbol} の財務データが取得できませんでした。")

            # 3. テクニカル指標計算
            indicator_sets = calculator.calculate_indicators(ohlcv_data)
            print(f"  テクニカル指標計算成功: {len(indicator_sets)} 件")

            # 4. 全特徴量計算
            feature_sets = calculate_features(
                ohlcv_data, indicator_sets, financial_data, feature_ids=None
            )
            print(f"  特徴量計算成功: {len(feature_sets)} 件の日付データ")

            # 5. パターン検出
            pattern_sets = detect_patterns(ohlcv_data, indicator_sets, pattern_ids=None)
            print(f"  パターン検出成功: {len(pattern_sets)} 件の日付データ")

            # 6. 戦略スコア計算（設定注入）
            score_results = calculate_scores(
                feature_sets,
                pattern_sets,
                score_ids=["S002_StrategyScore"],
                ohlcv_data=ohlcv_data,
                indicator_sets=indicator_sets,
                score_configs={"S002_StrategyScore": config.strategy_score},
            )
            print(f"  スコア計算成功: {len(score_results)} 件")

            all_feature_sets.extend(feature_sets)
            all_pattern_sets.extend(pattern_sets)
            all_score_results.extend(score_results)
            processed_symbols.append(symbol)

        except Exception as e:
            logger.error(f"パイプライン処理中にエラーが発生しました [{symbol}]: {e}")
            print(f"  エラー [{symbol}]: {e}")

    # 7. スクリーニング適用
    screener_instance = Screener()
    filtered_scores = screener_instance.apply_screener(
        all_score_results, criteria=config.screener
    )

    # 8. 総合・戦略別ランキング生成
    ranking_gen = RankingGenerator()
    strategy_rankings = ranking_gen.generate_strategy_rankings(
        filtered_scores,
        master_map=master_map,
        feature_sets=all_feature_sets,
        pattern_sets=all_pattern_sets,
        financial_map=financial_map,
        overall_top_n=config.ranking.top_n,
        strategy_top_n=config.ranking.strategy_top_n,
    )
    overall_ranking: List[AnalysisResultModel] = strategy_rankings["overall"]

    print(
        f"\n=== 全パイプライン処理完了: 抽出結果 {len(overall_ranking)} 件 "
        f"(対象 {len(processed_symbols)} 銘柄) ==="
    )

    run_metadata: Dict[str, Any] = {
        "target_symbols_count": len(target_symbols),
        "processed_symbols_count": len(processed_symbols),
        "total_score_results": len(all_score_results),
        "filtered_count": len(filtered_scores),
        "fiscal_year": effective_fiscal_year,
    }

    # 9. プレゼンテーション出力（CLI表示 ＋ レポート出力）
    presenter_instance = Presenter()
    presenter_instance.display_results(overall_ranking, output_type="cli")

    report_paths: Dict[str, Path] = {}
    if export_reports:
        resolved_output_dir = (
            output_dir if output_dir is not None else config.output.output_dir
        )
        report_paths = presenter_instance.export_reports(
            overall_ranking,
            output_dir=resolved_output_dir,
            formats=config.output.formats,
            as_of_date=as_of_date,
            strategy_rankings=strategy_rankings,
            metadata=run_metadata,
        )

    return {
        "as_of_date": as_of_date,
        "processed_symbols": processed_symbols,
        "score_results": all_score_results,
        "filtered_scores": filtered_scores,
        "analysis_results": overall_ranking,
        "strategy_rankings": strategy_rankings,
        "report_paths": report_paths,
        "config": config,
    }


if __name__ == "__main__":
    target_symbols = [
        "5803.T",  # フジクラ
        "5801.T",  # 古河電気工業
    ]

    start_date_obj = date(2025, 1, 1)
    end_date_obj = date(2025, 12, 31)
    fiscal_year = 2025

    run_full_pipeline(target_symbols, start_date_obj, end_date_obj, fiscal_year)
