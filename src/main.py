import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Union

from src.common.logger import get_logger
from src.config.screening_config import AtlasScreeningConfig, load_screening_config
from src.data_collector.collector import (
    collect_financial_data,
    collect_ohlcv_data,
    data_collector,
    prefetch_ohlcv_batch,
)
from src.data_collector.master import MasterManager
from src.evaluator.evaluator import ForwardReturnEvaluator
import src.feature_engine  # 特徴量クラスをインポートしてレジストリに登録させる
from src.feature_engine.manager import calculate_features
from src.indicator_calculator.calculator import IndicatorCalculator
from src.model.data_models import (
    AnalysisResultModel,
    EvaluationSummaryModel,
    FeatureSetModel,
    FinancialModel,
    OhlcvModel,
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


def _normalize_bar_date(value: date) -> date:
    """OhlcvModel.date が datetime の場合でも date 型へ正規化する。"""
    return value.date() if isinstance(value, datetime) else value


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
    mode: str = "screen",
    horizons: Optional[List[int]] = None,
    use_cache: bool = True,
    use_feature_cache: bool = False,
    update_master: bool = False,
    allow_irbank_download: bool = True,
) -> Dict[str, Any]:
    """
    Project Atlas 全パイプラインを実行する。
    1. 引数検証・YAML設定ロード
    2. マスタ・財務スナップショットに基づく事前スクリーニング（symbols 未指定時または use_pre_screening=True 時）
    3. OHLCV・財務データ収集、流動性チェック、テクニカル指標・特徴量・パターン検出
    4. 戦略スコア計算（S002_StrategyScore）
    5. スクリーニング・総合＆戦略別ランキング生成
    6. evaluate モード時はフォワードリターン検証を実行
    7. CLI表示および JSON / Markdown レポート出力

    Note:
        戻り値 ``timings_sec`` の ``total`` およびレポートメタ情報 ``elapsed_sec`` は、
        パイプライン開始からステップ6（フォワード評価）完了時点＝レポート出力・CLI表示前までの
        所要時間（秒）を計測する。
    """
    if mode not in ("screen", "evaluate"):
        raise ValueError(
            f"不正な実行モードが指定されました: {mode} ('screen' または 'evaluate' を指定してください)"
        )
    if mode == "evaluate" and as_of_date is None:
        raise ValueError("evaluate モードでは as_of_date の指定が必須です。")

    as_of_date = _normalize_bar_date(as_of_date) if as_of_date is not None else None
    start_date = _normalize_bar_date(start_date) if start_date is not None else None
    end_date = _normalize_bar_date(end_date) if end_date is not None else None

    pipeline_start = time.perf_counter()
    timings_sec: Dict[str, float] = {
        "setup_and_prescreen": 0.0,
        "ohlcv_collection": 0.0,
        "liquidity_filter": 0.0,
        "financial_collection": 0.0,
        "indicator_calculation": 0.0,
        "feature_calculation": 0.0,
        "pattern_detection": 0.0,
        "score_calculation": 0.0,
        "screening_and_ranking": 0.0,
        "forward_evaluation": 0.0,
        "total": 0.0,
    }

    t_setup = time.perf_counter()
    config: AtlasScreeningConfig = load_screening_config(config_path=config_path)
    resolved_horizons = horizons if horizons is not None else list(config.evaluation.horizons)
    if mode == "evaluate":
        resolved_horizons = ForwardReturnEvaluator._normalize_horizons(resolved_horizons)

    cache_key_suffix = f"asof_{as_of_date.isoformat()}" if as_of_date is not None else None

    analysis_end = (
        min(end_date, as_of_date)
        if (end_date is not None and as_of_date is not None)
        else (as_of_date or end_date or date.today())
    )
    effective_start = start_date or (analysis_end - timedelta(days=365))
    effective_fiscal_year = (
        fiscal_year
        if fiscal_year is not None
        else (as_of_date or analysis_end).year
    )

    # evaluate モード時は end_date の指定状況に応じてフォワード検証用 OHLCV の一括取得可否を決定する
    fetch_end = analysis_end
    fetch_as_of = as_of_date
    eval_end_arg: Optional[date] = None
    use_bulk_eval_ohlcv = False
    if mode == "evaluate":
        assert as_of_date is not None
        if end_date is None:
            eval_fetch_end = ForwardReturnEvaluator.compute_default_fetch_end(
                as_of_date, resolved_horizons
            )
            eval_end_arg = None
        elif end_date > as_of_date:
            eval_fetch_end = end_date
            eval_end_arg = end_date
        else:
            eval_fetch_end = analysis_end
            eval_end_arg = None

        if eval_fetch_end > analysis_end:
            fetch_end = eval_fetch_end
            fetch_as_of = eval_fetch_end
            use_bulk_eval_ohlcv = True

    master_manager = MasterManager()
    if update_master:
        master_stocks = master_manager.update_from_jpx()
    else:
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
    timings_sec["setup_and_prescreen"] = time.perf_counter() - t_setup

    print(f"=== Project Atlas 全パイプライン実行 ({len(target_symbols)}銘柄) ===")

    calculator = IndicatorCalculator()
    all_feature_sets: List[FeatureSetModel] = []
    all_pattern_sets: List[PatternSetModel] = []
    all_score_results: List[ScoreResultModel] = []
    financial_map: Dict[str, FinancialModel] = {}
    eval_ohlcv_map: Dict[str, List[OhlcvModel]] = {}
    processed_symbols: List[str] = []

    # 対象銘柄の OHLCV を事前にチャンク並列で一括プリフェッチ
    if target_symbols:
        t_prefetch = time.perf_counter()
        if fetch_as_of is not None:
            prefetch_ohlcv_batch(
                target_symbols,
                effective_start,
                fetch_end,
                as_of_date=fetch_as_of,
            )
        else:
            prefetch_ohlcv_batch(target_symbols, effective_start, fetch_end)
        timings_sec["ohlcv_collection"] += time.perf_counter() - t_prefetch

    latest_only_eval = bool(config.screener.latest_only_per_symbol)
    for symbol in target_symbols:
        print(f"\n--- [{symbol}] 処理開始 ---")
        try:
            # 1. OHLCVデータ収集（evaluate 一括取得時も分析側には as_of_date 以前のバーのみ渡す）
            t_ohlcv = time.perf_counter()
            if fetch_as_of is not None:
                raw_ohlcv = collect_ohlcv_data(
                    symbol, effective_start, fetch_end, as_of_date=fetch_as_of
                )
            else:
                raw_ohlcv = collect_ohlcv_data(symbol, effective_start, fetch_end)

            if as_of_date is not None:
                analysis_ohlcv = [
                    b for b in raw_ohlcv if _normalize_bar_date(b.date) <= as_of_date
                ]
            else:
                analysis_ohlcv = list(raw_ohlcv)
            analysis_ohlcv.sort(key=lambda b: _normalize_bar_date(b.date))
            timings_sec["ohlcv_collection"] += time.perf_counter() - t_ohlcv

            print(f"  OHLCVデータ取得件数: {len(analysis_ohlcv)} 件")
            if not analysis_ohlcv:
                print(f"  警告: {symbol} のOHLCVデータが存在しないためスキップします。")
                continue

            # 流動性フィルタ（有効時）
            if should_check_liquidity:
                t_liq = time.perf_counter()
                passed_liquidity = pre_screener.check_liquidity(
                    analysis_ohlcv,
                    as_of_date=as_of_date,
                    criteria=config.pre_screening,
                )
                timings_sec["liquidity_filter"] += time.perf_counter() - t_liq
                if not passed_liquidity:
                    print(f"  スキップ: {symbol} は流動性基準を満たしませんでした。")
                    continue

            # 一括取得を実行した銘柄は、未来バーが0件でも取得完了済みとして評価用共有マップへ格納する
            if use_bulk_eval_ohlcv:
                eval_ohlcv_map[symbol] = raw_ohlcv

            # 2. 財務データ収集（既取得終値を渡して内部の重複 OHLCV 取得を抑止）
            t_fin = time.perf_counter()
            latest_close = analysis_ohlcv[-1].close
            if as_of_date is not None:
                financial_data = collect_financial_data(
                    symbol,
                    fiscal_year=effective_fiscal_year,
                    as_of_date=as_of_date,
                    allow_download=allow_irbank_download,
                    latest_close=latest_close,
                )
            else:
                financial_data = collect_financial_data(
                    symbol,
                    effective_fiscal_year,
                    allow_download=allow_irbank_download,
                    latest_close=latest_close,
                )
            timings_sec["financial_collection"] += time.perf_counter() - t_fin

            if financial_data:
                financial_map[symbol] = financial_data
                print(
                    f"  財務データ取得成功: 決算日={financial_data.fiscal_date}, ROE={financial_data.roe}%"
                )
            else:
                print(f"  警告: {symbol} の財務データが取得できませんでした。")

            # 3. テクニカル指標計算
            t_ind = time.perf_counter()
            indicator_sets = calculator.calculate_indicators(
                analysis_ohlcv,
                use_cache=use_cache,
                cache_key_suffix=cache_key_suffix,
            )
            timings_sec["indicator_calculation"] += time.perf_counter() - t_ind
            print(f"  テクニカル指標計算成功: {len(indicator_sets)} 件")

            # 4. 全特徴量計算（特徴量キャッシュは use_feature_cache 指定時のみ有効）
            t_feat = time.perf_counter()
            feature_sets = calculate_features(
                analysis_ohlcv,
                indicator_sets,
                financial_data,
                feature_ids=None,
                use_cache=use_cache and use_feature_cache,
                cache_key_suffix=cache_key_suffix,
                latest_only=latest_only_eval,
            )
            timings_sec["feature_calculation"] += time.perf_counter() - t_feat
            print(f"  特徴量計算成功: {len(feature_sets)} 件の日付データ")

            # 5. パターン検出
            t_pat = time.perf_counter()
            pattern_sets = detect_patterns(
                analysis_ohlcv,
                indicator_sets,
                pattern_ids=None,
                latest_only=latest_only_eval,
            )
            timings_sec["pattern_detection"] += time.perf_counter() - t_pat
            print(f"  パターン検出成功: {len(pattern_sets)} 件の日付データ")

            # 6. 戦略スコア計算（設定注入）
            t_score = time.perf_counter()
            score_results = calculate_scores(
                feature_sets,
                pattern_sets,
                score_ids=["S002_StrategyScore"],
                ohlcv_data=analysis_ohlcv,
                indicator_sets=indicator_sets,
                score_configs={"S002_StrategyScore": config.strategy_score},
            )
            timings_sec["score_calculation"] += time.perf_counter() - t_score
            print(f"  スコア計算成功: {len(score_results)} 件")

            all_feature_sets.extend(feature_sets)
            all_pattern_sets.extend(pattern_sets)
            all_score_results.extend(score_results)
            processed_symbols.append(symbol)

        except Exception as e:
            logger.error(f"パイプライン処理中にエラーが発生しました [{symbol}]: {e}")
            print(f"  エラー [{symbol}]: {e}")

    # 7. スクリーニング適用 & 8. 総合・戦略別ランキング生成
    t_screen_rank = time.perf_counter()
    screener_instance = Screener()
    filtered_scores = screener_instance.apply_screener(
        all_score_results, criteria=config.screener
    )

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
    timings_sec["screening_and_ranking"] = time.perf_counter() - t_screen_rank

    print(
        f"\n=== 全パイプライン処理完了: 抽出結果 {len(overall_ranking)} 件 "
        f"(対象 {len(processed_symbols)} 銘柄) ==="
    )

    evaluation_summary: Optional[EvaluationSummaryModel] = None
    if mode == "evaluate":
        assert as_of_date is not None
        t_eval = time.perf_counter()
        evaluator = ForwardReturnEvaluator()
        evaluation_summary = evaluator.evaluate(
            overall_ranking,
            as_of_date=as_of_date,
            ohlcv_map=eval_ohlcv_map if use_bulk_eval_ohlcv else None,
            horizons=resolved_horizons,
            entry_price_mode=config.evaluation.entry_price_mode,
            eval_end_date=eval_end_arg,
        )
        timings_sec["forward_evaluation"] = time.perf_counter() - t_eval

    # レポート出力・CLI表示前（ステップ1〜6完了時点）までを合計所要時間として計測する
    timings_sec["total"] = time.perf_counter() - pipeline_start
    rounded_timings: Dict[str, float] = {k: round(v, 4) for k, v in timings_sec.items()}

    run_metadata: Dict[str, Any] = {
        "mode": mode,
        "target_symbols_count": len(target_symbols),
        "processed_symbols_count": len(processed_symbols),
        "total_score_results": len(all_score_results),
        "filtered_count": len(filtered_scores),
        "fiscal_year": effective_fiscal_year,
        "elapsed_sec": rounded_timings["total"],
    }

    # 9. プレゼンテーション出力（CLI表示 ＋ レポート出力）
    presenter_instance = Presenter()
    presenter_instance.display_results(
        overall_ranking,
        output_type="cli",
        evaluation_summary=evaluation_summary,
    )

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
            evaluation_summary=evaluation_summary,
        )

    timing_summary = ", ".join(f"{k}={v:.3f}s" for k, v in rounded_timings.items())
    logger.info(f"パイプラインフェーズ別所要時間: {timing_summary}")
    print(f"フェーズ別所要時間: {timing_summary}")

    return {
        "as_of_date": as_of_date,
        "processed_symbols": processed_symbols,
        "score_results": all_score_results,
        "filtered_scores": filtered_scores,
        "analysis_results": overall_ranking,
        "strategy_rankings": strategy_rankings,
        "evaluation_summary": evaluation_summary,
        "report_paths": report_paths,
        "config": config,
        "timings_sec": rounded_timings,
    }


