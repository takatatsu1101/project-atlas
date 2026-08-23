
from datetime import date
from typing import Dict, List, Optional

from src.config.settings import load_settings
from src.data_collector.collector import collect_ohlcv_data, collect_financial_data
from src.indicator_calculator.calculator import calculate_indicators
from src.feature_engine.manager import calculate_features
from src.pattern_detector.manager import detect_patterns
from src.score_engine.manager import calculate_scores
from src.screener.screener import apply_screener
from src.ranking.generator import generate_ranking
from src.presentation.presenter import display_results

from src.model.data_models import AnalysisResultModel, OhlcvModel, FinancialModel, IndicatorSetModel, FeatureSetModel, PatternSetModel, ScoreResultModel

def run_analysis(
    symbol: str,
    start_date: date,
    end_date: date,
    config: Optional[Dict] = None
) -> None:
    """
    指定された銘柄と期間で株式分析を実行するメイン関数。
    """
    print(f"{symbol} の分析を開始します: {start_date} から {end_date}")

    print(f"{symbol} の分析を開始します: {start_date} から {end_date}")

    # configがNoneの場合に空の辞書を渡す
    config = config if config is not None else {}

    # 1. 設定の読み込み
    settings = load_settings(config.get("env", "development"))
    print(f"設定を読み込みました: {settings.APP_ENV}")

    # 2. データ収集
    ohlcv_data = collect_ohlcv_data(symbol, start_date, end_date)
    financial_data = collect_financial_data(symbol, end_date.year) # 仮に最新年度の財務データを取得
    print(f"OHLCVデータ {len(ohlcv_data)} 件と財務データを収集しました。")

    # 3. 指標計算
    indicator_data = calculate_indicators(ohlcv_data)
    print(f"テクニカル指標を計算しました: {len(indicator_data)} 件")

    # 4. 特徴量計算
    feature_sets = calculate_features(ohlcv_data, indicator_data, financial_data)
    print(f"特徴量を計算しました: {len(feature_sets)} 件")

    # 5. パターン検出
    pattern_sets = detect_patterns(ohlcv_data, indicator_data)
    print(f"チャートパターンを検出しました: {len(pattern_sets)} 件")

    # 6. スコアリング
    score_results = calculate_scores(feature_sets, pattern_sets)
    print(f"スコアを計算しました: {len(score_results)} 件")

    # 7. スクリーニング
    filtered_score_results = apply_screener(score_results, config.get("screener_criteria", {}))
    print(f"スクリーニング結果: {len(filtered_score_results)} 件")

    # 8. ランキング
    analysis_results = generate_ranking(filtered_score_results)
    print(f"ランキングを生成しました: {len(analysis_results)} 件")

    # 9. 結果表示
    display_results(analysis_results, output_type=config.get("output_type", "cli"))
    print(f"{symbol} の分析が完了しました。")

if __name__ == "__main__":
    # 例として、特定の銘柄と期間で分析を実行
    target_symbol = "9984.T"  # ソフトバンクグループの銘柄コード（例）
    start_date_obj = date(2025, 1, 1)
    end_date_obj = date(2025, 12, 31)

    run_analysis(target_symbol, start_date_obj, end_date_obj)
