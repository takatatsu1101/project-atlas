
from datetime import date
from typing import List, Dict, Optional
import pandas as pd
import yfinance as yf
import os

from src.model.data_models import OhlcvModel, FinancialModel
from src.config.settings import load_settings

# 設定をロード
settings = load_settings()

class DataCollector:
    def __init__(self):
        self.cache_dir = settings.DATA_CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_ohlcv_from_yfinance(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Yahoo FinanceからOHLCVデータを取得する。
        """
        print(f"Yahoo Financeから {symbol} のOHLCVデータを取得中... ({start_date} - {end_date})")
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
            if df.empty:
                print(f"警告: {symbol} のOHLCVデータが見つかりませんでした。")
                return pd.DataFrame()
            df = df.reset_index()
            df.columns = [col.lower().replace(' ', '_') for col in df.columns]
            # 日本株の場合、'Date'がタイムゾーン情報を持つことがあるため、日付のみにする
            # 'Date'列がすでにdatetime型であるかを確認し、そうでない場合は変換を試みる
            if 'date' in df.columns:
                if not pd.api.types.is_datetime64_any_dtype(df["date"]):
                    df["date"] = pd.to_datetime(df["date"])
                df["date"] = df["date"].dt.tz_localize(None) if df["date"].dt.tz is not None else df["date"]
                df["date"] = df["date"].dt.date # 時刻情報を削除
            return df
        except Exception as e:
            print(f"エラー: {symbol} のOHLCVデータ取得中にエラーが発生しました: {e}")
            print(f"デバッグ情報: DataFrameの状態 - {df.head() if not df.empty else 'Empty'}")
            return pd.DataFrame()

    def collect_ohlcv_data(self, symbol: str, start_date: date, end_date: date) -> List[OhlcvModel]:
        """
        指定期間のOHLCVデータを収集し、保存後、データを返す。
        """
        df = self._get_ohlcv_from_yfinance(symbol, start_date, end_date)
        if df.empty:
            return []
        
        ohlcv_data = []
        for _, row in df.iterrows():
            ohlcv_data.append(OhlcvModel(
                symbol=symbol,
                date=row['date'],
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=row['volume']
            ))
        
        # TODO: 取得したデータを永続化するロジックを追加
        print(f"{symbol} のOHLCVデータを {len(ohlcv_data)} 件取得しました。")
        return ohlcv_data

    def collect_financial_data(self, symbol: str, fiscal_year: int) -> Optional[FinancialModel]:
        """
        指定年度の財務データを収集し、保存後、データを返す。
        現状はダミーデータを返す。
        """
        print(f"{symbol} の財務データを取得中... (会計年度: {fiscal_year})")
        # Yahoo Finance APIでは財務データを直接取得するのが難しい場合があるため、
        # ここではダミーデータを返す例を示す。
        # 実際には、別の財務データAPIを利用するか、スクレイピングなどが必要になる。
        
        dummy_financial_data = FinancialModel(
            symbol=symbol,
            fiscal_date=date(fiscal_year, 3, 31), # 例として3月期決算
            eps=150.0 + (fiscal_year - 2020) * 10, # ダミーデータ
            bps=2500.0 + (fiscal_year - 2020) * 100,
            roe=0.1 + (fiscal_year - 2020) * 0.01,
            roa=0.05 + (fiscal_year - 2020) * 0.005,
            per=15.0 - (fiscal_year - 2020) * 0.5,
            pbr=1.5 - (fiscal_year - 2020) * 0.05,
            revenue=1_000_000_000_000 + (fiscal_year - 2020) * 100_000_000_000,
            operating_profit=100_000_000_000 + (fiscal_year - 2020) * 10_000_000_000,
            net_profit=70_000_000_000 + (fiscal_year - 2020) * 7_000_000_000,
        )
        print(f"{symbol} の財務データを取得しました。(ダミーデータ)")
        return dummy_financial_data

# モジュールレベルでインスタンス化
data_collector = DataCollector()

def collect_ohlcv_data(symbol: str, start_date: date, end_date: date) -> List[OhlcvModel]:
    return data_collector.collect_ohlcv_data(symbol, start_date, end_date)

def collect_financial_data(symbol: str, fiscal_year: int) -> Optional[FinancialModel]:
    return data_collector.collect_financial_data(symbol, fiscal_year)

