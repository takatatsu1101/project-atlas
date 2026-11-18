import os
import json
import random
import time
import re
import calendar
from datetime import date, datetime, timedelta
from typing import Any, List, Dict, Optional, Sequence, Tuple
import pandas as pd
import yfinance as yf
import requests

from src.model.data_models import OhlcvModel, FinancialModel
from src.config.settings import load_settings
from src.common.logger import get_logger
from src.common.exceptions import DataCollectionError
from src.common.storage import StorageManager
from src.data_collector.market_calendar import (
    get_first_trading_day_on_or_after,
    get_latest_completed_trading_day,
)

logger = get_logger("DataCollector")

# 設定をロード
settings = load_settings()

# collect_ohlcv_data 用の Parquet 列限定読込対象
OHLCV_READ_COLUMNS: Tuple[str, ...] = ("date", "open", "high", "low", "close", "volume")

class DataCollector:
    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        cache_dir: Optional[str] = None,
        local_irbank_dir: Optional[str] = None,
        user_irbank_dir: Optional[str] = None,
        create_dirs: bool = True,
    ):
        self.storage = storage if storage is not None else StorageManager()
        self.cache_dir = str(cache_dir) if cache_dir is not None else settings.DATA_CACHE_DIR

        # ユーザー提供の既存IR BANKキャッシュディレクトリ
        self.user_irbank_dir = (
            str(user_irbank_dir)
            if user_irbank_dir is not None
            else "/Users/takatoritatsuo/program/python/stock_choice/data_fetcher/code_data"
        )
        # 本プロジェクト内のIR BANKキャッシュ保存先
        self.local_irbank_dir = (
            str(local_irbank_dir)
            if local_irbank_dir is not None
            else os.path.join(self.cache_dir, "irbank_code_data")
        )
        if create_dirs:
            os.makedirs(self.cache_dir, exist_ok=True)
            os.makedirs(self.local_irbank_dir, exist_ok=True)

        # IR BANKのダウンロード用定数
        self.URL_IRBANK_FILES = "https://f.irbank.net/files/"
        self.BALANCE_SHEET_FILE_NAME = "fy-balance-sheet.json"
        self.PROFIT_AND_LOSS_FILE_NAME = "fy-profit-and-loss.json"
        # IR BANK JSON のインメモリキャッシュとダウンロード失敗のネガティブキャッシュ
        self._irbank_json_cache: Dict[str, Dict] = {}
        self._irbank_failed_downloads: set[str] = set()
        # 市場最新完了営業日キャッシュ（(スケジュール終了日, ベンチマーク銘柄) -> (解決済み実市場最新日, 取得時刻)）
        self._market_latest_date_cache: Dict[Tuple[date, str], Tuple[date, float]] = {}
        self._market_latest_cache_ttl_sec: float = 300.0
        # バッチプリフェッチで取得試行済みの期間（symbol -> (fetch_start, fetch_end)）
        self._attempted_fetch_ranges: Dict[str, Tuple[date, date]] = {}

    def _parse_symbol(self, symbol: str) -> str:
        """
        '9984.T' や '130a.T' から数字4桁・英数字4桁のコード部を抽出する
        """
        match = re.match(r"^([A-Za-z0-9]{4})", symbol)
        if match:
            return match.group(1).upper()
        return symbol

    @staticmethod
    def _normalize_date_column(df: pd.DataFrame) -> pd.DataFrame:
        """DataFrame の date 列を datetime.date 型へ正規化する（TZ付きは JST へ変換）。"""
        if df is None or df.empty or "date" not in df.columns:
            return df
        result = df.copy()
        date_series = result["date"]

        if pd.api.types.is_datetime64_any_dtype(date_series):
            if getattr(date_series.dt, "tz", None) is not None:
                date_series = date_series.dt.tz_convert("Asia/Tokyo").dt.tz_localize(None)
            result["date"] = date_series.dt.date
            return result

        orig_valid_count = int(date_series.notna().sum())
        try:
            parsed = pd.to_datetime(date_series, errors="coerce")
        except (TypeError, ValueError):
            parsed = None

        if (
            parsed is not None
            and pd.api.types.is_datetime64_any_dtype(parsed)
            and int(parsed.notna().sum()) == orig_valid_count
        ):
            if getattr(parsed.dt, "tz", None) is not None:
                parsed = parsed.dt.tz_convert("Asia/Tokyo").dt.tz_localize(None)
            result["date"] = parsed.dt.date
            return result

        # 混合TZ・naive/aware混在時は pd.to_datetime が異なるTZ要素を NaT 化するため要素単位で安全変換する
        def _parse_single_date(val: Any) -> Optional[date]:
            if pd.isna(val):
                return None
            if isinstance(val, datetime):
                if val.tzinfo is not None and val.utcoffset() is not None:
                    return pd.Timestamp(val).tz_convert("Asia/Tokyo").date()
                return val.date()
            if isinstance(val, date):
                return val
            try:
                ts = pd.Timestamp(val)
            except Exception:
                return None
            if pd.isna(ts):
                return None
            if ts.tzinfo is not None:
                return ts.tz_convert("Asia/Tokyo").date()
            return ts.date()

        result["date"] = date_series.map(_parse_single_date)
        return result

    @staticmethod
    def _finalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
        """OHLCV DataFrame の列構成（標準8列）と数値型（volume int64・actions float64）を統一する。"""
        result = df.copy()
        if "volume" not in result.columns:
            result["volume"] = 0
        result["volume"] = (
            pd.to_numeric(result["volume"], errors="coerce").fillna(0).round().astype("int64")
        )

        standard_cols = ["date", "open", "high", "low", "close", "volume"]
        for action_col in ("dividends", "stock_splits"):
            if action_col in result.columns:
                result[action_col] = pd.to_numeric(result[action_col], errors="coerce").fillna(0.0)
                standard_cols.append(action_col)

        existing_cols = [col for col in standard_cols if col in result.columns]
        return result[existing_cols]

    @classmethod
    def _normalize_ohlcv_df(
        cls,
        df: pd.DataFrame,
        max_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """OHLCV DataFrame の列名・日付型・必須OHLC列・欠損値・上限日付を正規化する。"""
        if df is None or df.empty:
            return pd.DataFrame()

        result = df.copy()
        cols_lower = [str(col).lower().replace(" ", "_") for col in result.columns]
        if "date" not in cols_lower:
            result = result.reset_index()
            result.columns = [str(col).lower().replace(" ", "_") for col in result.columns]
            if "date" not in result.columns and "index" in result.columns:
                result = result.rename(columns={"index": "date"})
            elif "date" not in result.columns and "datetime" in result.columns:
                result = result.rename(columns={"datetime": "date"})
        else:
            result.columns = cols_lower

        if "date" not in result.columns:
            return pd.DataFrame()

        result = cls._normalize_date_column(result)
        result = result[result["date"].notna()]
        if result.empty:
            return pd.DataFrame()

        required_price_cols = ["open", "high", "low", "close"]
        if not all(col in result.columns for col in required_price_cols):
            return pd.DataFrame()

        for col in required_price_cols:
            result[col] = pd.to_numeric(result[col], errors="coerce")
        result = result.dropna(subset=required_price_cols)
        if result.empty:
            return pd.DataFrame()

        if max_date is not None:
            result = result[result["date"] <= max_date]
            if result.empty:
                return pd.DataFrame()

        result = cls._finalize_ohlcv_columns(result)
        return result.reset_index(drop=True)

    def _fetch_ticker_history_df(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """yf.Ticker.history で期間データを取得し、正規化済み DataFrame を返す共通ヘルパー。"""
        ticker = yf.Ticker(symbol)
        # yfinance の end は exclusive のため +1 日して当日足落ちを防ぐ
        yf_end = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")
        df = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=yf_end)
        if df is None or df.empty:
            return pd.DataFrame()
        return self._normalize_ohlcv_df(df, max_date=end_date)

    def _get_ohlcv_from_yfinance(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        """
        Yahoo FinanceからOHLCVデータを取得する。
        """
        logger.info(f"Yahoo Financeから {symbol} のOHLCVデータを取得中... ({start_date} - {end_date})")
        try:
            norm_df = self._fetch_ticker_history_df(symbol, start_date, end_date)
            if norm_df.empty:
                logger.warning(f"{symbol} のOHLCVデータが見つかりませんでした。")
                return pd.DataFrame()
            return norm_df
        except Exception as e:
            logger.error(f"{symbol} のOHLCVデータ取得中にエラーが発生しました: {e}")
            raise DataCollectionError(f"OHLCV data collection failed for {symbol}: {e}") from e

    def _fetch_benchmark_latest_date(
        self,
        benchmark_symbol: str,
        start_date: date,
        end_date: date,
    ) -> Optional[date]:
        """ベンチマーク銘柄の直近バーから実際の市場最新完了営業日を取得する。"""
        try:
            norm_df = self._fetch_ticker_history_df(benchmark_symbol, start_date, end_date)
            if norm_df.empty or "date" not in norm_df.columns:
                return None
            latest = norm_df["date"].max()
            return latest.date() if isinstance(latest, datetime) else latest
        except Exception as e:
            logger.warning(f"市場最新営業日のプリチェック ({benchmark_symbol}) に失敗しました: {e}")
            return None

    def _get_cached_market_latest_date(
        self,
        schedule_end: date,
        benchmark_symbol: str = "1306.T",
    ) -> Optional[date]:
        """TTL を考慮してキャッシュ済みの市場最新完了営業日を返す（期限切れ時は None）。"""
        entry = self._market_latest_date_cache.get((schedule_end, benchmark_symbol))
        if entry is None:
            return None
        resolved_date, cached_at = entry
        if resolved_date < schedule_end:
            if (time.monotonic() - cached_at) > self._market_latest_cache_ttl_sec:
                return None
        return resolved_date

    def resolve_latest_completed_trading_day(
        self,
        ref_date: Optional[date] = None,
        benchmark_symbol: str = "1306.T",
        use_remote_precheck: bool = True,
    ) -> date:
        """スケジュール基準の最新完了営業日を解決し、必要に応じベンチマーク銘柄で実市場日を確認する。"""
        schedule_end = get_latest_completed_trading_day(ref_date=ref_date)
        cached_resolved = self._get_cached_market_latest_date(
            schedule_end, benchmark_symbol=benchmark_symbol
        )
        if cached_resolved is not None:
            return cached_resolved

        if not use_remote_precheck:
            return schedule_end

        actual_latest = self._fetch_benchmark_latest_date(
            benchmark_symbol=benchmark_symbol,
            start_date=schedule_end - timedelta(days=14),
            end_date=schedule_end,
        )
        if actual_latest is not None:
            resolved = min(schedule_end, actual_latest)
            self._market_latest_date_cache[(schedule_end, benchmark_symbol)] = (
                resolved,
                time.monotonic(),
            )
            return resolved

        return schedule_end

    def _resolve_expected_range(
        self,
        req_start: date,
        req_end: date,
        market_latest_date: Optional[date] = None,
        benchmark_symbol: str = "1306.T",
    ) -> Tuple[date, date]:
        """要求期間の期待営業日開始日・終了日を算出する。"""
        expected_start = get_first_trading_day_on_or_after(req_start)
        expected_end = get_latest_completed_trading_day(ref_date=req_end)
        resolved_market_latest = (
            market_latest_date
            if market_latest_date is not None
            else self._get_cached_market_latest_date(expected_end, benchmark_symbol=benchmark_symbol)
        )
        if resolved_market_latest is not None:
            expected_end = min(expected_end, resolved_market_latest)
        return expected_start, expected_end

    def _is_cache_sufficient(
        self,
        cached_df: Optional[pd.DataFrame],
        req_start: date,
        req_end: date,
        market_latest_date: Optional[date] = None,
    ) -> bool:
        """ローカルキャッシュが要求期間の完了営業日を十分にカバーしているかを判定する。"""
        if cached_df is None or cached_df.empty or "date" not in cached_df.columns:
            return False

        normalized_df = self._normalize_date_column(cached_df)
        normalized_df = normalized_df[normalized_df["date"].notna()]
        if normalized_df.empty:
            return False

        expected_start, expected_end = self._resolve_expected_range(
            req_start, req_end, market_latest_date=market_latest_date
        )
        if expected_start > expected_end:
            return True

        min_date = normalized_df["date"].min()
        max_date = normalized_df["date"].max()
        return bool(min_date <= expected_start and max_date >= expected_end)

    def _merge_and_save_ohlcv(
        self,
        symbol: str,
        cached_df: Optional[pd.DataFrame],
        new_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """既存キャッシュと新規取得 OHLCV を日付重複排除・ソート・型統一して Parquet 保存する。"""
        if cached_df is not None and not cached_df.empty:
            combined_df = pd.concat([cached_df, new_df], ignore_index=True).drop_duplicates(
                subset=["date"], keep="last"
            )
            combined_df = combined_df.sort_values("date").reset_index(drop=True)
        else:
            combined_df = new_df.sort_values("date").reset_index(drop=True)

        combined_df = self._finalize_ohlcv_columns(combined_df)
        self.storage.save_parquet(combined_df, f"price/{symbol}.parquet")
        return combined_df

    @staticmethod
    def _extract_symbol_df_from_download(
        raw_df: Optional[pd.DataFrame],
        symbol: str,
        chunk_len: int,
    ) -> pd.DataFrame:
        """yf.download の戻り値から指定銘柄の DataFrame を抽出する。"""
        if raw_df is None or raw_df.empty:
            return pd.DataFrame()

        if isinstance(raw_df.columns, pd.MultiIndex):
            level0 = raw_df.columns.get_level_values(0)
            if symbol in level0:
                return raw_df[symbol].copy()
            upper_map0 = {str(k).upper(): k for k in dict.fromkeys(level0)}
            if symbol.upper() in upper_map0:
                return raw_df[upper_map0[symbol.upper()]].copy()

            if raw_df.columns.nlevels > 1:
                level1 = raw_df.columns.get_level_values(1)
                if symbol in level1:
                    return raw_df.xs(symbol, axis=1, level=1).copy()
                upper_map1 = {str(k).upper(): k for k in dict.fromkeys(level1)}
                if symbol.upper() in upper_map1:
                    return raw_df.xs(upper_map1[symbol.upper()], axis=1, level=1).copy()
            return pd.DataFrame()

        if chunk_len == 1:
            return raw_df.copy()
        return pd.DataFrame()

    @staticmethod
    def _build_prefetch_summary(
        total: int,
        skipped: int,
        batch_updated: int = 0,
        retried_updated: int = 0,
        failed_symbols: Optional[List[str]] = None,
        market_latest_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """バッチプリフェッチの結果サマリー辞書を構築する。"""
        failed_list = list(failed_symbols or [])
        return {
            "total": total,
            "skipped": skipped,
            "batch_updated": batch_updated,
            "retried_updated": retried_updated,
            "failed": len(failed_list),
            "failed_symbols": failed_list,
            "market_latest_date": market_latest_date,
        }

    def _classify_cached_symbols(
        self,
        symbols: Sequence[str],
        schedule_expected_start: date,
        schedule_expected_end: date,
    ) -> Tuple[
        Dict[str, Optional[pd.DataFrame]],
        Dict[str, Tuple[date, date]],
        List[str],
        List[str],
        List[str],
    ]:
        """各銘柄のローカル Parquet を読み込み、スキップ・末尾不足候補・全取得に分類する。"""
        cached_dfs: Dict[str, Optional[pd.DataFrame]] = {}
        cached_ranges: Dict[str, Tuple[date, date]] = {}
        skipped_symbols: List[str] = []
        tail_missing_candidates: List[str] = []
        head_or_full_missing: List[str] = []

        for symbol in symbols:
            try:
                df = self.storage.load_parquet(f"price/{symbol}.parquet")
            except Exception as e:
                logger.warning(
                    f"{symbol} のParquetキャッシュ読込に失敗したためキャッシュなしとして扱います: {e}"
                )
                df = None

            if df is not None and not df.empty and "date" in df.columns:
                df = self._normalize_date_column(df)
                df = df[df["date"].notna()]
            if df is None or df.empty or "date" not in df.columns:
                cached_dfs[symbol] = None
                head_or_full_missing.append(symbol)
                continue

            cached_dfs[symbol] = df
            min_d = df["date"].min()
            max_d = df["date"].max()
            cached_ranges[symbol] = (min_d, max_d)

            start_ok = min_d <= schedule_expected_start
            end_ok = max_d >= schedule_expected_end
            if start_ok and end_ok:
                skipped_symbols.append(symbol)
            elif start_ok and not end_ok:
                tail_missing_candidates.append(symbol)
            else:
                head_or_full_missing.append(symbol)

        return (
            cached_dfs,
            cached_ranges,
            skipped_symbols,
            tail_missing_candidates,
            head_or_full_missing,
        )

    def _build_prefetch_groups(
        self,
        req_start: date,
        req_end_raw: date,
        cached_ranges: Dict[str, Tuple[date, date]],
        tail_missing_symbols: Sequence[str],
        head_or_full_missing: Sequence[str],
    ) -> List[Tuple[str, Dict[str, Tuple[date, date]]]]:
        """不足種別ごとに銘柄別フェッチ範囲を算出し、取得グループリストを構築する。"""
        fetch_groups: List[Tuple[str, Dict[str, Tuple[date, date]]]] = []
        if tail_missing_symbols:
            tail_ranges: Dict[str, Tuple[date, date]] = {}
            for sym in tail_missing_symbols:
                min_d, max_d = cached_ranges[sym]
                # req_start > max_d の場合でも既存キャッシュ min_d..max_d との連続性を保ち中抜けを防ぐ
                sym_start = max(min(req_start, min_d), max_d - timedelta(days=7))
                sym_end = max(req_end_raw, max_d)
                tail_ranges[sym] = (sym_start, sym_end)
            fetch_groups.append(("tail_missing", tail_ranges))

        if head_or_full_missing:
            full_ranges: Dict[str, Tuple[date, date]] = {}
            for sym in head_or_full_missing:
                if sym in cached_ranges:
                    min_d, max_d = cached_ranges[sym]
                    sym_start = min(req_start, min_d)
                    sym_end = max(req_end_raw, max_d)
                else:
                    sym_start = req_start
                    sym_end = req_end_raw
                full_ranges[sym] = (sym_start, sym_end)
            fetch_groups.append(("full_or_head_missing", full_ranges))

        return fetch_groups

    def _execute_prefetch_group(
        self,
        group_name: str,
        sym_ranges: Dict[str, Tuple[date, date]],
        cached_dfs: Dict[str, Optional[pd.DataFrame]],
        chunk_size: int,
        failed_symbols: List[str],
    ) -> Tuple[int, int]:
        """取得グループを sym_start 降順ソートしてチャンク分割し、バッチ取得・個別リトライを実行する。"""
        sorted_symbols = sorted(
            sym_ranges.keys(),
            key=lambda s: sym_ranges[s][0],
            reverse=True,
        )
        group_min_start = min(r[0] for r in sym_ranges.values())
        group_max_end = max(r[1] for r in sym_ranges.values())
        logger.info(
            f"OHLCVバッチ取得開始 [{group_name}]: {len(sorted_symbols)}銘柄 "
            f"({group_min_start} - {group_max_end}, chunk_size={chunk_size})"
        )

        batch_updated = 0
        retried_updated = 0
        retry_targets: List[str] = []
        attempted_chunk_ranges: Dict[str, Tuple[date, date]] = {}

        for idx in range(0, len(sorted_symbols), chunk_size):
            chunk = sorted_symbols[idx : idx + chunk_size]
            chunk_start = min(sym_ranges[s][0] for s in chunk)
            chunk_end = max(sym_ranges[s][1] for s in chunk)
            yf_end = (chunk_end + timedelta(days=1)).strftime("%Y-%m-%d")

            try:
                raw_df = yf.download(
                    tickers=chunk,
                    start=chunk_start.strftime("%Y-%m-%d"),
                    end=yf_end,
                    actions=True,
                    threads=True,
                    group_by="ticker",
                    progress=False,
                )
            except Exception as e:
                logger.warning(
                    f"yf.download チャンク取得に失敗したため個別リトライへ回します ({len(chunk)}銘柄): {e}"
                )
                retry_targets.extend(chunk)
                continue

            if raw_df is None or raw_df.empty:
                logger.warning(
                    f"yf.download の戻り値が空のため個別リトライへ回します ({len(chunk)}銘柄)"
                )
                retry_targets.extend(chunk)
                continue

            for sym in chunk:
                sub_df = self._extract_symbol_df_from_download(raw_df, sym, len(chunk))
                norm_df = self._normalize_ohlcv_df(sub_df, max_date=chunk_end)
                if not norm_df.empty and "date" in norm_df.columns:
                    norm_df = norm_df[
                        (norm_df["date"] >= chunk_start) & (norm_df["date"] <= chunk_end)
                    ]
                if norm_df.empty:
                    retry_targets.append(sym)
                    continue

                attempted_chunk_ranges[sym] = (chunk_start, chunk_end)
                try:
                    self._merge_and_save_ohlcv(sym, cached_dfs.get(sym), norm_df)
                    batch_updated += 1
                except Exception as e:
                    logger.warning(f"{sym} のOHLCV Parquet保存に失敗しました: {e}")
                    failed_symbols.append(sym)

        # バッチ成功銘柄には実際に取得したチャンク範囲を記録する
        for sym, chunk_range in attempted_chunk_ranges.items():
            self._attempted_fetch_ranges[sym] = chunk_range

        # 欠損・失敗銘柄を1銘柄ずつ個別リトライし、実際に試みた sym_ranges[sym] を記録する
        for sym in retry_targets:
            sym_start, sym_end = sym_ranges[sym]
            try:
                retry_df = self._get_ohlcv_from_yfinance(sym, sym_start, sym_end)
                if retry_df is not None and not retry_df.empty:
                    self._merge_and_save_ohlcv(sym, cached_dfs.get(sym), retry_df)
                    retried_updated += 1
                else:
                    logger.warning(f"個別リトライでも {sym} のOHLCVデータが取得できませんでした。")
                    failed_symbols.append(sym)
            except Exception as e:
                logger.warning(f"個別リトライ中に {sym} の取得または保存が失敗しました: {e}")
                failed_symbols.append(sym)
            finally:
                self._attempted_fetch_ranges[sym] = (sym_start, sym_end)

        return batch_updated, retried_updated

    def prefetch_ohlcv_batch(
        self,
        symbols: Sequence[str],
        start_date: date,
        end_date: date,
        as_of_date: Optional[date] = None,
        chunk_size: int = 100,
        precheck_market: bool = True,
        benchmark_symbol: str = "1306.T",
    ) -> Dict[str, Any]:
        """複数銘柄の OHLCV データをキャッシュ判定・市場プリチェック付きでチャンク並列バッチ取得する。"""
        if chunk_size <= 0:
            raise ValueError(f"chunk_size は 1 以上の整数を指定してください: {chunk_size}")

        req_start = start_date.date() if isinstance(start_date, datetime) else start_date
        req_end_raw = end_date.date() if isinstance(end_date, datetime) else end_date
        as_of = as_of_date.date() if isinstance(as_of_date, datetime) else as_of_date
        effective_end = min(req_end_raw, as_of) if as_of is not None else req_end_raw

        unique_symbols = list(dict.fromkeys(s for s in symbols if s))
        if not unique_symbols or req_start > effective_end:
            summary = self._build_prefetch_summary(
                total=len(unique_symbols),
                skipped=len(unique_symbols),
            )
            logger.info(
                f"OHLCVバッチプリフェッチ完了（早期終了）: 対象={summary['total']}件, スキップ={summary['skipped']}件"
            )
            return summary

        schedule_expected_start = get_first_trading_day_on_or_after(req_start)
        schedule_expected_end = get_latest_completed_trading_day(ref_date=effective_end)
        if schedule_expected_start > schedule_expected_end:
            summary = self._build_prefetch_summary(
                total=len(unique_symbols),
                skipped=len(unique_symbols),
            )
            logger.info(
                f"OHLCVバッチプリフェッチ完了（対象期間内に完了営業日なし）: "
                f"対象={summary['total']}件, スキップ={summary['skipped']}件"
            )
            return summary

        # 1. 全対象銘柄のローカルキャッシュをロードしてスケジュール基準で分類
        (
            cached_dfs,
            cached_ranges,
            skipped_symbols,
            tail_missing_candidates,
            head_or_full_missing,
        ) = self._classify_cached_symbols(
            unique_symbols,
            schedule_expected_start=schedule_expected_start,
            schedule_expected_end=schedule_expected_end,
        )

        # 2. キャッシュありで end_ok=False の銘柄がある場合のみベンチマーク銘柄で市場最新日を1回プリチェック
        market_latest_date: Optional[date] = None
        has_cached_end_missing = any(
            sym in cached_ranges and cached_ranges[sym][1] < schedule_expected_end
            for sym in (tail_missing_candidates + head_or_full_missing)
        )
        if precheck_market and has_cached_end_missing:
            market_latest_date = self.resolve_latest_completed_trading_day(
                ref_date=effective_end,
                benchmark_symbol=benchmark_symbol,
                use_remote_precheck=True,
            )
            effective_expected_end = min(schedule_expected_end, market_latest_date)
            remaining_tail: List[str] = []
            for sym in tail_missing_candidates:
                if (
                    schedule_expected_start > effective_expected_end
                    or cached_ranges[sym][1] >= effective_expected_end
                ):
                    skipped_symbols.append(sym)
                else:
                    remaining_tail.append(sym)
            tail_missing_symbols = remaining_tail
        else:
            tail_missing_symbols = tail_missing_candidates

        # 3. 取得グループ化（末尾不足グループ / 先頭不足・新規グループ）
        fetch_groups = self._build_prefetch_groups(
            req_start=req_start,
            req_end_raw=req_end_raw,
            cached_ranges=cached_ranges,
            tail_missing_symbols=tail_missing_symbols,
            head_or_full_missing=head_or_full_missing,
        )

        # 4. グループごとにチャンク並列バッチ取得と失敗分の個別リトライを実行
        batch_updated = 0
        retried_updated = 0
        failed_symbols: List[str] = []
        for group_name, sym_ranges in fetch_groups:
            g_batch, g_retry = self._execute_prefetch_group(
                group_name=group_name,
                sym_ranges=sym_ranges,
                cached_dfs=cached_dfs,
                chunk_size=chunk_size,
                failed_symbols=failed_symbols,
            )
            batch_updated += g_batch
            retried_updated += g_retry

        summary = self._build_prefetch_summary(
            total=len(unique_symbols),
            skipped=len(skipped_symbols),
            batch_updated=batch_updated,
            retried_updated=retried_updated,
            failed_symbols=failed_symbols,
            market_latest_date=market_latest_date,
        )
        logger.info(
            f"OHLCVバッチプリフェッチ完了: 対象={summary['total']}件, "
            f"スキップ={summary['skipped']}件, バッチ更新={summary['batch_updated']}件, "
            f"個別リトライ更新={summary['retried_updated']}件, 失敗={summary['failed']}件, "
            f"市場最新完了営業日={market_latest_date}"
        )
        return summary

    def collect_ohlcv_data(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        as_of_date: Optional[date] = None,
        read_only: bool = False,
    ) -> List[OhlcvModel]:
        """
        指定期間のOHLCVデータを収集し、Parquet永続化・差分更新を行い、データを返す。
        as_of_date が指定された場合は、その日付以降のデータを含めない（先読みバイアス防止）。
        read_only=True の場合はローカルParquetキャッシュのみを参照し、通信・保存を一切行わない。
        """
        req_start = start_date.date() if isinstance(start_date, datetime) else start_date
        req_end_raw = end_date.date() if isinstance(end_date, datetime) else end_date
        as_of = as_of_date.date() if isinstance(as_of_date, datetime) else as_of_date
        effective_end = min(req_end_raw, as_of) if as_of is not None else req_end_raw
        if req_start > effective_end:
            return []

        req_end = effective_end
        fetch_start = req_start
        fetch_end = req_end_raw

        parquet_path = f"price/{symbol}.parquet"

        # 1. 既存のParquetデータを列限定でロード（モック互換のため TypeError 時は1引数フォールバック）
        try:
            cached_df = self.storage.load_parquet(parquet_path, columns=OHLCV_READ_COLUMNS)
        except TypeError:
            cached_df = self.storage.load_parquet(parquet_path)
        if cached_df is not None and not cached_df.empty and "date" in cached_df.columns:
            cached_df = self._normalize_date_column(cached_df)
            cached_df = cached_df[cached_df["date"].notna()]

        need_fetch = True
        if read_only:
            need_fetch = False
        elif self._is_cache_sufficient(cached_df, req_start, req_end):
            need_fetch = False
            logger.info(f"{symbol} のOHLCVデータをParquetストレージからロードしました。")
        else:
            expected_start, expected_end = self._resolve_expected_range(req_start, req_end)
            attempted = self._attempted_fetch_ranges.get(symbol)
            if attempted is not None:
                att_start, att_end = attempted
                start_covered = att_start <= expected_start
                if (
                    not start_covered
                    and cached_df is not None
                    and not cached_df.empty
                    and "date" in cached_df.columns
                ):
                    if cached_df["date"].min() <= expected_start and att_start <= cached_df["date"].max():
                        start_covered = True
                if start_covered and att_end >= expected_end:
                    need_fetch = False
                    logger.info(f"{symbol} はバッチ取得試行済みのため再通信をスキップします。")

            if need_fetch and cached_df is not None and not cached_df.empty and "date" in cached_df.columns:
                min_date = cached_df["date"].min()
                max_date = cached_df["date"].max()
                # 不足分がある場合は期間を拡張して再取得しマージ（キャッシュの中抜け防止のため as_of_date で切り詰めない）
                fetch_start = min(req_start, min_date)
                fetch_end = max(req_end_raw, max_date)

        if need_fetch:
            new_df = self._get_ohlcv_from_yfinance(symbol, fetch_start, fetch_end)
            if new_df.empty:
                if cached_df is not None and not cached_df.empty:
                    df_filtered = cached_df[(cached_df["date"] >= req_start) & (cached_df["date"] <= req_end)]
                else:
                    return []
            else:
                if "date" in new_df.columns:
                    new_df = self._normalize_date_column(new_df)
                # 保存し直す場合は既存の dividends / stock_splits 列を失わないよう不足時のみ全列を読み直してマージする
                merge_base_df = cached_df
                if cached_df is not None and not {"dividends", "stock_splits"}.issubset(
                    cached_df.columns
                ):
                    full_cached_df = self.storage.load_parquet(parquet_path)
                    if (
                        full_cached_df is not None
                        and not full_cached_df.empty
                        and "date" in full_cached_df.columns
                    ):
                        full_cached_df = self._normalize_date_column(full_cached_df)
                        full_cached_df = full_cached_df[full_cached_df["date"].notna()]
                        merge_base_df = full_cached_df
                cached_df = self._merge_and_save_ohlcv(symbol, merge_base_df, new_df)
                df_filtered = cached_df[(cached_df["date"] >= req_start) & (cached_df["date"] <= req_end)]
        else:
            if cached_df is None or cached_df.empty or "date" not in cached_df.columns:
                return []
            df_filtered = cached_df[(cached_df["date"] >= req_start) & (cached_df["date"] <= req_end)]

        if df_filtered is None or df_filtered.empty:
            return []

        required_price_cols = ("open", "high", "low", "close")
        if "date" not in df_filtered.columns or not all(
            col in df_filtered.columns for col in required_price_cols
        ):
            return []

        date_series = df_filtered["date"]
        if pd.api.types.is_datetime64_any_dtype(date_series) or any(
            type(v) is not date for v in date_series.tolist()
        ):
            date_series = self._normalize_date_column(df_filtered[["date"]])["date"]

        inf_values = [float("inf"), float("-inf")]
        nan_val = float("nan")
        open_s = pd.to_numeric(df_filtered["open"], errors="coerce").replace(inf_values, nan_val)
        high_s = pd.to_numeric(df_filtered["high"], errors="coerce").replace(inf_values, nan_val)
        low_s = pd.to_numeric(df_filtered["low"], errors="coerce").replace(inf_values, nan_val)
        close_s = pd.to_numeric(df_filtered["close"], errors="coerce").replace(inf_values, nan_val)

        valid_mask = (
            date_series.notna()
            & open_s.notna()
            & high_s.notna()
            & low_s.notna()
            & close_s.notna()
        )
        if not bool(valid_mask.any()):
            return []

        if "volume" in df_filtered.columns:
            vol_s = (
                pd.to_numeric(df_filtered.loc[valid_mask, "volume"], errors="coerce")
                .replace(inf_values, nan_val)
                .fillna(0)
                .round()
                .astype("int64")
            )
            volumes = vol_s.tolist()
        else:
            volumes = [0] * int(valid_mask.sum())

        dates = date_series[valid_mask].tolist()
        opens = open_s[valid_mask].astype("float64").tolist()
        highs = high_s[valid_mask].astype("float64").tolist()
        lows = low_s[valid_mask].astype("float64").tolist()
        closes = close_s[valid_mask].astype("float64").tolist()

        return [
            OhlcvModel.model_construct(
                symbol=symbol,
                date=dt,
                open=op,
                high=hi,
                low=lo,
                close=cl,
                volume=vol,
            )
            for dt, op, hi, lo, cl, vol in zip(
                dates, opens, highs, lows, closes, volumes
            )
        ]

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

    def _download_irbank_file(self, year_suffix: str, fy_type: str, save_path: str, timeout: int = 15):
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
        
        response = session.get(url, headers=headers, allow_redirects=True, timeout=timeout)
        if response.status_code != 200:
            raise Exception(f"IR BANKダウンロード失敗: HTTP {response.status_code}")

        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'wb') as f:
            f.write(response.content)
        logger.info(f"ダウンロード完了: {save_path}")

    def _load_irbank_json(
        self,
        year: int,
        fy_type: str,
        allow_download: bool = True,
        read_only: bool = False,
    ) -> Optional[Dict]:
        """
        指定年度のIR BANKの財務JSONデータをStorageManagerを利用してロードする。
        read_only=True の場合はダウンロードおよび破損ファイルの削除を一切行わない。
        """
        # 2010年以降の場合にサフィックス生成
        if year >= 2010:
            year_suffix = f"00{str(year)[-2:]}"
        else:
            year_suffix = "0000" # 最新
            
        file_name = f"{year_suffix}-{fy_type}"
        if file_name in self._irbank_json_cache:
            return self._irbank_json_cache[file_name]

        file_path = self._get_irbank_file_path(year_suffix, file_name)
        effective_allow_download = allow_download and not read_only
        
        # キャッシュがなければ自動ダウンロード（allow_download=False / read_only=True または失敗記録済みの場合は抑制）
        if not os.path.exists(file_path):
            if not effective_allow_download or file_name in self._irbank_failed_downloads:
                return None
            try:
                self._download_irbank_file(year_suffix, fy_type, file_path)
            except Exception as e:
                logger.error(f"エラー: IR BANKファイル({year_suffix}-{fy_type})取得失敗: {e}")
                self._irbank_failed_downloads.add(file_name)
                return None
                
        # StorageManagerのload_jsonを利用してロード
        try:
            data = self.storage.load_json(file_path)
        except Exception as e:
            logger.error(f"エラー: IR BANKファイル({year_suffix}-{fy_type})のJSON読込失敗: {e}")
            data = None
        if data is None:
            # 破損JSON等でロード失敗した場合は削除し、同一プロセス内の無限再ダウンロードを防止（読取専用時は削除しない）
            if not read_only and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            self._irbank_failed_downloads.add(file_name)
        elif isinstance(data, dict):
            self._irbank_json_cache[file_name] = data
        return data

    def warmup_irbank_cache(
        self,
        fiscal_years: Sequence[int],
        allow_download: bool = True,
    ) -> None:
        """
        並列ワーカー起動前に親プロセス側で指定年度群の BS / PL JSON を事前にロード・ダウンロードする。
        """
        unique_years = sorted({int(y) for y in fiscal_years if not isinstance(y, bool)})
        for year in unique_years:
            self._load_irbank_json(year, self.BALANCE_SHEET_FILE_NAME, allow_download=allow_download)
            self._load_irbank_json(year, self.PROFIT_AND_LOSS_FILE_NAME, allow_download=allow_download)

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

    def _load_irbank_json_with_mode(
        self,
        year: int,
        fy_type: str,
        allow_download: bool,
        read_only: bool,
    ) -> Optional[Dict]:
        """read_only=False 時は既存モック互換のため read_only 引数を省略して _load_irbank_json を呼ぶ。"""
        if read_only:
            return self._load_irbank_json(
                year, fy_type, allow_download=allow_download, read_only=True
            )
        return self._load_irbank_json(year, fy_type, allow_download=allow_download)

    def _resolve_disclosed_entry(
        self,
        code: str,
        target_year: int,
        as_of_date: Optional[date],
        disclosure_lag_days: int,
        bs_by_year: Dict[int, Optional[Dict]],
        pl_by_year: Dict[int, Optional[Dict]],
        allow_download: bool = True,
        read_only: bool = False,
    ) -> Optional[Tuple[int, List[Any], List[Any], date]]:
        """
        指定年度（データ未公開・欠損時や as_of_date 指定時は最大2期遡る）の BS・PL エントリを解決する。
        """
        max_lookback = 3
        effective_allow_download = allow_download and not read_only
        for offset in range(max_lookback):
            candidate_year = target_year - offset
            if candidate_year not in bs_by_year:
                bs_by_year[candidate_year] = self._load_irbank_json_with_mode(
                    candidate_year,
                    self.BALANCE_SHEET_FILE_NAME,
                    allow_download=effective_allow_download,
                    read_only=read_only,
                )
            if candidate_year not in pl_by_year:
                pl_by_year[candidate_year] = self._load_irbank_json_with_mode(
                    candidate_year,
                    self.PROFIT_AND_LOSS_FILE_NAME,
                    allow_download=effective_allow_download,
                    read_only=read_only,
                )

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
        allow_download: bool = True,
        latest_close: Optional[float] = None,
        read_only: bool = False,
    ) -> Optional[FinancialModel]:
        """
        指定年度の財務データを収集し、FinancialModelを構築して返す。
        as_of_date 指定時は決算期末月末日 + disclosure_lag_days で開示判定を行い、
        未開示またはデータ欠損の場合は最大2期分遡って利用可能な年度データを採用する。
        latest_close が指定された場合は内部で OHLCV を再取得せず、その終値を用いて PER / PBR を算出する。
        read_only=True の場合はダウンロードや破損JSON削除・OHLCV更新を行わない。
        """
        code = self._parse_symbol(symbol)
        target_year = fiscal_year if fiscal_year is not None else (as_of_date or date.today()).year
        logger.info(f"実財務データをキャッシュ読込中... {symbol}(コード: {code}), 会計年度: {target_year}")

        effective_allow_download = allow_download and not read_only
        bs_cache: Dict[int, Optional[Dict]] = {}
        pl_cache: Dict[int, Optional[Dict]] = {}
        resolve_kwargs: Dict[str, Any] = {
            "code": code,
            "target_year": target_year,
            "as_of_date": as_of_date,
            "disclosure_lag_days": disclosure_lag_days,
            "bs_by_year": bs_cache,
            "pl_by_year": pl_cache,
            "allow_download": effective_allow_download,
        }
        if read_only:
            resolve_kwargs["read_only"] = True
        resolved = self._resolve_disclosed_entry(**resolve_kwargs)
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
            y_pl = (
                pl_cache.get(y)
                if y in pl_cache
                else self._load_irbank_json_with_mode(
                    y,
                    self.PROFIT_AND_LOSS_FILE_NAME,
                    allow_download=effective_allow_download,
                    read_only=read_only,
                )
            )
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
            resolved_close = latest_close
            if resolved_close is None:
                ohlcv_end_date = as_of_date or date.today()
                ohlcv_kwargs: Dict[str, Any] = {}
                if as_of_date is not None:
                    ohlcv_kwargs["as_of_date"] = as_of_date
                if read_only:
                    ohlcv_kwargs["read_only"] = True
                ohlcv_list = self.collect_ohlcv_data(
                    symbol,
                    date(adopted_year, 1, 1),
                    ohlcv_end_date,
                    **ohlcv_kwargs,
                )
                if ohlcv_list:
                    resolved_close = ohlcv_list[-1].close
            if resolved_close is not None and resolved_close > 0:
                if eps > 0:
                    per = resolved_close / eps
                if bps > 0:
                    pbr = resolved_close / bps
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
        指定年度（最大2期前まで遡及）の BS・PL JSON を一度だけ読み込み、
        全銘柄分の FinancialModel を 4桁コードキーの辞書として高速に返す。
        yfinance による株価取得や IR BANK からの新規ダウンロードは行わない。
        """
        target_year = fiscal_year if fiscal_year is not None else (as_of_date or date.today()).year
        offsets = (0, 1, 2)

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
                allow_download=False,
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
    read_only: bool = False,
) -> List[OhlcvModel]:
    if not read_only:
        if as_of_date is None:
            return data_collector.collect_ohlcv_data(symbol, start_date, end_date)
        return data_collector.collect_ohlcv_data(symbol, start_date, end_date, as_of_date=as_of_date)
    if as_of_date is None:
        return data_collector.collect_ohlcv_data(symbol, start_date, end_date, read_only=True)
    return data_collector.collect_ohlcv_data(
        symbol, start_date, end_date, as_of_date=as_of_date, read_only=True
    )


def prefetch_ohlcv_batch(
    symbols: Sequence[str],
    start_date: date,
    end_date: date,
    as_of_date: Optional[date] = None,
    chunk_size: int = 100,
    precheck_market: bool = True,
    benchmark_symbol: str = "1306.T",
) -> Dict[str, Any]:
    """複数銘柄の OHLCV データを事前にバッチ取得してローカルキャッシュを更新する。"""
    return data_collector.prefetch_ohlcv_batch(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        as_of_date=as_of_date,
        chunk_size=chunk_size,
        precheck_market=precheck_market,
        benchmark_symbol=benchmark_symbol,
    )


def collect_financial_data(
    symbol: str,
    fiscal_year: Optional[int] = None,
    as_of_date: Optional[date] = None,
    disclosure_lag_days: int = 60,
    allow_download: bool = True,
    latest_close: Optional[float] = None,
    read_only: bool = False,
) -> Optional[FinancialModel]:
    if (
        as_of_date is None
        and disclosure_lag_days == 60
        and allow_download
        and latest_close is None
        and not read_only
    ):
        return data_collector.collect_financial_data(symbol, fiscal_year)
    kwargs: Dict[str, Any] = {
        "fiscal_year": fiscal_year,
        "as_of_date": as_of_date,
        "disclosure_lag_days": disclosure_lag_days,
        "allow_download": allow_download,
        "latest_close": latest_close,
    }
    if read_only:
        kwargs["read_only"] = True
    return data_collector.collect_financial_data(symbol, **kwargs)
