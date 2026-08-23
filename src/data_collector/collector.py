import os
import json
import random
import time
import re
from datetime import date, datetime
from typing import List, Dict, Optional
import pandas as pd
import yfinance as yf
import requests

from src.model.data_models import OhlcvModel, FinancialModel
from src.config.settings import load_settings
from src.common.logger import get_logger
from src.common.exceptions import DataCollectionError

logger = get_logger("DataCollector")

# 設定をロード
settings = load_settings()

class DataCollector:
    def __init__(self):
        self.cache_dir = settings.DATA_CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # ユーザー提供の既存IR BANKキャッシュディレクトリ
        self.user_irbank_dir = "/Users/takatoritatsuo/program/python/stock_choice/data_fetcher/code_data"
        # 本プロジェクト内のIR BANKキャッシュ保存先
        self.local_irbank_dir = os.path.join(self.cache_dir, "irbank_code_data")
        os.makedirs(self.local_irbank_dir, exist_ok=True)

        # IR BANKのダウンロード用定数
        self.URL_IRBANK_FILES = "https://f.irbank.net/files/"
        self.BALANCE_SHEET_FILE_NAME = "fy-balance-sheet.json"
        self.PROFIT_AND_LOSS_FILE_NAME = "fy-profit-and-loss.json"

    def _parse_symbol(self, symbol: str) -> str:
        """
        '9984.T' や '9984' から数字4桁などのコード部を抽出する
        """
        match = re.match(r"^([A-Z0-9]{4})", symbol)
        if match:
            return match.group(1)
        return symbol

    def _get_ohlcv_from_yfinance(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Yahoo FinanceからOHLCVデータを取得する。
        """
        logger.info(f"Yahoo Financeから {symbol} のOHLCVデータを取得中... ({start_date} - {end_date})")
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
            if df.empty:
                logger.warning(f"{symbol} のOHLCVデータが見つかりませんでした。")
                return pd.DataFrame()
            df = df.reset_index()
            df.columns = [col.lower().replace(' ', '_') for col in df.columns]
            
            if 'date' in df.columns:
                if not pd.api.types.is_datetime64_any_dtype(df["date"]):
                    df["date"] = pd.to_datetime(df["date"])
                df["date"] = df["date"].dt.tz_localize(None) if df["date"].dt.tz is not None else df["date"]
                df["date"] = df["date"].dt.date # 時刻情報を削除
            return df
        except Exception as e:
            logger.error(f"{symbol} のOHLCVデータ取得中にエラーが発生しました: {e}")
            raise DataCollectionError(f"OHLCV data collection failed for {symbol}: {e}") from e

    def collect_ohlcv_data(self, symbol: str, start_date: date, end_date: date) -> List[OhlcvModel]:
        """
        指定期間のOHLCVデータを収集し、キャッシュ保存後、データを返す。
        """
        cache_path = os.path.join(self.cache_dir, f"ohlcv_{symbol}.csv")
        
        # 1. ローカルキャッシュから読込
        cached_df = pd.DataFrame()
        if os.path.exists(cache_path):
            try:
                cached_df = pd.read_csv(cache_path)
                cached_df['date'] = pd.to_datetime(cached_df['date']).dt.date
            except Exception as e:
                print(f"キャッシュOHLCVの読み込み失敗、再取得します: {e}")

        # 期間の充足チェック
        need_fetch = True
        if not cached_df.empty:
            min_date = cached_df['date'].min()
            max_date = cached_df['date'].max()
            # キャッシュが必要な期間を完全にカバーしていれば、ネット取得をスキップ
            if min_date <= start_date and max_date >= end_date:
                need_fetch = False
                df_filtered = cached_df[(cached_df['date'] >= start_date) & (cached_df['date'] <= end_date)]
                print(f"{symbol} のOHLCVデータをローカルキャッシュから最速ロードしました。")
            else:
                # キャッシュ対象外の期間があれば、カバーする広めの期間で再取得
                start_date = min(start_date, min_date)
                end_date = max(end_date, max_date)

        if need_fetch:
            df = self._get_ohlcv_from_yfinance(symbol, start_date, end_date)
            if df.empty:
                # 取得失敗時はキャッシュから返せるだけ返す
                if not cached_df.empty:
                    df_filtered = cached_df[(cached_df['date'] >= start_date) & (cached_df['date'] <= end_date)]
                else:
                    return []
            else:
                # キャッシュを保存
                df.to_csv(cache_path, index=False)
                df_filtered = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
        else:
            df = df_filtered

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
        return ohlcv_data

    def _get_irbank_file_path(self, year_suffix: str, fy_type: str) -> str:
        """
        IR BANKのJSONキャッシュパスを取得する（ユーザー共有フォルダを優先、なければローカル）
        """
        file_name = f"{year_suffix}-{fy_type}.json"
        
        # 1. ユーザーフォルダを探索
        user_path = os.path.join(self.user_irbank_dir, file_name)
        if os.path.exists(user_path):
            return user_path
            
        # 2. ローカルプロジェクトフォルダを探索
        local_path = os.path.join(self.local_irbank_dir, file_name)
        return local_path

    def _download_irbank_file(self, year_suffix: str, fy_type: str, save_path: str):
        """
        IR BANKから安全にJSONファイルをダウンロードする
        """
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
            'Referer': 'https://irbank.net/',
            'Accept': 'application/json, text/plain, */*',
        }
        url = f"{self.URL_IRBANK_FILES}{year_suffix}/{fy_type}"
        print(f"IR BANK からダウンロード中...: {url}")
        
        # 負荷分散のためのランダムスリープ
        time.sleep(random.randint(1, 3))
        
        response = session.get(url, headers=headers, allow_redirects=True)
        if response.status_code != 200:
            raise Exception(f"IR BANKダウンロード失敗: HTTP {response.status_code}")
            
        with open(save_path, 'wb') as f:
            f.write(response.content)
        print(f"ダウンロード完了: {save_path}")

    def _load_irbank_json(self, year: int, fy_type: str) -> Optional[Dict]:
        """
        指定年度のIR BANKの財務JSONデータをロードする
        """
        # 2010年以降の場合にサフィックス生成
        if year >= 2010:
            year_suffix = f"00{str(year)[-2:]}"
        else:
            year_suffix = "0000" # 最新
            
        file_path = self._get_irbank_file_path(year_suffix, fy_type)
        
        # キャッシュがなければ自動ダウンロード
        if not os.path.exists(file_path):
            try:
                self._download_irbank_file(year_suffix, fy_type, file_path)
            except Exception as e:
                print(f"エラー: IR BANKファイル({year_suffix}-{fy_type})取得失敗: {e}")
                return None
                
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"エラー: JSON読込失敗({file_path}): {e}")
            if os.path.exists(file_path):
                os.remove(file_path) # 壊れたファイルを削除
            return None

    def collect_financial_data(self, symbol: str, fiscal_year: int) -> Optional[FinancialModel]:
        """
        指定年度の財務データを収集し、FinancialModelを構築して返す。
        """
        code = self._parse_symbol(symbol)
        print(f"実財務データをキャッシュ読込中... {symbol}(コード: {code}), 会計年度: {fiscal_year}")

        # 1. バランスシート & PLのロード
        bs_data = self._load_irbank_json(fiscal_year, self.BALANCE_SHEET_FILE_NAME)
        pl_data = self._load_irbank_json(fiscal_year, self.PROFIT_AND_LOSS_FILE_NAME)

        if not bs_data or not pl_data:
            print(f"警告: {fiscal_year}年度の財務データロードに失敗しました。")
            return None

        bs_items = bs_data.get("item", {})
        pl_items = pl_data.get("item", {})

        # 指定コードのデータが存在するか確認
        if code not in bs_items or code not in pl_items:
            print(f"警告: コード {code} の財務データが {fiscal_year}年度に見つかりませんでした。")
            return None

        # 単年の値抽出
        bs_val = bs_items[code]
        pl_val = pl_items[code]

        # 抽出処理における数値変換ヘルパー
        def to_float(val) -> float:
            if val is None or val == "-":
                return 0.0
            try:
                return float(val)
            except ValueError:
                return 0.0

        # BS データのパース
        # ["年度","総資産","純資産","株主資本","利益剰余金","短期借入金","長期借入金","BPS","自己資本比率"]
        bps = to_float(bs_val[7])

        # PL データのパース
        # ["年度","売上高","営業利益","経常利益","当期純利益","EPS","ROE","ROA"]
        revenue = to_float(pl_val[1])
        operating_profit = to_float(pl_val[2])
        net_profit = to_float(pl_val[4])
        eps = to_float(pl_val[5])
        roe = to_float(pl_val[6])
        roa = to_float(pl_val[7])

        # 2. 過去の売上高・純利益時系列をロードして成長率を計算する
        # CAGR計算用に直近5年分のPLを走査
        history_years = [fiscal_year - j for j in range(6)] # 0〜5年前
        history_pl = {}
        for y in history_years:
            y_pl = self._load_irbank_json(y, self.PROFIT_AND_LOSS_FILE_NAME)
            if y_pl and code in y_pl.get("item", {}):
                history_pl[y] = y_pl["item"][code]

        # 成長率（CAGR）の計算
        revenue_growth = 0.0
        net_profit_growth = 0.0
        revenue_growth_3y_avg = 0.0
        revenue_growth_5y_avg = 0.0
        net_profit_growth_3y_avg = 0.0
        net_profit_growth_5y_avg = 0.0

        # 1年前との単年成長率
        if fiscal_year - 1 in history_pl:
            pl_prev = history_pl[fiscal_year - 1]
            rev_prev = to_float(pl_prev[1])
            net_prev = to_float(pl_prev[4])
            if rev_prev > 0:
                revenue_growth = ((revenue - rev_prev) / rev_prev) * 100.0
            if net_prev > 0:
                net_profit_growth = ((net_profit - net_prev) / net_prev) * 100.0

        # 3年平均成長率（CAGR）
        if fiscal_year - 3 in history_pl:
            pl_prev_3 = history_pl[fiscal_year - 3]
            rev_prev_3 = to_float(pl_prev_3[1])
            net_prev_3 = to_float(pl_prev_3[4])
            if rev_prev_3 > 0 and revenue > 0:
                revenue_growth_3y_avg = ((revenue / rev_prev_3) ** (1.0 / 3.0) - 1.0) * 100.0
            if net_prev_3 > 0 and net_profit > 0:
                net_profit_growth_3y_avg = ((net_profit / net_prev_3) ** (1.0 / 3.0) - 1.0) * 100.0

        # 5年平均成長率（CAGR）
        if fiscal_year - 5 in history_pl:
            pl_prev_5 = history_pl[fiscal_year - 5]
            rev_prev_5 = to_float(pl_prev_5[1])
            net_prev_5 = to_float(pl_prev_5[4])
            if rev_prev_5 > 0 and revenue > 0:
                revenue_growth_5y_avg = ((revenue / rev_prev_5) ** (1.0 / 5.0) - 1.0) * 100.0
            if net_prev_5 > 0 and net_profit > 0:
                net_profit_growth_5y_avg = ((net_profit / net_prev_5) ** (1.0 / 5.0) - 1.0) * 100.0

        # 3. 最新の株価を取得してPER, PBRをリアルタイム算出
        # yfinanceから直近終値、またはohlcvキャッシュの最後の日付を基準にする
        per = 0.0
        pbr = 0.0
        try:
            # 安全に直近の株価を1日分引いて算出を試みる
            ohlcv_list = self.collect_ohlcv_data(symbol, date(fiscal_year, 1, 1), date(fiscal_year + 1, 6, 30))
            if ohlcv_list:
                latest_close = ohlcv_list[-1].close
                if eps > 0:
                    per = latest_close / eps
                if bps > 0:
                    pbr = latest_close / bps
        except Exception as e:
            print(f"警告: 最新株価の取得・PER/PBR算出に失敗しました: {e}")

        # FinancialModelオブジェクトの構築
        financial_model = FinancialModel(
            symbol=symbol,
            fiscal_date=date(fiscal_year, 3, 31), # デフォルトで3月決算を仮定
            eps=eps,
            bps=bps,
            roe=roe,
            roa=roa,
            per=per,
            pbr=pbr,
            revenue=revenue,
            operating_profit=operating_profit,
            net_profit=net_profit,
            revenue_growth=revenue_growth,
            net_profit_growth=net_profit_growth,
            revenue_growth_3y_avg=revenue_growth_3y_avg,
            revenue_growth_5y_avg=revenue_growth_5y_avg,
            net_profit_growth_3y_avg=net_profit_growth_3y_avg,
            net_profit_growth_5y_avg=net_profit_growth_5y_avg
        )

        print(f"実財務データの取得に成功しました。({symbol})")
        return financial_model

# モジュールレベルでインスタンス化
data_collector = DataCollector()

def collect_ohlcv_data(symbol: str, start_date: date, end_date: date) -> List[OhlcvModel]:
    return data_collector.collect_ohlcv_data(symbol, start_date, end_date)

def collect_financial_data(symbol: str, fiscal_year: int) -> Optional[FinancialModel]:
    return data_collector.collect_financial_data(symbol, fiscal_year)
