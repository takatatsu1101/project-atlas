
from datetime import date
from typing import Dict, List, Optional

from src.config.settings import load_settings
from src.data_collector.collector import collect_ohlcv_data, collect_financial_data
from src.indicator_calculator.calculator import IndicatorCalculator
import src.feature_engine  # 特徴量クラスをインポートしてレジストリに登録させる
from src.feature_engine.manager import calculate_features
import src.pattern_detector
from src.pattern_detector.manager import detect_patterns
import src.score_engine
from src.score_engine.manager import calculate_scores
from src.presentation.presenter import display_results
from src.model.data_models import AnalysisResultModel, ScoreResultModel

def run_full_pipeline(
    symbols: List[str],
    start_date: date,
    end_date: date,
    fiscal_year: int
) -> None:
    """
    ステップ5 & ステップ6: パターン検出・スコアリング・ランキング・プレゼンテーション出力までの全パイプラインの結合検証。
    """
    print(f"=== Project Atlas 全パイプライン実行 ({len(symbols)}銘柄) ===")
    calculator = IndicatorCalculator()
    analysis_results: List[AnalysisResultModel] = []

    for symbol in symbols:
        print(f"\n--- [{symbol}] 処理開始 ---")
        try:
            # 1. OHLCVデータ収集
            ohlcv_data = collect_ohlcv_data(symbol, start_date, end_date)
            print(f"  OHLCVデータ取得件数: {len(ohlcv_data)} 件")
            if not ohlcv_data:
                print(f"  警告: {symbol} のOHLCVデータが存在しないためスキップします。")
                continue

            # 2. 財務データ収集
            financial_data = collect_financial_data(symbol, fiscal_year)
            if financial_data:
                print(f"  財務データ取得成功: 決算日={financial_data.fiscal_date}, ROE={financial_data.roe}%")
            else:
                print(f"  警告: {symbol} の財務データが取得できませんでした。")

            # 3. テクニカル指標計算
            indicator_sets = calculator.calculate_indicators(ohlcv_data)
            print(f"  テクニカル指標計算成功: {len(indicator_sets)} 件")

            # 4. 全特徴量計算
            feature_sets = calculate_features(ohlcv_data, indicator_sets, financial_data, feature_ids=None)
            print(f"  特徴量計算成功: {len(feature_sets)} 件の日付データ")

            # 5. パターン検出
            pattern_sets = detect_patterns(ohlcv_data, indicator_sets, pattern_ids=None)
            print(f"  パターン検出成功: {len(pattern_sets)} 件の日付データ")

            # 6. スコアリング
            score_results = calculate_scores(feature_sets, pattern_sets, score_ids=None)
            print(f"  スコア計算成功: {len(score_results)} 件")

            # 最新または最高スコアを抽出
            total_score = 0.0
            latest_date = None
            if score_results:
                overall_scores = [sr for sr in score_results if sr.score_id == "S001_OverallScore"]
                if overall_scores:
                    latest_score_res = overall_scores[-1]
                    total_score = latest_score_res.total_score
                    latest_date = latest_score_res.date

            latest_features = feature_sets[-1].results if feature_sets else []
            latest_patterns = pattern_sets[-1].results if pattern_sets else []

            analysis_result = AnalysisResultModel(
                symbol=symbol,
                company_name=f"Company {symbol}",
                date=latest_date or end_date,
                total_score=total_score,
                feature_results=latest_features,
                pattern_results=latest_patterns,
                summary=f"Pipeline executed successfully for {symbol}. Total Score: {total_score:.2f}"
            )
            analysis_results.append(analysis_result)

        except Exception as e:
            print(f"  エラー [{symbol}]: {e}")

    # ランキング順位付け (スコア降順)
    analysis_results.sort(key=lambda x: x.total_score, reverse=True)
    for i, res in enumerate(analysis_results, start=1):
        res.rank = i

    print(f"\n=== 全パイプライン処理完了: 有効な分析結果 {len(analysis_results)} 件 ===")
    
    # 7. プレゼンテーション出力
    display_results(analysis_results, output_type="cli")

if __name__ == "__main__":
    target_symbols = [
        "7203.T",  # トヨタ自動車
        "9984.T",  # ソフトバンクグループ
        "6758.T",  # ソニーグループ
        "6861.T",  # キーエンス
        "9432.T",  # 日本電信電話 (NTT)
        "8306.T",  # 三菱UFJフィナンシャル・グループ
        "7974.T",  # 任天堂
        "6501.T",  # 日立製作所
        "4063.T",  # 信越化学工業
        "6098.T",  # リクルートホールディングス
    ]
    
    start_date_obj = date(2025, 1, 1)
    end_date_obj = date(2025, 12, 31)
    fiscal_year = 2025

    run_full_pipeline(target_symbols, start_date_obj, end_date_obj, fiscal_year)
