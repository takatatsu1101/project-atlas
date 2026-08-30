
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
    # 対象銘柄リスト（10〜20銘柄程度）
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

    print(f"=== 複数銘柄 ({len(target_symbols)}銘柄) の一括分析・スクリーニングを開始します ===")
    
    all_results = []
    for symbol in target_symbols:
        try:
            print(f"\n--- [{symbol}] 分析開始 ---")
            # 1. データ収集
            ohlcv_data = collect_ohlcv_data(symbol, start_date_obj, end_date_obj)
            if not ohlcv_data:
                print(f"{symbol}: OHLCVデータが取得できませんでした。スキップします。")
                continue
            
            financial_data = collect_financial_data(symbol, end_date_obj.year)
            
            # 2. 指標計算
            indicator_data = calculate_indicators(ohlcv_data)
            
            # 3. 特徴量計算
            feature_sets = calculate_features(ohlcv_data, indicator_data, financial_data)
            
            # 4. パターン検出
            pattern_sets = detect_patterns(ohlcv_data, indicator_data)
            
            # 5. スコアリング
            score_results = calculate_scores(feature_sets, pattern_sets)
            if score_results:
                # 最新日のスコア結果を採用
                latest_score = score_results[-1]
                all_results.append(latest_score)
                print(f"{symbol}: 総合スコア算出完了 ({latest_score.overall_score:.2f})")
        except Exception as e:
            print(f"{symbol} の分析中にエラーが発生しました: {e}")

    if all_results:
        # ランキング生成 & 表示
        print(f"\n=== 総合ランキング生成 ({len(all_results)}銘柄) ===")
        analysis_results = generate_ranking(all_results)
        display_results(analysis_results, output_type="cli")
    else:
        print("有効な分析結果がありませんでした。")