def _parse_date(value: str) -> date:
    """YYYY-MM-DD 形式の文字列を date 型へ変換する。"""
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"日付は YYYY-MM-DD 形式で指定してください: {value}"
        ) from e


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """コマンドライン引数をパースする。"""
    parser = argparse.ArgumentParser(
        description="Project Atlas 株式スクリーニング＆フォワードリターン検証パイプライン"
    )
    parser.add_argument(
        "--mode",
        choices=["screen", "evaluate"],
        default="screen",
        help="実行モード（screen: スクリーニング / evaluate: フォワードリターン検証）",
    )
    parser.add_argument(
        "--as-of-date",
        type=_parse_date,
        default=None,
        help="分析基準日 (YYYY-MM-DD)。evaluate モードでは必須",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="対象銘柄コード（例: 7203.T 6758.T）。未指定時はマスタから自動抽出",
    )
    parser.add_argument(
        "--start-date",
        type=_parse_date,
        default=None,
        help="OHLCV取得開始日 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=_parse_date,
        default=None,
        help="OHLCV取得終了日 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--fiscal-year",
        type=int,
        default=None,
        help="対象会計年度（例: 2025）",
    )
    parser.add_argument(
        "--horizons",
        nargs="+",
        type=int,
        default=None,
        help="evaluate モード時の検証ホライズン（営業日数、例: 5 20 60）",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="スクリーニング設定YAMLファイルのパス",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="レポート出力先ディレクトリ",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="JSON / Markdown レポートのファイル出力を無効化する",
    )
    parser.add_argument(
        "--use-pre-screening",
        action="store_true",
        help="--symbols 指定時にも事前スクリーニングフィルタを適用する",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="指標・特徴量のファイルキャッシュを読み書きしない",
    )
    parser.add_argument(
        "--use-feature-cache",
        action="store_true",
        help="特徴量のファイルキャッシュを読み書きする（デフォルト無効）",
    )
    parser.add_argument(
        "--update-master",
        action="store_true",
        help="JPXから最新の東証上場銘柄マスタを取得して更新する",
    )
    parser.add_argument(
        "--no-irbank-download",
        action="store_true",
        help="IR BANKからの新規財務データダウンロードを抑止する",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI エントリポイント"""
    args = parse_args(argv)
    try:
        run_full_pipeline(
            symbols=args.symbols,
            start_date=args.start_date,
            end_date=args.end_date,
            fiscal_year=args.fiscal_year,
            as_of_date=args.as_of_date,
            config_path=args.config,
            output_dir=args.output_dir,
            export_reports=not args.no_export,
            use_pre_screening=args.use_pre_screening,
            mode=args.mode,
            horizons=args.horizons,
            use_cache=not args.no_cache,
            use_feature_cache=args.use_feature_cache,
            update_master=args.update_master,
            allow_irbank_download=not args.no_irbank_download,
        )
        return 0
    except Exception as e:
        logger.error(f"パイプライン実行に失敗しました: {e}")
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
