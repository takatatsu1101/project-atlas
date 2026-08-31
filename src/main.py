
from datetime import date
from typing import Dict, List, Optional

from src.config.settings import load_settings
from src.data_collector.collector import collect_ohlcv_data, collect_financial_data
from src.indicator_calculator.calculator import IndicatorCalculator
import src.feature_engine  # 特徴量クラスをインポートしてレジストリに登録させる
from src.feature_engine.manager import calculate_features

def run_pipeline_step4(
    symbols: List[str],
    start_date: date,
    end_date: date,
    fiscal_year: int
) -> None:
    """
    ステップ4: 特徴量計算（Feature Engine）の結合検証（サブタスク4-2: M001単体検証）。
    """
    print(f"=== ステップ4: 特徴量計算（M001）の結合検証 ({len(symbols)}銘柄) ===")
    calculator = IndicatorCalculator()
    
    for symbol in symbols:
        print(f"\n--- [{symbol}] 処理中 ---")
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

            # 4. 特徴量計算 (P001_PullbackScore のテスト)
            print(f"  特徴量 (P001_PullbackScore) 計算開始...")
            feature_sets = calculate_features(ohlcv_data, indicator_sets, financial_data, feature_ids=["P001_PullbackScore"])
            print(f"  特徴量計算成功: {len(feature_sets)} 件")
            if feature_sets:
                latest_f = feature_sets[-1]
                print(f"    最新日付 ({latest_f.date}) の特徴量結果一覧:")
                for res in latest_f.results:
                    print(f"      - [{res.feature_id}] スコア: {res.score}, 生値: {res.raw_value}")

        except Exception as e:
            print(f"  エラー [{symbol}]: {e}")

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

    run_pipeline_step4(target_symbols, start_date_obj, end_date_obj, fiscal_year)
    print("\n=== ステップ4 (M001) 検証完了 ===")
