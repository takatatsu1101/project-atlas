
from datetime import date
from typing import Dict, List, Optional

from src.config.settings import load_settings
from src.data_collector.collector import collect_ohlcv_data, collect_financial_data

def run_data_collection_test(
    symbols: List[str],
    start_date: date,
    end_date: date,
    fiscal_year: int
) -> None:
    """
    ステップ1・2: データ取得（OHLCV・財務データ）の動作確認用メイン関数。
    """
    print(f"=== データ収集テスト開始 ({len(symbols)}銘柄) ===")
    
    for symbol in symbols:
        print(f"\n--- [{symbol}] データ収集中 ---")
        try:
            # 1. OHLCVデータ収集 (Parquet & Yahoo Finance)
            ohlcv_data = collect_ohlcv_data(symbol, start_date, end_date)
            print(f"OHLCVデータ取得件数: {len(ohlcv_data)} 件")
            if ohlcv_data:
                print(f"  先頭日付: {ohlcv_data[0].date}, 終値: {ohlcv_data[0].close}")
                print(f"  末尾日付: {ohlcv_data[-1].date}, 終値: {ohlcv_data[-1].close}")

            # 2. 財務データ収集 (IR Bank JSONキャッシュ)
            financial_data = collect_financial_data(symbol, fiscal_year)
            if financial_data:
                print(f"財務データ取得成功: 決算日={financial_data.fiscal_date}, EPS={financial_data.eps}, BPS={financial_data.bps}, ROE={financial_data.roe}%")
            else:
                print(f"警告: {symbol} の {fiscal_year}年度財務データが取得できませんでした。")
                
        except Exception as e:
            print(f"エラー [{symbol}]: {e}")

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
    fiscal_year = 2025  # 2025年度のローカルキャッシュを使用

    run_data_collection_test(target_symbols, start_date_obj, end_date_obj, fiscal_year)

    if all_results:
        # ランキング生成 & 表示
        print(f"\n=== 総合ランキング生成 ({len(all_results)}銘柄) ===")
        analysis_results = generate_ranking(all_results)
        display_results(analysis_results, output_type="cli")
    else:
        print("有効な分析結果がありませんでした。")
