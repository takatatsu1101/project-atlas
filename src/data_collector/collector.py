import os
import json
import random
import time
import re
import calendar
from datetime import date, datetime, timedelta
from typing import Any, List, Dict, Optional, Tuple
import pandas as pd
import yfinance as yf
import requests

from src.model.data_models import OhlcvModel, FinancialModel
from src.config.settings import load_settings
from src.common.logger import get_logger
from src.common.exceptions import DataCollectionError
from src.common.storage import StorageManager

logger = get_logger("DataCollector")

# 設定をロード
settings = load_settings()

class DataCollector:
    def __init__(self):
        self.storage = StorageManager()
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
        '9984.T' や '130a.T' から数字4桁・英数字4桁のコード部を抽出する
        """
        match = re.match(r"^([A-Za-z0-9]{4})", symbol)
        if match:
            return match.group(1).upper()
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

    def collect_ohlcv_data(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        as_of_date: Optional[date] = None,
    ) -> List[OhlcvModel]:
        """
        指定期間のOHLCVデータを収集し、Parquet永続化・差分更新を行い、データを返す。
        as_of_date が指定された場合は、その日付以降のデータを含めない（先読みバイアス防止）。
        """
        effective_end = min(end_date, as_of_date) if as_of_date is not None else end_date
        if start_date > effective_end:
            return []

        req_start = start_date
        req_end = effective_end
        fetch_start = start_date
        fetch_end = end_date

        parquet_path = f"price/{symbol}.parquet"

        # 1. 既存のParquetデータをロード
        cached_df = self.storage.load_parquet(parquet_path)

        need_fetch = True
        if cached_df is not None and not cached_df.empty:
            if 'date' in cached_df.columns:
                if not pd.api.types.is_datetime64_any_dtype(cached_df["date"]):
                    cached_df["date"] = pd.to_datetime(cached_df["date"])
                cached_df["date"] = cached_df["date"].dt.tz_localize(None) if cached_df["date"].dt.tz is not None else cached_df["date"]
                cached_df["date"] = cached_df["date"].dt.date

                min_date = cached_df['date'].min()
                max_date = cached_df['date'].max()

                # キャッシュが要求期間を完全にカバーしていれば再取得不要
                if min_date <= req_start and max_date >= req_end:
                    need_fetch = False
                    logger.info(f"{symbol} のOHLCVデータをParquetストレージからロードしました。")
                else:
                    # 不足分がある場合は期間を拡張して再取得しマージ（キャッシュの中抜け防止のため as_of_date で切り詰めない）
                    fetch_start = min(start_date, min_date)
                    fetch_end = max(end_date, max_date)

        if need_fetch:
            new_df = self._get_ohlcv_from_yfinance(symbol, fetch_start, fetch_end)
            if new_df.empty:
                if cached_df is not None and not cached_df.empty:
                    df_filtered = cached_df[(cached_df['date'] >= req_start) & (cached_df['date'] <= req_end)]
                else:
                    return []
            else:
                if cached_df is not None and not cached_df.empty:
                    # 既存データと新着データを結合し、日付で重複排除（新着優先）
                    combined_df = pd.concat([cached_df, new_df]).drop_duplicates(subset=['date'], keep='last')
                    combined_df = combined_df.sort_values('date').reset_index(drop=True)
                else:
                    combined_df = new_df.sort_values('date').reset_index(drop=True)

                # Parquetとして保存
                self.storage.save_parquet(combined_df, parquet_path)
                cached_df = combined_df

            df_filtered = cached_df[(cached_df['date'] >= req_start) & (cached_df['date'] <= req_end)]
        else:
            df_filtered = cached_df[(cached_df['date'] >= req_start) & (cached_df['date'] <= req_end)]

        ohlcv_data = []
        for _, row in df_filtered.iterrows():
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

    def _get_irbank_file_path(self, year_suffix: str, file_name: str) -> str:
        """
        IR BANKのJSONファイルパスを取得する。
        探索順序: ① data/financial/ -> ② data/cache/irbank_code_data/ -> ③ ユーザー共有フォルダ
        どこにも存在しない場合はダウンロード保存先として ① data/financial/ のパスを返す。
        """
        # 1. data/financial/ を最優先で探索
        financial_path = os.path.join(str(self.storage.financial_dir), file_name)
        if os.path.exists(financial_path):
            return financial_path

        # 2. ローカルプロジェクトキャッシュフォルダを探索
        local_path = os.path.join(self.local_irbank_dir, file_name)
        if os.path.exists(local_path):
            return local_path

        # 3. ユーザー共有フォルダを探索
        user_path = os.path.join(self.user_irbank_dir, file_name)
        if os.path.exists(user_path):
            return user_path

        return financial_path

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
        logger.info(f"IR BANK からダウンロード中...: {url}")
        
        # 負荷分散のためのランダムスリープ
        time.sleep(random.randint(1, 3))
        
        response = session.get(url, headers=headers, allow_redirects=True)
        if response.status_code != 200:
            raise Exception(f"IR BANKダウンロード失敗: HTTP {response.status_code}")

        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'wb') as f:
            f.write(response.content)
        logger.info(f"ダウンロード完了: {save_path}")

    def _load_irbank_json(self, year: int, fy_type: str, allow_download: bool = True) -> Optional[Dict]:
        """
        指定年度のIR BANKの財務JSONデータをStorageManagerを利用してロードする
        """
        # 2010年以降の場合にサフィックス生成
        if year >= 2010:
            year_suffix = f"00{str(year)[-2:]}"
        else:
            year_suffix = "0000" # 最新
            
        file_name = f"{year_suffix}-{fy_type}"
        file_path = self._get_irbank_file_path(year_suffix, file_name)
        
        # キャッシュがなければ自動ダウンロード（allow_download=False の場合は抑制）
        if not os.path.exists(file_path):
            if not allow_download:
                return None
            try:
                self._download_irbank_file(year_suffix, fy_type, file_path)
            except Exception as e:
                logger.error(f"エラー: IR BANKファイル({year_suffix}-{fy_type})取得失敗: {e}")
                return None
                
        # StorageManagerのload_jsonを利用してロード
        data = self.storage.load_json(file_path)
        if data is None and os.path.exists(file_path):
            # 読込失敗時は破損ファイルとして削除
            try:
                os.remove(file_path)
            except Exception:
                pass
        return data

    @staticmethod
    def _to_float(val: Any) -> float:
        """数値変換ヘルパー"""
        if val is None or val == "-":
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _to_optional_float(val: Any) -> Optional[float]:
        """欠損値('-')と0.0を区別するオプショナル数値変換ヘルパー"""
        if val is None or val == "-":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_fiscal_year_month(ym_str: Any) -> Optional[date]:
        """IR BANK の 'YYYY/MM' 形式文字列を解析し、その月の末日を返す"""
        if not ym_str or not isinstance(ym_str, str):
            return None
        match = re.match(r"^\s*(\d{4})[/\-](\d{1,2})\s*$", ym_str)
        if not match:
            return None
        year = int(match.group(1))
        month = int(match.group(2))
        if not (1 <= month <= 12):
            return None
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, last_day)

    @staticmethod
    def _is_disclosed(fiscal_end_date: date, as_of_date: date, disclosure_lag_days: int) -> bool:
        """決算期末月末日 + 開示ラグ日数が as_of_date 以下であれば開示済みと判定する"""
        return (fiscal_end_date + timedelta(days=disclosure_lag_days)) <= as_of_date

    def _resolve_disclosed_entry(
        self,
        code: str,
        target_year: int,
        as_of_date: Optional[date],
        disclosure_lag_days: int,
        bs_by_year: Dict[int, Optional[Dict]],
        pl_by_year: Dict[int, Optional[Dict]],
    ) -> Optional[Tuple[int, List[Any], List[Any], date]]:
        """
        指定年度（as_of_date 指定時は開示済みとなるまで最大2期遡る）の BS・PL エントリを解決する。
        """
        max_lookback = 3 if as_of_date is not None else 1
        for offset in range(max_lookback):
            candidate_year = target_year - offset
            if candidate_year not in bs_by_year:
                bs_by_year[candidate_year] = self._load_irbank_json(candidate_year, self.BALANCE_SHEET_FILE_NAME)
            if candidate_year not in pl_by_year:
                pl_by_year[candidate_year] = self._load_irbank_json(candidate_year, self.PROFIT_AND_LOSS_FILE_NAME)

            bs_data = bs_by_year[candidate_year]
            pl_data = pl_by_year[candidate_year]
            if not bs_data or not pl_data:
                continue

            bs_items = bs_data.get("item", {})
            pl_items = pl_data.get("item", {})
            if code not in bs_items or code not in pl_items:
                continue

            bs_val = bs_items[code]
            pl_val = pl_items[code]
            parsed_date = self._parse_fiscal_year_month(bs_val[0] if bs_val else None)
            if parsed_date is None:
                parsed_date = self._parse_fiscal_year_month(pl_val[0] if pl_val else None)
            fiscal_end_date = parsed_date or date(candidate_year, 3, 31)

            if as_of_date is not None and not self._is_disclosed(fiscal_end_date, as_of_date, disclosure_lag_days):
                continue

            return candidate_year, bs_val, pl_val, fiscal_end_date

        return None

    def collect_financial_data(
        self,
        symbol: str,
        fiscal_year: Optional[int] = None,
        as_of_date: Optional[date] = None,
        disclosure_lag_days: int = settings.FINANCIAL_DISCLOSURE_LAG_DAYS,
    ) -> Optional[FinancialModel]:
        """
        指定年度の財務データを収集し、FinancialModelを構築して返す。
        as_of_date 指定時は決算期末月末日 + disclosure_lag_days で開示判定を行い、
        未開示の場合は最大2期分遡って開示済みの年度データを採用する。
        """
        code = self._parse_symbol(symbol)
        target_year = fiscal_year if fiscal_year is not None else (as_of_date or date.today()).year
        logger.info(f"実財務データをキャッシュ読込中... {symbol}(コード: {code}), 会計年度: {target_year}")

        bs_cache: Dict[int, Optional[Dict]] = {}
        pl_cache: Dict[int, Optional[Dict]] = {}
        resolved = self._resolve_disclosed_entry(
            code=code,
            target_year=target_year,
            as_of_date=as_of_date,
            disclosure_lag_days=disclosure_lag_days,
            bs_by_year=bs_cache,
            pl_by_year=pl_cache,
        )
        if resolved is None:
            logger.warning(f"コード {code} の開示済み財務データが {target_year}年度（遡及含む）で見つかりませんでした。")
            return None

        adopted_year, bs_val, pl_val, fiscal_date = resolved
        to_float = self._to_float
        to_opt_float = self._to_optional_float

        # BS データのパース
        # ["年度","総資産","純資産","株主資本","利益剰余金","短期借入金","長期借入金","BPS","自己資本比率"]
        total_assets = to_opt_float(bs_val[1]) if len(bs_val) > 1 else None
        bps = to_float(bs_val[7]) if len(bs_val) > 7 else 0.0
        equity_ratio = to_opt_float(bs_val[8]) if len(bs_val) > 8 else None

        # PL データのパース
        # ["年度","売上高","営業利益","経常利益","当期純利益","EPS","ROE","ROA"]
        revenue = to_float(pl_val[1]) if len(pl_val) > 1 else 0.0
        operating_profit = to_float(pl_val[2]) if len(pl_val) > 2 else 0.0
        net_profit = to_float(pl_val[4]) if len(pl_val) > 4 else 0.0
        eps = to_float(pl_val[5]) if len(pl_val) > 5 else 0.0
        roe = to_float(pl_val[6]) if len(pl_val) > 6 else 0.0
        roa = to_float(pl_val[7]) if len(pl_val) > 7 else 0.0

        # 2. 過去の売上高・純利益時系列をロードして成長率を計算する
        # CAGR計算用に直近5年分のPLを走査
        history_years = [adopted_year - j for j in range(6)] # 0〜5年前
        history_pl = {}
        for y in history_years:
            y_pl = pl_cache.get(y) if y in pl_cache else self._load_irbank_json(y, self.PROFIT_AND_LOSS_FILE_NAME)
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
        if adopted_year - 1 in history_pl:
            pl_prev = history_pl[adopted_year - 1]
            rev_prev = to_float(pl_prev[1])
            net_prev = to_float(pl_prev[4])
            if rev_prev > 0:
                revenue_growth = ((revenue - rev_prev) / rev_prev) * 100.0
            if net_prev > 0:
                net_profit_growth = ((net_profit - net_prev) / net_prev) * 100.0

        # 3年平均成長率（CAGR）
        if adopted_year - 3 in history_pl:
            pl_prev_3 = history_pl[adopted_year - 3]
            rev_prev_3 = to_float(pl_prev_3[1])
            net_prev_3 = to_float(pl_prev_3[4])
            if rev_prev_3 > 0 and revenue > 0:
                revenue_growth_3y_avg = ((revenue / rev_prev_3) ** (1.0 / 3.0) - 1.0) * 100.0
            if net_prev_3 > 0 and net_profit > 0:
                net_profit_growth_3y_avg = ((net_profit / net_prev_3) ** (1.0 / 3.0) - 1.0) * 100.0

        # 5年平均成長率（CAGR）
        if adopted_year - 5 in history_pl:
            pl_prev_5 = history_pl[adopted_year - 5]
            rev_prev_5 = to_float(pl_prev_5[1])
            net_prev_5 = to_float(pl_prev_5[4])
            if rev_prev_5 > 0 and revenue > 0:
                revenue_growth_5y_avg = ((revenue / rev_prev_5) ** (1.0 / 5.0) - 1.0) * 100.0
            if net_prev_5 > 0 and net_profit > 0:
                net_profit_growth_5y_avg = ((net_profit / net_prev_5) ** (1.0 / 5.0) - 1.0) * 100.0

        # 3. 最新の株価を取得してPER, PBRを算出（as_of_date 指定時は未来株価を参照しない）
        per = 0.0
        pbr = 0.0
        try:
            ohlcv_end_date = as_of_date or date.today()
            if as_of_date is None:
                ohlcv_list = self.collect_ohlcv_data(symbol, date(adopted_year, 1, 1), ohlcv_end_date)
            else:
                ohlcv_list = self.collect_ohlcv_data(
                    symbol,
                    date(adopted_year, 1, 1),
                    ohlcv_end_date,
                    as_of_date=as_of_date,
                )
            if ohlcv_list:
                latest_close = ohlcv_list[-1].close
                if eps > 0:
                    per = latest_close / eps
                if bps > 0:
                    pbr = latest_close / bps
        except Exception as e:
            logger.warning(f"最新株価の取得・PER/PBR算出に失敗しました: {e}")

        # FinancialModelオブジェクトの構築
        financial_model = FinancialModel(
            symbol=symbol,
            fiscal_date=fiscal_date,
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
            net_profit_growth_5y_avg=net_profit_growth_5y_avg,
            total_assets=total_assets,
            equity_ratio=equity_ratio,
        )

        logger.info(f"実財務データの取得に成功しました。({symbol})")
        return financial_model

    def load_financial_snapshot(
        self,
        fiscal_year: Optional[int] = None,
        as_of_date: Optional[date] = None,
        disclosure_lag_days: int = settings.FINANCIAL_DISCLOSURE_LAG_DAYS,
    ) -> Dict[str, FinancialModel]:
        """
        指定年度（as_of_date 指定時は最大2期前まで）の BS・PL JSON を一度だけ読み込み、
        全銘柄分の FinancialModel を 4桁コードキーの辞書として高速に返す。
        yfinance による株価取得や IR BANK からの新規ダウンロードは行わない。
        """
        target_year = fiscal_year if fiscal_year is not None else (as_of_date or date.today()).year
        offsets = (0, 1, 2) if as_of_date is not None else (0,)

        bs_by_year: Dict[int, Optional[Dict]] = {}
        pl_by_year: Dict[int, Optional[Dict]] = {}
        candidate_codes: set[str] = set()

        for offset in offsets:
            y = target_year - offset
            bs_data = self._load_irbank_json(y, self.BALANCE_SHEET_FILE_NAME, allow_download=False)
            pl_data = self._load_irbank_json(y, self.PROFIT_AND_LOSS_FILE_NAME, allow_download=False)
            bs_by_year[y] = bs_data
            pl_by_year[y] = pl_data
            if bs_data and pl_data:
                bs_keys = bs_data.get("item", {}).keys()
                pl_keys = pl_data.get("item", {}).keys()
                candidate_codes.update(bs_keys & pl_keys)

        snapshot: Dict[str, FinancialModel] = {}
        to_float = self._to_float
        to_opt_float = self._to_optional_float

        for code in candidate_codes:
            resolved = self._resolve_disclosed_entry(
                code=code,
                target_year=target_year,
                as_of_date=as_of_date,
                disclosure_lag_days=disclosure_lag_days,
                bs_by_year=bs_by_year,
                pl_by_year=pl_by_year,
            )
            if resolved is None:
                continue

            _, bs_val, pl_val, fiscal_date = resolved
            snapshot[code] = FinancialModel(
                symbol=f"{code}.T",
                fiscal_date=fiscal_date,
                total_assets=to_opt_float(bs_val[1]) if len(bs_val) > 1 else None,
                bps=to_float(bs_val[7]) if len(bs_val) > 7 else 0.0,
                equity_ratio=to_opt_float(bs_val[8]) if len(bs_val) > 8 else None,
                revenue=to_float(pl_val[1]) if len(pl_val) > 1 else 0.0,
                operating_profit=to_float(pl_val[2]) if len(pl_val) > 2 else 0.0,
                net_profit=to_float(pl_val[4]) if len(pl_val) > 4 else 0.0,
                eps=to_float(pl_val[5]) if len(pl_val) > 5 else 0.0,
                roe=to_float(pl_val[6]) if len(pl_val) > 6 else 0.0,
                roa=to_float(pl_val[7]) if len(pl_val) > 7 else 0.0,
            )

        return snapshot


# モジュールレベルでインスタンス化
data_collector = DataCollector()


def collect_ohlcv_data(
    symbol: str,
    start_date: date,
    end_date: date,
    as_of_date: Optional[date] = None,
) -> List[OhlcvModel]:
    if as_of_date is None:
        return data_collector.collect_ohlcv_data(symbol, start_date, end_date)
    return data_collector.collect_ohlcv_data(symbol, start_date, end_date, as_of_date=as_of_date)


def collect_financial_data(
    symbol: str,
    fiscal_year: Optional[int] = None,
    as_of_date: Optional[date] = None,
    disclosure_lag_days: int = 60,
) -> Optional[FinancialModel]:
    if as_of_date is None and disclosure_lag_days == 60:
        return data_collector.collect_financial_data(symbol, fiscal_year)
    return data_collector.collect_financial_data(
        symbol,
        fiscal_year=fiscal_year,
        as_of_date=as_of_date,
        disclosure_lag_days=disclosure_lag_days,
    )
