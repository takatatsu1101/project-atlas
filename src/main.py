
from datetime import date
from typing import Dict, List, Optional

from src.config.settings import load_settings
from src.data_collector.collector import collect_ohlcv_data, collect_financial_data
from src.indicator_calculator.calculator import IndicatorCalculator

def run_pipeline_step3(
    symbols: List[str],
    start_date: date,
    end_date: date,
    fiscal_year: int
) -> None:
    """
    ステップ3: データ取得（OHLCV・財務） ＋ テクニカル指標計算 (Indicator Calculator) の結合・検証。
    """
    print(f"=== ステップ3: テクニカル指標計算の結合検証 ({len(symbols)}銘柄) ===")
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

            # 3. テクニカル指標計算 (Indicator Calculator)
            indicator_sets = calculator.calculate_indicators(ohlcv_data)
            print(f"  テクニカル指標計算成功: {len(indicator_sets)} 件")
            if indicator_sets:
                latest = indicator_sets[-1]
                print(f"    最新日付 ({latest.date}) の指標一覧: {latest.indicators}")

        except Exception as e:
            print(f"  エラー [{symbol}]: {e}")

if __name__ == "__main__":
    target_symbols = [
        "7203.T",  # トヨタ自動車
        # "9984.T",  # ソフトバンクグループ
        # "6758.T",  # ソニーグループ
        # "6861.T",  # キーエンス
        # "9432.T",  # 日本電信電話 (NTT)
        # "8306.T",  # 三菱UFJフィナンシャル・グループ
        # "7974.T",  # 任天堂
        # "6501.T",  # 日立製作所
        # "4063.T",  # 信越化学工業
        # "6098.T",  # リクルートホールディングス
    ]
    
    start_date_obj = date(2025, 1, 1)
    end_date_obj = date(2025, 12, 31)
    fiscal_year = 2025

    run_pipeline_step3(target_symbols, start_date_obj, end_date_obj, fiscal_year)
    print("\n=== ステップ3検証完了 ===")
