from contextlib import redirect_stdout
import io
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import os

from src.common.storage import StorageManager
from src.data_collector.collector import (
    DataCollector,
    OHLCV_READ_COLUMNS,
    collect_ohlcv_data,
    collect_financial_data,
    prefetch_ohlcv_batch,
)
from src.model.data_models import OhlcvModel, FinancialModel

class TestDataCollector(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.collector = DataCollector()
        self.collector.storage = StorageManager(base_dir=self.temp_dir.name)
        self.symbol = "1301.T" # テスト用実コード例
        self.start_date = date(2025, 1, 1)
        self.end_date = date(2025, 1, 5)
        self.mock_df_data = {
            "date": [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 4), date(2025, 1, 5)],
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [105.0, 106.0, 107.0, 108.0, 109.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [104.0, 105.0, 106.0, 107.0, 108.0],
            "volume": [1000, 1100, 1200, 1300, 1400]
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("yfinance.Ticker")
    def test_collect_ohlcv_data_success_and_cached(self, mock_ticker):
        # キャッシュファイルを一時的に回避するため、存在しないパスになるようパッチするか削除する
        cache_path = os.path.join(self.collector.cache_dir, f"ohlcv_{self.symbol}.csv")
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except Exception:
                pass

        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        # カラム名をすべて小文字で定義
        history_df = pd.DataFrame(self.mock_df_data).rename(columns=str.lower)
        history_df = history_df.set_index("date")
        mock_instance.history.return_value = history_df

        ohlcv_list = self.collector.collect_ohlcv_data(self.symbol, self.start_date, self.end_date)
        
        self.assertIsInstance(ohlcv_list, list)
        self.assertEqual(len(ohlcv_list), 5)
        self.assertIsInstance(ohlcv_list[0], OhlcvModel)
        self.assertEqual(ohlcv_list[0].symbol, self.symbol)
        self.assertEqual(ohlcv_list[0].date, date(2025, 1, 1))
        self.assertEqual(ohlcv_list[0].close, 104.0)

        # 二回目の読込はキャッシュから行われる
        with patch.object(self.collector, "_get_ohlcv_from_yfinance") as mock_get:
            ohlcv_list_cached = self.collector.collect_ohlcv_data(self.symbol, self.start_date, self.end_date)
            # yfinanceは呼ばれない
            mock_get.assert_not_called()
            self.assertEqual(len(ohlcv_list_cached), 5)

        # 後始末
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except Exception:
                pass

    @patch("yfinance.Ticker")
    def test_collect_ohlcv_data_empty(self, mock_ticker):
        cache_path = os.path.join(self.collector.cache_dir, f"ohlcv_{self.symbol}.csv")
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except Exception:
                pass

        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.history.return_value = pd.DataFrame()

        ohlcv_list = self.collector.collect_ohlcv_data(self.symbol, self.start_date, self.end_date)
        self.assertEqual(len(ohlcv_list), 0)

    @patch("src.data_collector.collector.DataCollector._load_irbank_json")
    def test_collect_financial_data(self, mock_load_json):
        # バランスシートのモックデータ
        mock_bs_data = {
            "meta": {"item": {"code": ["年度","総資産","純資産","株主資本","利益剰余金","短期借入金","長期借入金","BPS","自己資本比率"]}},
            "item": {
                "1301": ["2023/03", "10000", "5000", "4000", "3000", "1000", "2000", "4000.0", "50.0"]
            }
        }
        # 損益計算書のモックデータ
        mock_pl_data_2023 = {
            "meta": {"item": {"code": ["年度","売上高","営業利益","経常利益","当期純利益","EPS","ROE","ROA"]}},
            "item": {
                "1301": ["2023/03", "20000", "1500", "1600", "1000", "150.0", "15.0", "8.0"]
            }
        }
        # 1年前（2022年）のPLモックデータ (売上高: 18000, 純利益: 900) -> 成長率約 11.1%, 11.1%
        mock_pl_data_2022 = {
            "meta": {"item": {"code": ["年度","売上高","営業利益","経常利益","当期純利益","EPS","ROE","ROA"]}},
            "item": {
                "1301": ["2022/03", "18000", "1300", "1400", "900", "135.0", "14.0", "7.5"]
            }
        }
        # 3年前（2020年）のPLモックデータ (売上高: 15000, 純利益: 800)
        mock_pl_data_2020 = {
            "meta": {"item": {"code": ["年度","売上高","営業利益","経常利益","当期純利益","EPS","ROE","ROA"]}},
            "item": {
                "1301": ["2020/03", "15000", "1100", "1200", "800", "120.0", "12.0", "6.5"]
            }
        }
        # 5年前（2018年）のPLモックデータ (売上高: 12000, 純利益: 600)
        mock_pl_data_2018 = {
            "meta": {"item": {"code": ["年度","売上高","営業利益","経常利益","当期純利益","EPS","ROE","ROA"]}},
            "item": {
                "1301": ["2018/03", "12000", "900", "1000", "600", "90.0", "10.0", "5.5"]
            }
        }

        # ロード処理の戻り値を年度・ファイルタイプごとにモックする
        def side_effect(year, fy_type, allow_download=True):
            if "balance-sheet" in fy_type:
                return mock_bs_data
            elif "profit-and-loss" in fy_type:
                if year == 2023:
                    return mock_pl_data_2023
                elif year == 2022:
                    return mock_pl_data_2022
                elif year == 2020:
                    return mock_pl_data_2020
                elif year == 2018:
                    return mock_pl_data_2018
            return None

        mock_load_json.side_effect = side_effect

        # 株価データのモックを同時に差し込み、PER, PBRも計算
        with patch.object(self.collector, "collect_ohlcv_data") as mock_ohlcv:
            mock_ohlcv.return_value = [OhlcvModel(symbol="1301.T", date=date(2023, 3, 31), open=1500, high=1510, low=1490, close=1500.0, volume=1000)]
            
            financial_data = self.collector.collect_financial_data("1301.T", 2023)
            
            self.assertIsNotNone(financial_data)
            self.assertEqual(financial_data.symbol, "1301.T")
            self.assertEqual(financial_data.eps, 150.0)
            self.assertEqual(financial_data.bps, 4000.0)
            self.assertEqual(financial_data.roe, 15.0)
            self.assertEqual(financial_data.roa, 8.0)
            self.assertEqual(financial_data.revenue, 20000.0)
            self.assertEqual(financial_data.operating_profit, 1500.0)
            self.assertEqual(financial_data.net_profit, 1000.0)
            
            # 成長率の検証
            self.assertAlmostEqual(financial_data.revenue_growth, 11.1111111)
            self.assertAlmostEqual(financial_data.net_profit_growth, 11.1111111)
            # CAGR 3年平均: (20000 / 15000)**(1/3) - 1 => 10.06%
            self.assertAlmostEqual(financial_data.revenue_growth_3y_avg, 10.0642416, places=4)
            # CAGR 5年平均: (20000 / 12000)**(1/5) - 1 => 10.76%
            self.assertAlmostEqual(financial_data.revenue_growth_5y_avg, 10.756641, places=4)

            # PER/PBR の検証 (株価1500.0 / eps 150 = 10.0, 株価1500.0 / bps 4000 = 0.375)
            self.assertEqual(financial_data.per, 10.0)
            self.assertEqual(financial_data.pbr, 0.375)

    @patch("src.data_collector.collector.data_collector")
    def test_module_level_collect_ohlcv_data(self, mock_data_collector):
        mock_data_collector.collect_ohlcv_data.return_value = [MagicMock(spec=OhlcvModel)]
        result = collect_ohlcv_data(self.symbol, self.start_date, self.end_date)
        mock_data_collector.collect_ohlcv_data.assert_called_once_with(self.symbol, self.start_date, self.end_date)
        self.assertIsInstance(result, list)

    @patch("src.data_collector.collector.data_collector")
    def test_module_level_collect_financial_data(self, mock_data_collector):
        mock_data_collector.collect_financial_data.return_value = MagicMock(spec=FinancialModel)
        result = collect_financial_data(self.symbol, 2025)
        mock_data_collector.collect_financial_data.assert_called_once_with(self.symbol, 2025)
        self.assertIsNotNone(result)

    def test_get_irbank_file_path_priority(self):
        """data/financial/ が最優先で参照され、未存在時も data/financial/ が返る"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            collector = DataCollector()
            collector.storage = StorageManager(base_dir=tmp_path / "data")
            collector.local_irbank_dir = str(tmp_path / "cache_irbank")
            collector.user_irbank_dir = str(tmp_path / "user_irbank")
            os.makedirs(collector.local_irbank_dir, exist_ok=True)
            os.makedirs(collector.user_irbank_dir, exist_ok=True)

            file_name = "0025-fy-balance-sheet.json"
            fin_file = collector.storage.financial_dir / file_name
            local_file = Path(collector.local_irbank_dir) / file_name
            user_file = Path(collector.user_irbank_dir) / file_name

            # どこにもない場合は data/financial/ のパスを返す（ダウンロード保存先）
            self.assertEqual(collector._get_irbank_file_path("0025", file_name), str(fin_file))

            # user のみ存在
            user_file.write_text("{}", encoding="utf-8")
            self.assertEqual(collector._get_irbank_file_path("0025", file_name), str(user_file))

            # local が追加されれば local 優先
            local_file.write_text("{}", encoding="utf-8")
            self.assertEqual(collector._get_irbank_file_path("0025", file_name), str(local_file))

            # data/financial/ が追加されれば最優先
            fin_file.write_text("{}", encoding="utf-8")
            self.assertEqual(collector._get_irbank_file_path("0025", file_name), str(fin_file))

    def test_collect_ohlcv_data_as_of_date_prevents_leakage(self):
        """as_of_date を超える OHLCV データが返却されないことを検証"""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = DataCollector()
            collector.storage = StorageManager(base_dir=Path(tmpdir))

            full_df = pd.DataFrame({
                "date": [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6)],
                "open": [100.0, 101.0, 102.0, 105.0],
                "high": [105.0, 106.0, 107.0, 110.0],
                "low": [99.0, 100.0, 101.0, 104.0],
                "close": [104.0, 105.0, 106.0, 109.0],
                "volume": [1000, 1100, 1200, 1500],
            })
            collector.storage.save_parquet(full_df, f"price/{self.symbol}.parquet")

            # end_date が未来でも as_of_date=2025-01-03 までしか返らない
            res = collector.collect_ohlcv_data(
                self.symbol,
                date(2025, 1, 1),
                date(2025, 1, 10),
                as_of_date=date(2025, 1, 3),
            )
            self.assertEqual([r.date for r in res], [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)])

            # start_date > as_of_date なら空リスト
            res_empty = collector.collect_ohlcv_data(
                self.symbol,
                date(2025, 1, 5),
                date(2025, 1, 10),
                as_of_date=date(2025, 1, 3),
            )
            self.assertEqual(res_empty, [])

    @patch("src.data_collector.collector.DataCollector._load_irbank_json")
    def test_collect_financial_data_as_of_date_disclosure_lag(self, mock_load_json):
        """as_of_date と開示ラグ（60日）により未開示決算が前年度へフォールバックされる"""
        bs_2025 = {"item": {"7203": ["2025/03", "90000", "0", "0", "0", "0", "0", "3000.0", "45.0"]}}
        pl_2025 = {"item": {"7203": ["2025/03", "50000", "5000", "5200", "3500", "250.0", "12.0", "6.0"]}}
        bs_2024 = {"item": {"7203": ["2024/03", "80000", "0", "0", "0", "0", "0", "2700.0", "42.0"]}}
        pl_2024 = {"item": {"7203": ["2024/03", "45000", "4200", "4300", "3000", "210.0", "11.0", "5.5"]}}

        def side_effect(year, fy_type, allow_download=True):
            if year == 2025:
                if "balance-sheet" in fy_type:
                    return bs_2025
                if "profit-and-loss" in fy_type:
                    return pl_2025
            if year == 2024:
                if "balance-sheet" in fy_type:
                    return bs_2024
                if "profit-and-loss" in fy_type:
                    return pl_2024
            return None

        mock_load_json.side_effect = side_effect

        with patch.object(self.collector, "collect_ohlcv_data") as mock_ohlcv:
            mock_ohlcv.return_value = [
                OhlcvModel(symbol="7203.T", date=date(2025, 5, 1), open=2500, high=2550, low=2480, close=2520.0, volume=10000)
            ]
            # 2025/03/31 + 60日 = 2025/05/30 -> 2025/05/15 時点では未開示のため 2024/03 期を採用
            fin_before = self.collector.collect_financial_data(
                "7203.T",
                fiscal_year=2025,
                as_of_date=date(2025, 5, 15),
                disclosure_lag_days=60,
            )
            self.assertIsNotNone(fin_before)
            self.assertEqual(fin_before.fiscal_date, date(2024, 3, 31))
            self.assertEqual(fin_before.revenue, 45000.0)
            self.assertEqual(fin_before.total_assets, 80000.0)
            self.assertEqual(fin_before.equity_ratio, 42.0)
            mock_ohlcv.assert_called_with("7203.T", date(2024, 1, 1), date(2025, 5, 15), as_of_date=date(2025, 5, 15))

            # 2025/06/01 時点では 2025/03 期が開示済み
            fin_after = self.collector.collect_financial_data(
                "7203.T",
                fiscal_year=2025,
                as_of_date=date(2025, 6, 1),
                disclosure_lag_days=60,
            )
            self.assertIsNotNone(fin_after)
            self.assertEqual(fin_after.fiscal_date, date(2025, 3, 31))
            self.assertEqual(fin_after.revenue, 50000.0)
            self.assertEqual(fin_after.total_assets, 90000.0)
            self.assertEqual(fin_after.equity_ratio, 45.0)

    @patch("src.data_collector.collector.DataCollector._load_irbank_json")
    def test_load_financial_snapshot(self, mock_load_json):
        """load_financial_snapshot が通信なしで一括ロードし、開示ラグを反映する"""
        bs_2025 = {
            "item": {
                "7203": ["2025/03", "90000", "0", "0", "0", "0", "0", "3000.0", "45.0"],
                "9984": ["2025/02", "50000", "0", "0", "0", "0", "0", "2000.0", "30.0"],
            }
        }
        pl_2025 = {
            "item": {
                "7203": ["2025/03", "50000", "5000", "5200", "3500", "250.0", "12.0", "6.0"],
                "9984": ["2025/02", "30000", "2000", "2100", "1200", "100.0", "8.0", "4.0"],
            }
        }
        bs_2024 = {
            "item": {
                "7203": ["2024/03", "80000", "0", "0", "0", "0", "0", "2700.0", "42.0"],
            }
        }
        pl_2024 = {
            "item": {
                "7203": ["2024/03", "45000", "4200", "4300", "3000", "210.0", "11.0", "5.5"],
            }
        }

        def side_effect(year, fy_type, allow_download=True):
            if year == 2025:
                if "balance-sheet" in fy_type:
                    return bs_2025
                if "profit-and-loss" in fy_type:
                    return pl_2025
            if year == 2024:
                if "balance-sheet" in fy_type:
                    return bs_2024
                if "profit-and-loss" in fy_type:
                    return pl_2024
            return None

        mock_load_json.side_effect = side_effect

        with patch.object(self.collector, "collect_ohlcv_data") as mock_ohlcv:
            # 2025/05/15 時点: 2025/02 (2/28+60日=4/29) は開示済み、2025/03 (3/31+60日=5/30) は未開示
            snapshot = self.collector.load_financial_snapshot(
                fiscal_year=2025,
                as_of_date=date(2025, 5, 15),
                disclosure_lag_days=60,
            )
            mock_ohlcv.assert_not_called()
            self.assertIn("7203", snapshot)
            self.assertIn("9984", snapshot)
            self.assertEqual(snapshot["7203"].fiscal_date, date(2024, 3, 31))
            self.assertEqual(snapshot["7203"].revenue, 45000.0)
            self.assertEqual(snapshot["9984"].fiscal_date, date(2025, 2, 28))
            self.assertEqual(snapshot["9984"].revenue, 30000.0)

    def test_parse_symbol_lowercase_alpha(self):
        """小文字英字を含む銘柄コードも大文字4桁として抽出される"""
        self.assertEqual(self.collector._parse_symbol("130a.T"), "130A")
        self.assertEqual(self.collector._parse_symbol("130a"), "130A")

    def test_load_financial_snapshot_no_download_when_missing(self):
        """未存在の年度に対して _download_irbank_file が呼ばれないことを検証"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            collector = DataCollector()
            collector.storage = StorageManager(base_dir=tmp_path / "data")
            collector.local_irbank_dir = str(tmp_path / "cache_irbank")
            collector.user_irbank_dir = str(tmp_path / "user_irbank")
            os.makedirs(collector.local_irbank_dir, exist_ok=True)
            os.makedirs(collector.user_irbank_dir, exist_ok=True)

            with patch.object(collector, "_download_irbank_file") as mock_download:
                snapshot = collector.load_financial_snapshot(
                    fiscal_year=2099,
                    as_of_date=date(2099, 6, 1),
                    disclosure_lag_days=60,
                )
                mock_download.assert_not_called()
                self.assertEqual(snapshot, {})

    def test_collect_ohlcv_data_as_of_date_does_not_truncate_fetch_range(self):
        """as_of_date 指定時でもフェッチ範囲は as_of_date で切り詰められずキャッシュ中抜けを防ぐ"""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = DataCollector()
            collector.storage = StorageManager(base_dir=Path(tmpdir))

            fetched_df = pd.DataFrame({
                "date": [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 6), date(2025, 1, 10)],
                "open": [100.0, 101.0, 105.0, 108.0],
                "high": [105.0, 106.0, 110.0, 112.0],
                "low": [99.0, 100.0, 104.0, 107.0],
                "close": [104.0, 105.0, 109.0, 111.0],
                "volume": [1000, 1100, 1500, 1600],
            })

            with patch.object(collector, "_get_ohlcv_from_yfinance", return_value=fetched_df) as mock_yf:
                res = collector.collect_ohlcv_data(
                    self.symbol,
                    date(2025, 1, 1),
                    date(2025, 1, 10),
                    as_of_date=date(2025, 1, 3),
                )
                mock_yf.assert_called_once_with(self.symbol, date(2025, 1, 1), date(2025, 1, 10))
                self.assertEqual([r.date for r in res], [date(2025, 1, 1), date(2025, 1, 2)])

    def test_load_irbank_json_negative_cache(self):
        """ダウンロード失敗時はネガティブキャッシュに記録され、2回目以降 _download_irbank_file が再実行されない"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            collector = DataCollector()
            collector.storage = StorageManager(base_dir=tmp_path / "data")
            collector.local_irbank_dir = str(tmp_path / "cache_irbank")
            collector.user_irbank_dir = str(tmp_path / "user_irbank")
            os.makedirs(collector.local_irbank_dir, exist_ok=True)
            os.makedirs(collector.user_irbank_dir, exist_ok=True)

            with patch.object(collector, "_download_irbank_file", side_effect=Exception("HTTP 404")) as mock_dl:
                res1 = collector._load_irbank_json(2098, collector.BALANCE_SHEET_FILE_NAME)
                res2 = collector._load_irbank_json(2098, collector.BALANCE_SHEET_FILE_NAME)
                self.assertIsNone(res1)
                self.assertIsNone(res2)
                mock_dl.assert_called_once()
                self.assertIn("0098-fy-balance-sheet.json", collector._irbank_failed_downloads)

    def test_load_irbank_json_corrupted_negative_cache(self):
        """ダウンロードしたファイルが破損JSONだった場合、削除されてネガティブキャッシュに登録され2回目で再ダウンロードされない"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            collector = DataCollector()
            collector.storage = StorageManager(base_dir=tmp_path / "data")
            collector.local_irbank_dir = str(tmp_path / "cache_irbank")
            collector.user_irbank_dir = str(tmp_path / "user_irbank")
            os.makedirs(collector.local_irbank_dir, exist_ok=True)
            os.makedirs(collector.user_irbank_dir, exist_ok=True)

            def write_corrupted(_year_suffix: str, _fy_type: str, save_path: str):
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                Path(save_path).write_text("{corrupted json", encoding="utf-8")

            with patch.object(collector, "_download_irbank_file", side_effect=write_corrupted) as mock_dl:
                res1 = collector._load_irbank_json(2099, collector.BALANCE_SHEET_FILE_NAME)
                res2 = collector._load_irbank_json(2099, collector.BALANCE_SHEET_FILE_NAME)
                self.assertIsNone(res1)
                self.assertIsNone(res2)
                mock_dl.assert_called_once()
                self.assertIn("0099-fy-balance-sheet.json", collector._irbank_failed_downloads)
                expected_path = Path(collector._get_irbank_file_path("0099", "0099-fy-balance-sheet.json"))
                self.assertFalse(expected_path.exists())

    def test_load_irbank_json_in_memory_cache(self):
        """一度ロードした JSON はインメモリキャッシュされ、2回目で storage.load_json が再実行されない"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            collector = DataCollector()
            collector.storage = StorageManager(base_dir=tmp_path / "data")
            collector.local_irbank_dir = str(tmp_path / "cache_irbank")
            collector.user_irbank_dir = str(tmp_path / "user_irbank")
            os.makedirs(collector.local_irbank_dir, exist_ok=True)
            os.makedirs(collector.user_irbank_dir, exist_ok=True)

            sample_data = {"item": {"7203": ["2025/03", "100"]}}
            file_path = collector.storage.financial_dir / "0025-fy-balance-sheet.json"
            collector.storage.save_json(sample_data, file_path)

            with patch.object(collector.storage, "load_json", wraps=collector.storage.load_json) as mock_load:
                res1 = collector._load_irbank_json(2025, collector.BALANCE_SHEET_FILE_NAME)
                res2 = collector._load_irbank_json(2025, collector.BALANCE_SHEET_FILE_NAME)
                self.assertEqual(res1, sample_data)
                self.assertEqual(res2, sample_data)
                mock_load.assert_called_once()

    def test_collect_financial_data_allow_download_false(self):
        """allow_download=False の場合、未存在ファイルのダウンロードを試みない"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            collector = DataCollector()
            collector.storage = StorageManager(base_dir=tmp_path / "data")
            collector.local_irbank_dir = str(tmp_path / "cache_irbank")
            collector.user_irbank_dir = str(tmp_path / "user_irbank")
            os.makedirs(collector.local_irbank_dir, exist_ok=True)
            os.makedirs(collector.user_irbank_dir, exist_ok=True)

            with patch.object(collector, "_download_irbank_file") as mock_dl:
                res = collector.collect_financial_data("7203.T", fiscal_year=2097, allow_download=False)
                self.assertIsNone(res)
                mock_dl.assert_not_called()

    @patch("src.data_collector.collector.DataCollector._load_irbank_json")
    def test_collect_financial_data_fallback_without_as_of_date(self, mock_load_json):
        """as_of_date=None でも最新年度データが欠損していれば最大2期前まで遡って取得できる"""
        bs_2025 = {"item": {"7203": ["2025/03", "90000", "0", "0", "0", "0", "0", "3000.0", "45.0"]}}
        pl_2025 = {"item": {"7203": ["2025/03", "50000", "5000", "5200", "3500", "250.0", "12.0", "6.0"]}}

        def side_effect(year, fy_type, allow_download=True):
            if year == 2025:
                if "balance-sheet" in fy_type:
                    return bs_2025
                if "profit-and-loss" in fy_type:
                    return pl_2025
            return None

        mock_load_json.side_effect = side_effect

        with patch.object(self.collector, "collect_ohlcv_data", return_value=[]):
            fin = self.collector.collect_financial_data("7203.T", fiscal_year=2026, as_of_date=None)
            self.assertIsNotNone(fin)
            self.assertEqual(fin.fiscal_date, date(2025, 3, 31))
            self.assertEqual(fin.revenue, 50000.0)

    def test_load_financial_snapshot_fallback_when_as_of_date_is_none(self):
        """as_of_date=None でも load_financial_snapshot が前年度データへフォールバックし、ダウンロードは行わない"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            collector = DataCollector()
            collector.storage = StorageManager(base_dir=tmp_path / "data")
            collector.local_irbank_dir = str(tmp_path / "cache_irbank")
            collector.user_irbank_dir = str(tmp_path / "user_irbank")
            os.makedirs(collector.local_irbank_dir, exist_ok=True)
            os.makedirs(collector.user_irbank_dir, exist_ok=True)

            bs_2025 = {"item": {"7203": ["2025/03", "90000", "0", "0", "0", "0", "0", "3000.0", "45.0"]}}
            pl_2025 = {"item": {"7203": ["2025/03", "50000", "5000", "5200", "3500", "250.0", "12.0", "6.0"]}}
            collector.storage.save_json(bs_2025, collector.storage.financial_dir / "0025-fy-balance-sheet.json")
            collector.storage.save_json(pl_2025, collector.storage.financial_dir / "0025-fy-profit-and-loss.json")

            with patch.object(collector, "_download_irbank_file") as mock_dl:
                snap = collector.load_financial_snapshot(fiscal_year=2026, as_of_date=None)
                mock_dl.assert_not_called()
                self.assertIn("7203", snap)
                self.assertEqual(snap["7203"].fiscal_date, date(2025, 3, 31))
                self.assertEqual(snap["7203"].revenue, 50000.0)

    @patch("src.data_collector.collector.DataCollector._load_irbank_json")
    def test_collect_financial_data_with_latest_close_skips_ohlcv(self, mock_load_json):
        """latest_close 指定時は collect_ohlcv_data を呼ばず PER / PBR を算出する"""
        bs_2025 = {"item": {"7203": ["2025/03", "90000", "0", "0", "0", "0", "0", "2000.0", "45.0"]}}
        pl_2025 = {"item": {"7203": ["2025/03", "50000", "5000", "5200", "3500", "200.0", "12.0", "6.0"]}}

        def side_effect(year, fy_type, allow_download=True):
            if year == 2025:
                if "balance-sheet" in fy_type:
                    return bs_2025
                if "profit-and-loss" in fy_type:
                    return pl_2025
            return None

        mock_load_json.side_effect = side_effect

        with patch.object(self.collector, "collect_ohlcv_data") as mock_ohlcv:
            fin = self.collector.collect_financial_data(
                "7203.T",
                fiscal_year=2025,
                as_of_date=date(2025, 6, 1),
                latest_close=3000.0,
            )
            mock_ohlcv.assert_not_called()
            self.assertIsNotNone(fin)
            self.assertAlmostEqual(fin.per, 15.0)  # 3000.0 / 200.0
            self.assertAlmostEqual(fin.pbr, 1.5)   # 3000.0 / 2000.0

            # latest_close <= 0 (0.0 および負値) の場合も collect_ohlcv_data を呼ばず 0.0 フォールバック
            fin_zero = self.collector.collect_financial_data(
                "7203.T",
                fiscal_year=2025,
                as_of_date=date(2025, 6, 1),
                latest_close=0.0,
            )
            mock_ohlcv.assert_not_called()
            self.assertIsNotNone(fin_zero)
            self.assertEqual(fin_zero.per, 0.0)
            self.assertEqual(fin_zero.pbr, 0.0)

            fin_negative = self.collector.collect_financial_data(
                "7203.T",
                fiscal_year=2025,
                as_of_date=date(2025, 6, 1),
                latest_close=-100.0,
            )
            mock_ohlcv.assert_not_called()
            self.assertIsNotNone(fin_negative)
            self.assertEqual(fin_negative.per, 0.0)
            self.assertEqual(fin_negative.pbr, 0.0)

    @patch("src.data_collector.collector.data_collector")
    def test_module_level_collect_financial_data_passes_latest_close(self, mock_data_collector):
        """モジュールレベル collect_financial_data が latest_close を引き継ぐ"""
        mock_data_collector.collect_financial_data.return_value = MagicMock(spec=FinancialModel)
        result = collect_financial_data(self.symbol, 2025, latest_close=1500.0)
        mock_data_collector.collect_financial_data.assert_called_once_with(
            self.symbol,
            fiscal_year=2025,
            as_of_date=None,
            disclosure_lag_days=60,
            allow_download=True,
            latest_close=1500.0,
        )
        self.assertIsNotNone(result)

    @patch("src.data_collector.collector.data_collector._load_irbank_json")
    def test_module_level_collect_financial_data_zero_latest_close_skips_ohlcv(self, mock_load_json):
        """モジュールレベル collect_financial_data(..., latest_close=0.0) でも collect_ohlcv_data を呼ばない"""
        bs_2025 = {"item": {"7203": ["2025/03", "90000", "0", "0", "0", "0", "0", "2000.0", "45.0"]}}
        pl_2025 = {"item": {"7203": ["2025/03", "50000", "5000", "5200", "3500", "200.0", "12.0", "6.0"]}}
        def _side_effect_module(year, fy_type, allow_download=True):
            if year == 2025:
                if "balance-sheet" in fy_type:
                    return bs_2025
                if "profit-and-loss" in fy_type:
                    return pl_2025
            return None

        mock_load_json.side_effect = _side_effect_module

        with patch("src.data_collector.collector.data_collector.collect_ohlcv_data") as mock_ohlcv:
            fin = collect_financial_data("7203.T", fiscal_year=2025, latest_close=0.0)

        mock_ohlcv.assert_not_called()
        self.assertIsNotNone(fin)
        self.assertEqual(fin.per, 0.0)
        self.assertEqual(fin.pbr, 0.0)

    @staticmethod
    def _build_price_df(dates_list, base_price=1000.0):
        return pd.DataFrame({
            "date": dates_list,
            "open": [base_price + i for i in range(len(dates_list))],
            "high": [base_price + i + 10.0 for i in range(len(dates_list))],
            "low": [base_price + i - 10.0 for i in range(len(dates_list))],
            "close": [base_price + i + 5.0 for i in range(len(dates_list))],
            "volume": [10000 + i * 100 for i in range(len(dates_list))],
        })

    @staticmethod
    def _build_yf_multiindex_df(symbol_rows: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """yf.download(group_by='ticker') 形式の MultiIndex DataFrame を生成する。"""
        frames = {}
        for sym, df in symbol_rows.items():
            sub = df.copy()
            sub["Date"] = pd.to_datetime(sub["date"])
            sub = sub.set_index("Date")
            sub = sub.rename(columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            })[["Open", "High", "Low", "Close", "Volume"]]
            frames[sym] = sub
        return pd.concat(frames, axis=1)

    @patch("yfinance.Ticker")
    def test_get_ohlcv_from_yfinance_uses_exclusive_end_plus_one_day(self, mock_ticker):
        """_get_ohlcv_from_yfinance が end_date + 1日を yfinance へ渡し当日足を落とさない"""
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        raw = pd.DataFrame(
            {
                "Open": [100.0, 101.0, 102.0],
                "High": [105.0, 106.0, 107.0],
                "Low": [99.0, 100.0, 101.0],
                "Close": [104.0, 105.0, 106.0],
                "Volume": [1000, None, 1200],
            },
            index=pd.to_datetime(["2025-01-06", "2025-01-07", "2025-01-08"]),
        )
        # 一部 NaN 価格行が混入しても除去され、2025-01-09 の余分な行は max_date で除外される
        extra = pd.DataFrame(
            {
                "Open": [None, 103.0],
                "High": [110.0, 108.0],
                "Low": [98.0, 102.0],
                "Close": [105.0, 107.0],
                "Volume": [500, 1300],
            },
            index=pd.to_datetime(["2025-01-07", "2025-01-09"]),
        )
        mock_instance.history.return_value = pd.concat([raw, extra])

        df = self.collector._get_ohlcv_from_yfinance("7203.T", date(2025, 1, 6), date(2025, 1, 8))
        mock_instance.history.assert_called_once_with(start="2025-01-06", end="2025-01-09")
        self.assertEqual(list(df["date"]), [date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 8)])
        self.assertEqual(df.loc[df["date"] == date(2025, 1, 7), "volume"].iloc[0], 0)

    def test_is_cache_sufficient_holiday_margin_and_intraday_skip(self):
        """開始・終了日の休場マージンおよび場中カットオフ時にキャッシュ十分と判定して再通信しない"""
        # 2025/1/1(水・祝)〜1/5(日)は休場、最初の営業日は 1/6(月)
        # 2025/1/10(金)までキャッシュがあれば、1/12(日)を終了日指定しても十分と判定される
        cached_df = self._build_price_df([
            date(2025, 1, 6),
            date(2025, 1, 7),
            date(2025, 1, 8),
            date(2025, 1, 9),
            date(2025, 1, 10),
        ])
        self.collector.storage.save_parquet(cached_df, "price/7203.T.parquet")

        self.assertTrue(
            self.collector._is_cache_sufficient(
                cached_df,
                req_start=date(2025, 1, 1),
                req_end=date(2025, 1, 12),
            )
        )
        with patch.object(self.collector, "_get_ohlcv_from_yfinance") as mock_yf:
            res = self.collector.collect_ohlcv_data("7203.T", date(2025, 1, 1), date(2025, 1, 12))
            mock_yf.assert_not_called()
            self.assertEqual(len(res), 5)

        # 場中（例: 2025-01-14 火曜 10:00 JST -> 完了営業日は 2025-01-10 金曜[1/13成人の日]）
        with patch(
            "src.data_collector.collector.get_latest_completed_trading_day",
            return_value=date(2025, 1, 10),
        ):
            self.assertTrue(
                self.collector._is_cache_sufficient(
                    cached_df,
                    req_start=date(2025, 1, 6),
                    req_end=date(2025, 1, 14),
                )
            )

    def test_prefetch_ohlcv_batch_market_precheck_moves_tail_missing_to_skipped(self):
        """1306.T プリチェックで実市場最新日がキャッシュ済み末尾と一致した場合、tail_missing が skipped に移る"""
        # 2025-01-10(金)までキャッシュ済み、要求は 2025-01-14(火)まで（スケジュール上は 1/14 が営業日）
        cached_df = self._build_price_df([date(2025, 1, 6), date(2025, 1, 10)])
        self.collector.storage.save_parquet(cached_df, "price/7203.T.parquet")

        benchmark_df = pd.DataFrame(
            {
                "Open": [2800.0],
                "High": [2820.0],
                "Low": [2790.0],
                "Close": [2810.0],
                "Volume": [100000],
            },
            index=pd.to_datetime(["2025-01-10"]),
        )
        mock_ticker_inst = MagicMock()
        mock_ticker_inst.history.return_value = benchmark_df

        with patch("yfinance.Ticker", return_value=mock_ticker_inst) as mock_ticker_cls, \
             patch("yfinance.download") as mock_download:
            summary = self.collector.prefetch_ohlcv_batch(
                symbols=["7203.T"],
                start_date=date(2025, 1, 6),
                end_date=date(2025, 1, 14),
                precheck_market=True,
                benchmark_symbol="1306.T",
            )

        mock_ticker_cls.assert_called_once_with("1306.T")
        mock_download.assert_not_called()
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["batch_updated"], 0)
        self.assertEqual(summary["market_latest_date"], date(2025, 1, 10))
        cached_entry = self.collector._market_latest_date_cache[(date(2025, 1, 14), "1306.T")]
        self.assertEqual(cached_entry[0], date(2025, 1, 10))

    def test_prefetch_ohlcv_batch_skips_precheck_when_no_cache_or_all_skipped(self):
        """全銘柄キャッシュなし（新規取得のみ）または全銘柄スキップ時は 1306.T プリチェックを実行しない"""
        # 1. 新規取得のみ（キャッシュなし）
        dl_df = self._build_yf_multiindex_df({
            "7203.T": self._build_price_df([date(2025, 1, 6), date(2025, 1, 7)]),
        })
        with patch.object(self.collector, "resolve_latest_completed_trading_day") as mock_precheck, \
             patch("yfinance.download", return_value=dl_df) as mock_download:
            summary_new = self.collector.prefetch_ohlcv_batch(
                symbols=["7203.T", "7203.T"],  # 重複排除も検証
                start_date=date(2025, 1, 6),
                end_date=date(2025, 1, 7),
                precheck_market=True,
            )
        mock_precheck.assert_not_called()
        mock_download.assert_called_once()
        self.assertEqual(summary_new["total"], 1)
        self.assertEqual(summary_new["batch_updated"], 1)

        # 2. 既にキャッシュが十分な状態（全銘柄スキップ）
        with patch.object(self.collector, "resolve_latest_completed_trading_day") as mock_precheck, \
             patch("yfinance.download") as mock_download:
            summary_skip = self.collector.prefetch_ohlcv_batch(
                symbols=["7203.T"],
                start_date=date(2025, 1, 6),
                end_date=date(2025, 1, 7),
                precheck_market=True,
            )
        mock_precheck.assert_not_called()
        mock_download.assert_not_called()
        self.assertEqual(summary_skip["skipped"], 1)

    def test_prefetch_ohlcv_batch_chunks_case_insensitive_and_single_layer(self):
        """チャンク分割・大文字小文字ティッカー一致・単一ティッカー単層DF・as_of_date非切り詰めを検証する"""
        # 3銘柄を chunk_size=2 で2チャンク（[130a.T, 7203.T], [9984.T]）に分割
        chunk1_df = self._build_yf_multiindex_df({
            # yf.download がティッカーを大文字化して返すケース
            "130A.T": self._build_price_df([date(2025, 1, 6), date(2025, 1, 10)]),
            "7203.T": self._build_price_df([date(2025, 1, 6), date(2025, 1, 10)], base_price=2000.0),
        })
        # 単一ティッカーチャンクで単層 DataFrame が返るケース
        chunk2_df = self._build_price_df([date(2025, 1, 6), date(2025, 1, 10)], base_price=3000.0)
        chunk2_df["Date"] = pd.to_datetime(chunk2_df["date"])
        chunk2_df = chunk2_df.set_index("Date")[["open", "high", "low", "close", "volume"]]
        chunk2_df.columns = ["Open", "High", "Low", "Close", "Volume"]

        with patch("yfinance.download", side_effect=[chunk1_df, chunk2_df]) as mock_download:
            summary = self.collector.prefetch_ohlcv_batch(
                symbols=["130a.T", "7203.T", "9984.T"],
                start_date=date(2025, 1, 6),
                end_date=date(2025, 1, 10),
                as_of_date=date(2025, 1, 8),  # 取得範囲は end_date=2025-01-10 を切り詰めない
                chunk_size=2,
                precheck_market=False,
            )

        self.assertEqual(mock_download.call_count, 2)
        first_call_kwargs = mock_download.call_args_list[0].kwargs
        self.assertEqual(first_call_kwargs["tickers"], ["130a.T", "7203.T"])
        self.assertEqual(first_call_kwargs["start"], "2025-01-06")
        self.assertEqual(first_call_kwargs["end"], "2025-01-11")
        self.assertTrue(first_call_kwargs["actions"])
        self.assertTrue(first_call_kwargs["threads"])
        self.assertEqual(first_call_kwargs["group_by"], "ticker")
        self.assertFalse(first_call_kwargs["progress"])

        self.assertEqual(summary["batch_updated"], 3)
        self.assertEqual(summary["failed"], 0)
        for sym in ("130a.T", "7203.T", "9984.T"):
            saved = self.collector.storage.load_parquet(f"price/{sym}.parquet")
            self.assertIsNotNone(saved)
            self.assertEqual(len(saved), 2)
            # 2025-01-10 まで保存されており as_of_date=1/8 で中抜けしていない
            self.assertEqual(pd.to_datetime(saved["date"]).dt.date.max(), date(2025, 1, 10))

    def test_prefetch_ohlcv_batch_retry_on_missing_and_error_and_skip_refetch(self):
        """バッチ欠損/例外時の個別リトライ（成功・失敗継続）と _attempted_fetch_ranges による再通信抑止を検証"""
        # 7203.T はバッチで全NaN（有効行0件）、6758.T はティッカー欠損、9984.T はバッチ成功
        nan_df = pd.DataFrame(
            {"Open": [None], "High": [None], "Low": [None], "Close": [None], "Volume": [None]},
            index=pd.to_datetime(["2025-01-06"]),
        )
        dl_df = pd.concat(
            {
                "9984.T": pd.DataFrame(
                    {"Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [104.0], "Volume": [1000]},
                    index=pd.to_datetime(["2025-01-06"]),
                ),
                "7203.T": nan_df,
            },
            axis=1,
        )

        retry_7203_df = self._build_price_df([date(2025, 1, 6), date(2025, 1, 7)])

        def retry_side_effect(sym, s_date, e_date):
            if sym == "7203.T":
                return retry_7203_df
            raise Exception("network error")

        with patch("yfinance.download", return_value=dl_df), \
             patch.object(self.collector, "_get_ohlcv_from_yfinance", side_effect=retry_side_effect) as mock_retry:
            summary = self.collector.prefetch_ohlcv_batch(
                symbols=["9984.T", "7203.T", "6758.T"],
                start_date=date(2025, 1, 6),
                end_date=date(2025, 1, 7),
                precheck_market=False,
            )

        self.assertEqual(summary["batch_updated"], 1)
        self.assertEqual(summary["retried_updated"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["failed_symbols"], ["6758.T"])
        self.assertEqual(mock_retry.call_count, 2)

        # 直後に失敗銘柄 6758.T を collect_ohlcv_data しても _attempted_fetch_ranges により再通信しない
        with patch.object(self.collector, "_get_ohlcv_from_yfinance") as mock_single:
            res_failed = self.collector.collect_ohlcv_data("6758.T", date(2025, 1, 6), date(2025, 1, 7))
            mock_single.assert_not_called()
            self.assertEqual(res_failed, [])

        # yf.download 自体が例外を起こした場合も全銘柄個別リトライへ回る
        collector2 = DataCollector()
        collector2.storage = self.collector.storage
        with patch("yfinance.download", side_effect=RuntimeError("download failed")), \
             patch.object(collector2, "_get_ohlcv_from_yfinance", return_value=pd.DataFrame()) as mock_retry2:
            summary2 = collector2.prefetch_ohlcv_batch(
                symbols=["6758.T"],
                start_date=date(2025, 1, 6),
                end_date=date(2025, 1, 7),
                precheck_market=False,
            )
        mock_retry2.assert_called_once_with("6758.T", date(2025, 1, 6), date(2025, 1, 7))
        self.assertEqual(summary2["failed"], 1)

    def test_prefetch_ohlcv_batch_tail_missing_narrow_range_and_skip_refetch_when_no_bar(self):
        """末尾のみ不足グループは max_date - 7日 の狭い範囲で取得し、新着なしでも再通信を抑止する"""
        cached_df = self._build_price_df([
            date(2025, 1, 6),
            date(2025, 1, 7),
            date(2025, 1, 8),
            date(2025, 1, 9),
            date(2025, 1, 10),
        ])
        self.collector.storage.save_parquet(cached_df, "price/7203.T.parquet")

        with patch("yfinance.download", return_value=pd.DataFrame()) as mock_dl, \
             patch.object(self.collector, "_get_ohlcv_from_yfinance", return_value=pd.DataFrame()):
            summary = self.collector.prefetch_ohlcv_batch(
                symbols=["7203.T"],
                start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 15),
                precheck_market=False,
            )

        # start=max(2025-01-01, 2025-01-10 - 7d = 2025-01-03) -> 2025-01-03
        self.assertEqual(mock_dl.call_args.kwargs["start"], "2025-01-03")
        self.assertEqual(mock_dl.call_args.kwargs["end"], "2025-01-16")
        self.assertEqual(summary["failed"], 1)

        # tail_missing 取得試行済みなので、直後の collect_ohlcv_data でも再通信しない
        with patch.object(self.collector, "_get_ohlcv_from_yfinance") as mock_single:
            res = self.collector.collect_ohlcv_data("7203.T", date(2025, 1, 1), date(2025, 1, 15))
            mock_single.assert_not_called()
            self.assertEqual(len(res), 5)

    @patch("src.data_collector.collector.data_collector")
    def test_module_level_prefetch_ohlcv_batch(self, mock_data_collector):
        """モジュールレベル prefetch_ohlcv_batch が data_collector へ委譲される"""
        mock_data_collector.prefetch_ohlcv_batch.return_value = {"total": 1, "skipped": 0}
        res = prefetch_ohlcv_batch(
            ["7203.T"],
            date(2025, 1, 1),
            date(2025, 1, 10),
            as_of_date=date(2025, 1, 8),
            chunk_size=50,
            precheck_market=False,
            benchmark_symbol="1306.T",
        )
        mock_data_collector.prefetch_ohlcv_batch.assert_called_once_with(
            symbols=["7203.T"],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 10),
            as_of_date=date(2025, 1, 8),
            chunk_size=50,
            precheck_market=False,
            benchmark_symbol="1306.T",
        )
        self.assertEqual(res["total"], 1)

    def test_prefetch_ohlcv_batch_tail_missing_prevents_gap_when_req_start_after_max_date(self):
        """tail_missing で req_start > max_d の場合も既存キャッシュとの間に中抜けを作らない"""
        # 既存キャッシュは 1/6〜1/8 のみ。要求は 1/20〜1/24 (req_start=1/20 > max_d=1/8)
        cached_df = self._build_price_df([date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 8)])
        self.collector.storage.save_parquet(cached_df, "price/7203.T.parquet")

        batch_df = self._build_yf_multiindex_df({
            "7203.T": self._build_price_df(
                [date(2025, 1, 9), date(2025, 1, 10), date(2025, 1, 20), date(2025, 1, 24)]
            ),
        })
        with patch("yfinance.download", return_value=batch_df) as mock_dl:
            summary = self.collector.prefetch_ohlcv_batch(
                symbols=["7203.T"],
                start_date=date(2025, 1, 20),
                end_date=date(2025, 1, 24),
                precheck_market=False,
            )

        self.assertEqual(summary["batch_updated"], 1)
        # sym_start = max(min(1/20, 1/6), 1/8 - 7d = 1/1) = 1/6 となり中抜けしない
        self.assertEqual(mock_dl.call_args.kwargs["start"], "2025-01-06")
        saved = self.collector.storage.load_parquet("price/7203.T.parquet")
        saved_dates = list(pd.to_datetime(saved["date"]).dt.date)
        self.assertIn(date(2025, 1, 9), saved_dates)
        self.assertIn(date(2025, 1, 10), saved_dates)
        self.assertIn(date(2025, 1, 24), saved_dates)

    def test_attempted_fetch_ranges_isolated_on_retry_and_holiday_start(self):
        """チャンク内リトライ銘柄へ他銘柄の広い範囲が誤記録されないこと・休場開始日カバー判定を検証"""
        # 7203.T: 1/20..1/24 キャッシュあり (tail_missing: sym_start=1/17) だがバッチ欠損で個別リトライ失敗
        # 9984.T: キャッシュなし、ただし start_date=1/6 ではなく既存キャッシュで範囲差を作る
        # A(9984.T): キャッシュ 1/15..1/16, 要求 1/6..1/24 -> head_missing (sym_start=1/6)
        # B(7203.T): キャッシュ 1/6..1/6? いや同グループ full_or_head_missing に混在させるため:
        # A(9984.T): キャッシュ 1/10..1/15 -> head_missing (sym_start=1/6)
        # B(7203.T): キャッシュ 1/20..1/21 -> head_missing (sym_start=1/6) ではなく
        # B の sym_start を 1/20 にするため、start_date=1/20 かつ A は min_d=1/6 のキャッシュあり head_missing にする?
        # head_missing は start_ok=False なので min_d > expected_start。
        # tail_missing グループ内で混在させると分かりやすい！
        # A(9984.T): 1/6..1/10 キャッシュ (max_d=1/10 -> sym_start=1/6)
        # B(7203.T): 1/6..1/22 キャッシュ (max_d=1/22 -> sym_start=1/15)
        self.collector.storage.save_parquet(
            self._build_price_df([date(2025, 1, 6), date(2025, 1, 10)]),
            "price/9984.T.parquet",
        )
        self.collector.storage.save_parquet(
            self._build_price_df([date(2025, 1, 6), date(2025, 1, 22)]),
            "price/7203.T.parquet",
        )

        # バッチは 9984.T のみ返却、7203.T は欠損 -> 7203.T のみ個別リトライ(失敗)
        dl_df = self._build_yf_multiindex_df({
            "9984.T": self._build_price_df([date(2025, 1, 10), date(2025, 1, 24)]),
        })
        with patch("yfinance.download", return_value=dl_df), \
             patch.object(self.collector, "_get_ohlcv_from_yfinance", side_effect=RuntimeError("fail")) as mock_retry:
            summary = self.collector.prefetch_ohlcv_batch(
                symbols=["9984.T", "7203.T"],
                start_date=date(2025, 1, 6),
                end_date=date(2025, 1, 24),
                chunk_size=10,
                precheck_market=False,
            )

        self.assertEqual(summary["batch_updated"], 1)
        self.assertEqual(summary["failed"], 1)
        mock_retry.assert_called_once_with("7203.T", date(2025, 1, 15), date(2025, 1, 24))
        # 7203.T には他銘柄の 1/6 ではなく自身の 1/15..1/24 が記録される
        self.assertEqual(self.collector._attempted_fetch_ranges["7203.T"], (date(2025, 1, 15), date(2025, 1, 24)))
        self.assertEqual(self.collector._attempted_fetch_ranges["9984.T"], (date(2025, 1, 6), date(2025, 1, 24)))

        # 7203.T を新しい開始日 2025-01-10 で（キャッシュ削除して）再要求した場合、att_start=1/15 > expected_start=1/10 なので再通信する
        self.collector.storage.save_parquet(self._build_price_df([date(2025, 1, 20)]), "price/7203.T.parquet")
        with patch.object(self.collector, "_get_ohlcv_from_yfinance", return_value=pd.DataFrame()) as mock_refetch:
            self.collector.collect_ohlcv_data("7203.T", date(2025, 1, 10), date(2025, 1, 24))
            mock_refetch.assert_called_once()

        # 休場日(1/1〜1/5)から開始する collect_ohlcv_data でも att_start=1/6 <= expected_start=1/6 でスキップされる
        self.collector._attempted_fetch_ranges["6758.T"] = (date(2025, 1, 6), date(2025, 1, 10))
        with patch.object(self.collector, "_get_ohlcv_from_yfinance") as mock_skip:
            res = self.collector.collect_ohlcv_data("6758.T", date(2025, 1, 1), date(2025, 1, 10))
            mock_skip.assert_not_called()
            self.assertEqual(res, [])

    def test_ohlcv_normalization_types_standard_columns_and_missing_required_col(self):
        """volume の int64 維持・actions の NaN 補完・不要列除去・必須 OHLC 欠損時のリトライを検証"""
        # 既存キャッシュは actions なし・float volume
        cached_df = pd.DataFrame({
            "date": [date(2025, 1, 6)],
            "open": [100.0],
            "high": [105.0],
            "low": [99.0],
            "close": [104.0],
            "volume": [1000.0],
        })
        self.collector.storage.save_parquet(cached_df, "price/9984.T.parquet")

        # 新着バッチは Dividends / Stock Splits / Capital Gains / Adj Close 混在・float volume
        new_raw = pd.DataFrame(
            {
                "Open": [101.0],
                "High": [106.0],
                "Low": [100.0],
                "Close": [105.0],
                "Adj Close": [105.0],
                "Volume": [1500.0],
                "Dividends": [25.0],
                "Stock Splits": [None],
                "Capital Gains": [99.0],
            },
            index=pd.to_datetime(["2025-01-07"]),
        )
        # 7203.T は必須列 'Low' が欠損しているケース
        bad_raw = pd.DataFrame(
            {
                "Open": [200.0],
                "High": [210.0],
                "Close": [205.0],
                "Volume": [3000],
            },
            index=pd.to_datetime(["2025-01-07"]),
        )
        multi_raw = pd.concat({"9984.T": new_raw, "7203.T": bad_raw}, axis=1)

        retry_7203 = self._build_price_df([date(2025, 1, 6), date(2025, 1, 7)])
        with patch("yfinance.download", return_value=multi_raw), \
             patch.object(self.collector, "_get_ohlcv_from_yfinance", return_value=retry_7203) as mock_retry:
            summary = self.collector.prefetch_ohlcv_batch(
                symbols=["9984.T", "7203.T"],
                start_date=date(2025, 1, 6),
                end_date=date(2025, 1, 7),
                precheck_market=False,
            )

        self.assertEqual(summary["batch_updated"], 1)
        self.assertEqual(summary["retried_updated"], 1)
        mock_retry.assert_called_once()

        saved_9984 = self.collector.storage.load_parquet("price/9984.T.parquet")
        self.assertEqual(
            list(saved_9984.columns),
            ["date", "open", "high", "low", "close", "volume", "dividends", "stock_splits"],
        )
        self.assertEqual(str(saved_9984["volume"].dtype), "int64")
        self.assertEqual(saved_9984["dividends"].isna().sum(), 0)
        self.assertEqual(saved_9984["stock_splits"].isna().sum(), 0)
        self.assertEqual(saved_9984.loc[0, "dividends"], 0.0)
        self.assertEqual(saved_9984.loc[1, "dividends"], 25.0)

    def test_market_latest_date_cache_benchmark_separation_and_ttl(self):
        """_market_latest_date_cache のベンチマーク別キー分離、TTL 期限切れ再取得、確定日保持・例外フォールバックを検証"""
        df_1306 = pd.DataFrame(
            {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [100]},
            index=pd.to_datetime(["2025-01-10"]),
        )
        df_1321 = pd.DataFrame(
            {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [100]},
            index=pd.to_datetime(["2025-01-14"]),
        )

        def ticker_side_effect(sym):
            m = MagicMock()
            if sym == "1306.T":
                m.history.return_value = df_1306
            elif sym == "1321.T":
                m.history.return_value = df_1321
            else:
                m.history.side_effect = RuntimeError("timeout")
            return m

        with patch("yfinance.Ticker", side_effect=ticker_side_effect) as mock_ticker, \
             patch("src.data_collector.collector.time.monotonic", side_effect=[100.0, 100.0, 200.0, 500.0, 500.0, 900.0]):
            # 1. 1306.T は未確定日 (1/10 < 1/14) としてキャッシュ
            res_1306_1 = self.collector.resolve_latest_completed_trading_day(
                ref_date=date(2025, 1, 14), benchmark_symbol="1306.T"
            )
            # 2. 別ベンチマーク 1321.T は別キーなので独立取得 (1/14 == schedule_end)
            res_1321_1 = self.collector.resolve_latest_completed_trading_day(
                ref_date=date(2025, 1, 14), benchmark_symbol="1321.T"
            )
            # 3. TTL 内 (200.0 - 100.0 = 100 < 300) は 1306.T キャッシュヒット
            res_1306_2 = self.collector.resolve_latest_completed_trading_day(
                ref_date=date(2025, 1, 14), benchmark_symbol="1306.T"
            )
            # 4. TTL 超過 (500.0 - 100.0 = 400 > 300) は 1306.T を再取得
            res_1306_3 = self.collector.resolve_latest_completed_trading_day(
                ref_date=date(2025, 1, 14), benchmark_symbol="1306.T"
            )
            # 5. 確定済み (1321.T は 1/14 == schedule_end) は TTL 超過相当時刻 (900.0) でも再取得しない
            res_1321_2 = self.collector.resolve_latest_completed_trading_day(
                ref_date=date(2025, 1, 14), benchmark_symbol="1321.T"
            )
            # 6. 例外発生時は schedule_end へフォールバックしキャッシュしない
            res_err = self.collector.resolve_latest_completed_trading_day(
                ref_date=date(2025, 1, 14), benchmark_symbol="9999.T"
            )

        self.assertEqual(res_1306_1, date(2025, 1, 10))
        self.assertEqual(res_1306_2, date(2025, 1, 10))
        self.assertEqual(res_1306_3, date(2025, 1, 10))
        self.assertEqual(res_1321_1, date(2025, 1, 14))
        self.assertEqual(res_1321_2, date(2025, 1, 14))
        self.assertEqual(res_err, date(2025, 1, 14))
        self.assertNotIn((date(2025, 1, 14), "9999.T"), self.collector._market_latest_date_cache)
        # 1306.T が2回、1321.T が1回、9999.T が1回 = 計4回
        self.assertEqual(mock_ticker.call_count, 4)

    def test_prefetch_edge_cases_level1_sort_optimization_and_io_isolation(self):
        """level1 MultiIndex抽出・chunk_size<=0・早期終了・チャンク最適化・Parquet例外隔離・TZ正規化を検証"""
        # 1. chunk_size <= 0
        with self.assertRaises(ValueError):
            self.collector.prefetch_ohlcv_batch(["7203.T"], date(2025, 1, 6), date(2025, 1, 7), chunk_size=0)

        # 2. symbols=[] および 営業日0日（キャッシュなしでも通信しない）
        with patch("yfinance.download") as mock_dl:
            s_empty = self.collector.prefetch_ohlcv_batch([], date(2025, 1, 6), date(2025, 1, 7))
            s_no_bd = self.collector.prefetch_ohlcv_batch(["7203.T"], date(2025, 1, 1), date(2025, 1, 5))
        mock_dl.assert_not_called()
        self.assertEqual(s_empty["total"], 0)
        self.assertEqual(s_no_bd["skipped"], 1)

        # 3. _extract_symbol_df_from_download の level1 パス
        level0_df = self._build_yf_multiindex_df({"130A.T": self._build_price_df([date(2025, 1, 6)])})
        level1_df = level0_df.swaplevel(0, 1, axis=1)
        extracted = self.collector._extract_symbol_df_from_download(level1_df, "130a.T", 2)
        self.assertFalse(extracted.empty)
        self.assertIn("Close", extracted.columns)

        # 4. _normalize_date_column の UTC / 混合 TZ -> JST 正規化
        tz_df = pd.DataFrame({
            "date": [
                pd.Timestamp("2025-01-05 16:00:00+00:00"),  # JST 2025-01-06 01:00
                pd.Timestamp("2025-01-07 09:00:00+09:00"),  # JST 2025-01-07 09:00
            ]
        })
        norm_tz = self.collector._normalize_date_column(tz_df)
        self.assertEqual(list(norm_tz["date"]), [date(2025, 1, 6), date(2025, 1, 7)])

        # 5. sym_start 降順ソートによるチャンク開始日最適化
        # A(1111.T): 古いキャッシュ 1/6..1/8 -> tail_missing sym_start=1/6
        # B(2222.T): 直近キャッシュ 1/6..1/22 -> tail_missing sym_start=1/15
        # C(3333.T): 直近キャッシュ 1/6..1/23 -> tail_missing sym_start=1/16
        self.collector.storage.save_parquet(self._build_price_df([date(2025, 1, 6), date(2025, 1, 8)]), "price/1111.T.parquet")
        self.collector.storage.save_parquet(self._build_price_df([date(2025, 1, 6), date(2025, 1, 22)]), "price/2222.T.parquet")
        self.collector.storage.save_parquet(self._build_price_df([date(2025, 1, 6), date(2025, 1, 23)]), "price/3333.T.parquet")

        chunk_a = self._build_yf_multiindex_df({
            "3333.T": self._build_price_df([date(2025, 1, 24)]),
            "2222.T": self._build_price_df([date(2025, 1, 24)]),
        })
        chunk_b = self._build_yf_multiindex_df({
            "1111.T": self._build_price_df([date(2025, 1, 24)]),
        })
        with patch("yfinance.download", side_effect=[chunk_a, chunk_b]) as mock_dl:
            self.collector.prefetch_ohlcv_batch(
                symbols=["1111.T", "2222.T", "3333.T"],
                start_date=date(2025, 1, 6),
                end_date=date(2025, 1, 24),
                chunk_size=2,
                precheck_market=False,
            )
        # 降順ソートにより [3333.T, 2222.T] が先頭チャンク (start=2025-01-15) で取得される
        self.assertEqual(mock_dl.call_args_list[0].kwargs["tickers"], ["3333.T", "2222.T"])
        self.assertEqual(mock_dl.call_args_list[0].kwargs["start"], "2025-01-15")
        self.assertEqual(mock_dl.call_args_list[1].kwargs["tickers"], ["1111.T"])
        self.assertEqual(mock_dl.call_args_list[1].kwargs["start"], "2025-01-06")

        # 6. Parquet 読込失敗・保存失敗の銘柄別隔離
        def load_side_effect(path):
            if "BAD_READ" in path:
                raise OSError("corrupt parquet")
            return None

        def save_side_effect(df, path):
            if "BAD_SAVE" in path:
                raise OSError("disk full")

        dl_io = self._build_yf_multiindex_df({
            "BAD_READ.T": self._build_price_df([date(2025, 1, 6)]),
            "BAD_SAVE.T": self._build_price_df([date(2025, 1, 6)]),
            "GOOD.T": self._build_price_df([date(2025, 1, 6)]),
        })
        with patch.object(self.collector.storage, "load_parquet", side_effect=load_side_effect), \
             patch.object(self.collector.storage, "save_parquet", side_effect=save_side_effect), \
             patch("yfinance.download", return_value=dl_io):
            summary_io = self.collector.prefetch_ohlcv_batch(
                symbols=["BAD_READ.T", "BAD_SAVE.T", "GOOD.T"],
                start_date=date(2025, 1, 6),
                end_date=date(2025, 1, 6),
                precheck_market=False,
            )
        self.assertEqual(summary_io["batch_updated"], 2)  # BAD_READ.T と GOOD.T は保存成功
        self.assertEqual(summary_io["failed"], 1)
        self.assertEqual(summary_io["failed_symbols"], ["BAD_SAVE.T"])

    def test_collect_ohlcv_uses_column_pruning_and_preserves_native_types(self):
        """collect_ohlcv_data が列限定読込と model_construct によるネイティブ Python 型を返す"""
        df = pd.DataFrame({
            "date": [date(2025, 1, 6), date(2025, 1, 7)],
            "open": [100.0, 102.0],
            "high": [105.0, 107.0],
            "low": [99.0, 101.0],
            "close": [104.0, 106.0],
            "volume": [1000, 1500],
            "dividends": [0.0, 20.0],
            "stock_splits": [0.0, 0.0],
        })
        self.collector.storage.save_parquet(df, f"price/{self.symbol}.parquet")

        orig_load = self.collector.storage.load_parquet
        with patch.object(
            self.collector.storage, "load_parquet", side_effect=orig_load
        ) as spy_load:
            res = self.collector.collect_ohlcv_data(
                self.symbol, date(2025, 1, 6), date(2025, 1, 7)
            )

        spy_load.assert_called_once_with(
            f"price/{self.symbol}.parquet", columns=OHLCV_READ_COLUMNS
        )
        self.assertEqual(len(res), 2)
        bar = res[0]
        self.assertIs(type(bar.symbol), str)
        self.assertIs(type(bar.date), date)
        self.assertIs(type(bar.open), float)
        self.assertIs(type(bar.high), float)
        self.assertIs(type(bar.low), float)
        self.assertIs(type(bar.close), float)
        self.assertIs(type(bar.volume), int)
        # OhlcvModel(...) の通常バリデーション構築と完全一致
        expected = OhlcvModel(
            symbol=self.symbol,
            date=date(2025, 1, 6),
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=1000,
        )
        self.assertEqual(bar.model_dump(), expected.model_dump())

    def test_collect_ohlcv_legacy_single_arg_load_parquet_mock_fallback(self):
        """1引数のみ受け付ける load_parquet モックでも TypeError フォールバックで動作する"""
        sample_df = pd.DataFrame({
            "date": [date(2025, 1, 6)],
            "open": [100.0],
            "high": [105.0],
            "low": [99.0],
            "close": [104.0],
            "volume": [1000],
        })

        def single_arg_load(path):
            return sample_df

        with patch.object(self.collector.storage, "load_parquet", side_effect=single_arg_load):
            res = self.collector.collect_ohlcv_data(
                self.symbol, date(2025, 1, 6), date(2025, 1, 6)
            )
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].close, 104.0)

    def test_collect_ohlcv_cleanses_nan_rows_and_volume(self):
        """Parquet 内の NaN 行除外および volume の丸め int64 化を検証"""
        dirty_df = pd.DataFrame({
            "date": [date(2025, 1, 6), None, date(2025, 1, 8), date(2025, 1, 9)],
            "open": [100.0, 101.0, float("nan"), 103.0],
            "high": [105.0, 106.0, 107.0, 108.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [104.0, 105.0, 106.0, 107.0],
            "volume": [float("nan"), 1100.0, 1200.0, 1300.6],
        })
        self.collector.storage.save_parquet(dirty_df, f"price/{self.symbol}.parquet")

        res = self.collector.collect_ohlcv_data(
            self.symbol, date(2025, 1, 6), date(2025, 1, 9)
        )
        self.assertEqual([r.date for r in res], [date(2025, 1, 6), date(2025, 1, 9)])
        self.assertEqual(res[0].volume, 0)
        self.assertIs(type(res[0].volume), int)
        self.assertEqual(res[1].volume, 1301)

    def test_collect_ohlcv_cleanses_inf_values_in_price_and_volume(self):
        """価格列や volume に inf / -inf が混入しても IntCastingNaNError にならず安全にクレンジングされる"""
        inf_df = pd.DataFrame({
            "date": [date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 8)],
            "open": [100.0, float("inf"), 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [99.0, 100.0, float("-inf")],
            "close": [104.0, 105.0, 106.0],
            "volume": [float("inf"), 1100.0, float("-inf")],
        })
        self.collector.storage.save_parquet(inf_df, f"price/{self.symbol}.parquet")

        res = self.collector.collect_ohlcv_data(
            self.symbol, date(2025, 1, 6), date(2025, 1, 8)
        )
        # 1/7 (open=inf) と 1/8 (low=-inf) は除外され、1/6 (volume=inf -> 0) のみ残る
        self.assertEqual([r.date for r in res], [date(2025, 1, 6)])
        self.assertEqual(res[0].volume, 0)
        self.assertIs(type(res[0].volume), int)

    @patch("yfinance.Ticker")
    def test_collect_ohlcv_need_fetch_preserves_dividends_and_stock_splits(self, mock_ticker):
        """need_fetch=True で再保存する際に既存 Parquet の dividends / stock_splits 列を失わない"""
        existing_df = pd.DataFrame({
            "date": [date(2025, 1, 6), date(2025, 1, 7)],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            "close": [104.0, 105.0],
            "volume": [1000, 1100],
            "dividends": [0.0, 25.0],
            "stock_splits": [0.0, 2.0],
        })
        self.collector.storage.save_parquet(existing_df, f"price/{self.symbol}.parquet")

        new_history = pd.DataFrame({
            "Open": [102.0],
            "High": [108.0],
            "Low": [101.0],
            "Close": [107.0],
            "Volume": [1200],
            "Dividends": [0.0],
            "Stock Splits": [0.0],
        }, index=pd.to_datetime(["2025-01-08"]))
        mock_ticker.return_value.history.return_value = new_history

        res = self.collector.collect_ohlcv_data(
            self.symbol, date(2025, 1, 6), date(2025, 1, 8)
        )
        self.assertEqual(len(res), 3)

        saved_full = self.collector.storage.load_parquet(f"price/{self.symbol}.parquet")
        self.assertIsNotNone(saved_full)
        self.assertIn("dividends", saved_full.columns)
        self.assertIn("stock_splits", saved_full.columns)
        row_jan7 = saved_full[saved_full["date"] == date(2025, 1, 7)].iloc[0]
        self.assertAlmostEqual(float(row_jan7["dividends"]), 25.0)
        self.assertAlmostEqual(float(row_jan7["stock_splits"]), 2.0)

    def test_collect_ohlcv_read_only_uses_cache_only_and_never_fetches_or_saves(self):
        """read_only=True 時はキャッシュ不足でも yfinance 通信・Parquet 保存せずキャッシュ部分のみ返し、未存在時は [] を返す"""
        # 1. キャッシュ未存在時は []
        with patch("yfinance.Ticker") as mock_ticker, \
             patch.object(self.collector.storage, "save_parquet") as mock_save:
            res_missing = self.collector.collect_ohlcv_data(
                self.symbol, date(2025, 1, 6), date(2025, 1, 10), read_only=True
            )
        self.assertEqual(res_missing, [])
        mock_ticker.assert_not_called()
        mock_save.assert_not_called()

        # 2. キャッシュが部分期間（1/6〜1/7のみ）しかなくても 1/6〜1/10 要求時に通信・保存せず 1/6〜1/7 を返す
        partial_df = pd.DataFrame({
            "date": [date(2025, 1, 6), date(2025, 1, 7)],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            "close": [104.0, 105.0],
            "volume": [1000, 1100],
        })
        self.collector.storage.save_parquet(partial_df, f"price/{self.symbol}.parquet")

        with patch("yfinance.Ticker") as mock_ticker, \
             patch.object(self.collector.storage, "save_parquet") as mock_save:
            res_partial = self.collector.collect_ohlcv_data(
                self.symbol, date(2025, 1, 6), date(2025, 1, 10), read_only=True
            )
        self.assertEqual([b.date for b in res_partial], [date(2025, 1, 6), date(2025, 1, 7)])
        mock_ticker.assert_not_called()
        mock_save.assert_not_called()

        # 3. モジュールレベルラッパーも read_only=True を伝播する
        with patch("src.data_collector.collector.data_collector") as mock_dc:
            mock_dc.collect_ohlcv_data.return_value = []
            collect_ohlcv_data(
                self.symbol,
                date(2025, 1, 6),
                date(2025, 1, 10),
                as_of_date=date(2025, 1, 10),
                read_only=True,
            )
            mock_dc.collect_ohlcv_data.assert_called_once_with(
                self.symbol,
                date(2025, 1, 6),
                date(2025, 1, 10),
                as_of_date=date(2025, 1, 10),
                read_only=True,
            )

    def test_load_irbank_json_read_only_prevents_download_and_corrupt_removal(self):
        """read_only=True の _load_irbank_json と collect_financial_data は DL も破損JSON削除も行わない"""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = DataCollector()
            collector.storage = StorageManager(base_dir=tmpdir)
            collector.local_irbank_dir = os.path.join(tmpdir, "local_irbank")
            collector.user_irbank_dir = os.path.join(tmpdir, "user_irbank")
            os.makedirs(collector.local_irbank_dir, exist_ok=True)
            os.makedirs(collector.user_irbank_dir, exist_ok=True)

            # 1. 未存在ファイルに対して allow_download=True でも read_only=True なら DL しない
            with patch.object(collector, "_download_irbank_file") as mock_dl:
                res_missing = collector._load_irbank_json(
                    2095, collector.BALANCE_SHEET_FILE_NAME, allow_download=True, read_only=True
                )
            self.assertIsNone(res_missing)
            mock_dl.assert_not_called()

            # 2. 破損 JSON が存在しても read_only=True 時は os.remove しない
            corrupt_path = collector.storage.financial_dir / "0096-fy-balance-sheet.json"
            corrupt_path.write_text("{corrupt json", encoding="utf-8")
            with patch.object(collector, "_download_irbank_file") as mock_dl:
                res_corrupt = collector._load_irbank_json(
                    2096, collector.BALANCE_SHEET_FILE_NAME, allow_download=True, read_only=True
                )
            self.assertIsNone(res_corrupt)
            mock_dl.assert_not_called()
            self.assertTrue(corrupt_path.exists())

            # 3. collect_financial_data(..., read_only=True) も DL・破損削除しない
            corrupt_pl = collector.storage.financial_dir / "0096-fy-profit-and-loss.json"
            corrupt_pl.write_text("{corrupt json", encoding="utf-8")
            with patch.object(collector, "_download_irbank_file") as mock_dl:
                fin = collector.collect_financial_data(
                    "7203.T",
                    fiscal_year=2096,
                    allow_download=True,
                    latest_close=1000.0,
                    read_only=True,
                )
            self.assertIsNone(fin)
            mock_dl.assert_not_called()
            self.assertTrue(corrupt_path.exists())
            self.assertTrue(corrupt_pl.exists())

    def test_warmup_irbank_cache_preloads_bs_and_pl_for_unique_years(self):
        """warmup_irbank_cache が重複排除した全年度の BS / PL / 配当 / CF(ローカル) と最新CF/配当を事前ロードする"""
        collector = DataCollector()
        with patch.object(collector, "_load_irbank_json", return_value={"item": {}}) as mock_load:
            collector.warmup_irbank_cache([2025, 2023, 2025, 2024], allow_download=False)

        expected_calls = [
            unittest.mock.call(2023, collector.BALANCE_SHEET_FILE_NAME, allow_download=False),
            unittest.mock.call(2023, collector.PROFIT_AND_LOSS_FILE_NAME, allow_download=False),
            unittest.mock.call(2023, collector.STOCK_DIVIDEND_FILE_NAME, allow_download=False),
            unittest.mock.call(2023, collector.CASH_FLOW_FILE_NAME, allow_download=False),
            unittest.mock.call(2024, collector.BALANCE_SHEET_FILE_NAME, allow_download=False),
            unittest.mock.call(2024, collector.PROFIT_AND_LOSS_FILE_NAME, allow_download=False),
            unittest.mock.call(2024, collector.STOCK_DIVIDEND_FILE_NAME, allow_download=False),
            unittest.mock.call(2024, collector.CASH_FLOW_FILE_NAME, allow_download=False),
            unittest.mock.call(2025, collector.BALANCE_SHEET_FILE_NAME, allow_download=False),
            unittest.mock.call(2025, collector.PROFIT_AND_LOSS_FILE_NAME, allow_download=False),
            unittest.mock.call(2025, collector.STOCK_DIVIDEND_FILE_NAME, allow_download=False),
            unittest.mock.call(2025, collector.CASH_FLOW_FILE_NAME, allow_download=False),
            unittest.mock.call(0, collector.CASH_FLOW_FILE_NAME, allow_download=False),
            unittest.mock.call(0, collector.STOCK_DIVIDEND_FILE_NAME, allow_download=False),
        ]
        self.assertEqual(mock_load.call_args_list, expected_calls)

        # allow_download=True 時も年度別 CF のみ allow_download=False となることを検証
        with patch.object(collector, "_load_irbank_json", return_value={"item": {}}) as mock_load_dl:
            collector.warmup_irbank_cache([2024], allow_download=True)

        expected_calls_dl = [
            unittest.mock.call(2024, collector.BALANCE_SHEET_FILE_NAME, allow_download=True),
            unittest.mock.call(2024, collector.PROFIT_AND_LOSS_FILE_NAME, allow_download=True),
            unittest.mock.call(2024, collector.STOCK_DIVIDEND_FILE_NAME, allow_download=True),
            unittest.mock.call(2024, collector.CASH_FLOW_FILE_NAME, allow_download=False),
            unittest.mock.call(0, collector.CASH_FLOW_FILE_NAME, allow_download=True),
            unittest.mock.call(0, collector.STOCK_DIVIDEND_FILE_NAME, allow_download=True),
        ]
        self.assertEqual(mock_load_dl.call_args_list, expected_calls_dl)

    def test_prefetch_ohlcv_batch_and_warmup_progress_output(self):
        """prefetch_ohlcv_batch のチャンク進捗・開始/完了サマリーと warmup_irbank_cache のサマリー出力を検証"""
        symbols = [f"{7000 + i}.T" for i in range(10)]
        dates = pd.to_datetime(["2025-01-06", "2025-01-07"])

        def fake_yf_download(tickers, **kwargs):
            cols = pd.MultiIndex.from_product(
                [tickers, ["Open", "High", "Low", "Close", "Volume"]]
            )
            data = {}
            for sym in tickers:
                data[(sym, "Open")] = [100.0, 101.0]
                data[(sym, "High")] = [105.0, 106.0]
                data[(sym, "Low")] = [99.0, 100.0]
                data[(sym, "Close")] = [104.0, 105.0]
                data[(sym, "Volume")] = [10000, 12000]
            return pd.DataFrame(data, index=dates, columns=cols)

        buf = io.StringIO()
        with patch("src.data_collector.collector.yf.download", side_effect=fake_yf_download), \
             patch.object(self.collector, "_load_irbank_json", return_value={"item": {}}), \
             redirect_stdout(buf):
            summary = self.collector.prefetch_ohlcv_batch(
                symbols=symbols,
                start_date=date(2025, 1, 6),
                end_date=date(2025, 1, 7),
                chunk_size=5,
                precheck_market=False,
            )
            self.collector.warmup_irbank_cache([2024, 2025], allow_download=False)

        self.assertEqual(summary["batch_updated"], 10)
        out = buf.getvalue()
        self.assertIn("OHLCVバッチ取得開始: 更新対象=10銘柄", out)
        self.assertIn("[進行度] OHLCV取得[full_or_head_missing]: 5/10 (50.0%)", out)
        self.assertIn("[進行度] OHLCV取得[full_or_head_missing]: 10/10 (100.0%)", out)
        self.assertIn("OHLCVバッチプリフェッチ完了:", out)
        self.assertIn("IR BANK 財務キャッシュ準備中: 2024〜2025年度 (2期分)...", out)
        self.assertIn("IR BANK 財務キャッシュ準備完了 (2期分)", out)

    def test_collect_financial_data_split_adjustment_and_lookahead_boundary(self):
        """株式分割による EPS/BPS/PER/PBR 補正と先読みバイアス境界・フォールバックを検証"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=tmpdir)
            collector = DataCollector(storage=storage)

            # 2024年3月期決算 (fiscal_date = 2024-03-31, 開示日 = 2024-05-30)
            bs_2024 = {
                "item": {
                    "7203": ["2024/03", "1000000", "500000", "450000", "300000", "10000", "20000", "2000.0", "45.0"]
                }
            }
            pl_2024 = {
                "item": {
                    "7203": ["2024/03", "100000", "15000", "16000", "10000", "100.0", "12.0", "5.0"]
                }
            }
            (storage.financial_dir / "0024-fy-balance-sheet.json").write_text(
                json.dumps(bs_2024), encoding="utf-8"
            )
            (storage.financial_dir / "0024-fy-profit-and-loss.json").write_text(
                json.dumps(pl_2024), encoding="utf-8"
            )

            # price Parquet に境界日付の stock_splits を保存
            # - 2024-03-31 (fiscal_date 当日): 適用しない
            # - 2024-06-01 (fiscal_date < d <= as_of_date): 適用する (2.0)
            # - 2024-09-01 (通常日 0.0): 無視する
            # - 2024-10-01 (as_of_date=2024-09-30 より未来): 適用しない (3.0)
            price_df = pd.DataFrame({
                "date": [date(2024, 3, 31), date(2024, 6, 1), date(2024, 9, 1), date(2024, 10, 1)],
                "open": [1000.0, 1000.0, 1000.0, 1000.0],
                "high": [1000.0, 1000.0, 1000.0, 1000.0],
                "low": [1000.0, 1000.0, 1000.0, 1000.0],
                "close": [1000.0, 1000.0, 1000.0, 1000.0],
                "volume": [10000, 10000, 10000, 10000],
                "stock_splits": [2.0, 2.0, 0.0, 3.0],
            })
            storage.save_parquet(price_df, storage.price_dir / "7203.T.parquet")

            # as_of_date = 2024-09-30, latest_close=1000.0, read_only=True
            fin_sep = collector.collect_financial_data(
                "7203.T",
                fiscal_year=2024,
                as_of_date=date(2024, 9, 30),
                allow_download=False,
                latest_close=1000.0,
                read_only=True,
            )
            self.assertIsNotNone(fin_sep)
            self.assertAlmostEqual(fin_sep.eps, 50.0)
            self.assertAlmostEqual(fin_sep.bps, 1000.0)
            self.assertAlmostEqual(fin_sep.per, 20.0)
            self.assertAlmostEqual(fin_sep.pbr, 1.0)

            # as_of_date = 2024-10-15 では 2024-10-01 の 3.0 も累積乗算 (ratio = 6.0)
            fin_oct = collector.collect_financial_data(
                "7203.T",
                fiscal_year=2024,
                as_of_date=date(2024, 10, 15),
                allow_download=False,
                latest_close=1000.0,
                read_only=True,
            )
            self.assertIsNotNone(fin_oct)
            self.assertAlmostEqual(fin_oct.eps, 100.0 / 6.0)
            self.assertAlmostEqual(fin_oct.bps, 2000.0 / 6.0)
            self.assertAlmostEqual(fin_oct.per, 60.0)
            self.assertAlmostEqual(fin_oct.pbr, 3.0)

            # Parquet が存在しない場合は ratio=1.0 へ安全にフォールバック
            (storage.price_dir / "7203.T.parquet").unlink()
            fin_no_parquet = collector.collect_financial_data(
                "7203.T",
                fiscal_year=2024,
                as_of_date=date(2024, 9, 30),
                allow_download=False,
                latest_close=1000.0,
                read_only=True,
            )
            self.assertIsNotNone(fin_no_parquet)
            self.assertAlmostEqual(fin_no_parquet.eps, 100.0)
            self.assertAlmostEqual(fin_no_parquet.bps, 2000.0)

    def test_collect_financial_data_growth_missing_keeps_none_and_f002_integration(self):
        """成長率欠損時に None を維持し、F002_GrowthScore が 3年平均へ正しくフォールバックすることを検証"""
        from src.feature_engine.features.fundamental.growth_score import GrowthScore
        from src.model.data_models import IndicatorSetModel

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=tmpdir)
            collector = DataCollector(storage=storage)

            bs_2024 = {
                "item": {
                    "7203": ["2024/03", "1000000", "500000", "450000", "300000", "10000", "20000", "2000.0", "45.0"]
                }
            }
            # 当期(2024): 売上 173.0, 純利益 173.0 (3年前 100.0 から年率+20%超)
            pl_2024 = {"item": {"7203": ["2024/03", "173.0", "20", "20", "173.0", "100.0", "12.0", "5.0"]}}
            # 1年前(2023): 欠損 "-"
            pl_2023 = {"item": {"7203": ["2023/03", "-", "10", "10", "-", "50.0", "10.0", "4.0"]}}
            # 3年前(2021): 売上 100.0, 純利益 100.0
            pl_2021 = {"item": {"7203": ["2021/03", "100.0", "10", "10", "100.0", "50.0", "10.0", "4.0"]}}
            # 5年前(2019): 欠損 "-"
            pl_2019 = {"item": {"7203": ["2019/03", "-", "10", "10", "-", "50.0", "10.0", "4.0"]}}

            (storage.financial_dir / "0024-fy-balance-sheet.json").write_text(json.dumps(bs_2024), encoding="utf-8")
            (storage.financial_dir / "0024-fy-profit-and-loss.json").write_text(json.dumps(pl_2024), encoding="utf-8")
            (storage.financial_dir / "0023-fy-profit-and-loss.json").write_text(json.dumps(pl_2023), encoding="utf-8")
            (storage.financial_dir / "0021-fy-profit-and-loss.json").write_text(json.dumps(pl_2021), encoding="utf-8")
            (storage.financial_dir / "0019-fy-profit-and-loss.json").write_text(json.dumps(pl_2019), encoding="utf-8")

            fin = collector.collect_financial_data(
                "7203.T",
                fiscal_year=2024,
                as_of_date=date(2024, 9, 30),
                allow_download=False,
                latest_close=1000.0,
                read_only=True,
            )
            self.assertIsNotNone(fin)
            self.assertIsNone(fin.revenue_growth)
            self.assertIsNone(fin.net_profit_growth)
            self.assertIsNone(fin.revenue_growth_5y_avg)
            self.assertIsNone(fin.net_profit_growth_5y_avg)
            self.assertGreater(fin.revenue_growth_3y_avg, 20.0)
            self.assertGreater(fin.net_profit_growth_3y_avg, 20.0)

            # F002_GrowthScore が 5年平均=None をスキップして 3年平均(+20%) を採用し 100点になること
            ind = [IndicatorSetModel(symbol="7203.T", date=date(2024, 9, 30), indicators={})]
            f002_res = GrowthScore().calculate([], ind, financial_data=fin)
            self.assertEqual(len(f002_res), 1)
            self.assertAlmostEqual(f002_res[0].score, 100.0)

    def test_collect_financial_data_split_edge_cases_and_relative_storage(self):
        """stock_splits の異常値・列欠損・同一日付重複・相対パス StorageManager・1引数モック互換を検証"""
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmpdir:
            rel_base = Path(tmpdir).relative_to(Path.cwd())
            rel_storage = StorageManager(base_dir=str(rel_base))
            rel_collector = DataCollector(storage=rel_storage)

            # 相対パス StorageManager でも base_dir 二重結合せずに _compute_cumulative_split_ratio が動作すること
            rel_df = pd.DataFrame({
                "date": [date(2024, 6, 1)],
                "open": [1000.0],
                "high": [1000.0],
                "low": [1000.0],
                "close": [1000.0],
                "volume": [10000],
                "stock_splits": [2.0],
            })
            rel_storage.save_parquet(rel_df, "price/7203.T.parquet")
            self.assertAlmostEqual(
                rel_collector._compute_cumulative_split_ratio(
                    "7203.T", date(2024, 3, 31), date(2024, 9, 30)
                ),
                2.0,
            )

            storage = StorageManager(base_dir=tmpdir)
            collector = DataCollector(storage=storage)

            bs_2024 = {
                "item": {
                    "7203": ["2024/03", "1000000", "500000", "450000", "300000", "10000", "20000", "2000.0", "45.0"]
                }
            }
            pl_2024 = {
                "item": {
                    "7203": ["2024/03", "100000", "15000", "16000", "10000", "100.0", "12.0", "5.0"]
                }
            }
            (storage.financial_dir / "0024-fy-balance-sheet.json").write_text(
                json.dumps(bs_2024), encoding="utf-8"
            )
            (storage.financial_dir / "0024-fy-profit-and-loss.json").write_text(
                json.dumps(pl_2024), encoding="utf-8"
            )

            # 1) NaN / inf / -inf / 負値、および同一日付重複行（keep="last" で後の値 2.0 のみ採用）を含む Parquet
            price_df = pd.DataFrame({
                "date": [
                    date(2024, 5, 1),
                    date(2024, 5, 15),
                    date(2024, 5, 20),
                    date(2024, 5, 25),
                    date(2024, 6, 1),
                    date(2024, 6, 1),
                ],
                "open": [1000.0] * 6,
                "high": [1000.0] * 6,
                "low": [1000.0] * 6,
                "close": [1000.0] * 6,
                "volume": [10000] * 6,
                "stock_splits": [float("nan"), float("inf"), float("-inf"), -2.0, 5.0, 2.0],
            })
            storage.save_parquet(price_df, "price/7203.T.parquet")

            fin_rel = collector.collect_financial_data(
                "7203.T",
                fiscal_year=2024,
                as_of_date=date(2024, 9, 30),
                allow_download=False,
                latest_close=1000.0,
                read_only=True,
            )
            self.assertIsNotNone(fin_rel)
            # 重複日の keep="last" (2.0) のみが適用されること
            self.assertAlmostEqual(fin_rel.eps, 50.0)
            self.assertAlmostEqual(fin_rel.bps, 1000.0)

            # 2) columns 引数を受け付けないモック StorageManager でも 1引数フォールバックで動作すること
            orig_load = storage.load_parquet
            with patch.object(
                storage,
                "load_parquet",
                side_effect=lambda p: orig_load(p),
            ):
                fin_mock = collector.collect_financial_data(
                    "7203.T",
                    fiscal_year=2024,
                    as_of_date=date(2024, 9, 30),
                    allow_download=False,
                    latest_close=1000.0,
                    read_only=True,
                )
            self.assertIsNotNone(fin_mock)
            self.assertAlmostEqual(fin_mock.eps, 50.0)

            # 3) stock_splits 列が存在しない Parquet の場合は ratio=1.0
            no_split_col_df = price_df.drop(columns=["stock_splits"])
            storage.save_parquet(no_split_col_df, "price/7203.T.parquet")
            fin_no_col = collector.collect_financial_data(
                "7203.T",
                fiscal_year=2024,
                as_of_date=date(2024, 9, 30),
                allow_download=False,
                latest_close=1000.0,
                read_only=True,
            )
            self.assertIsNotNone(fin_no_col)
            self.assertAlmostEqual(fin_no_col.eps, 100.0)
            self.assertAlmostEqual(fin_no_col.bps, 2000.0)

    def test_collect_financial_data_abnormal_eps_bps_and_datetime_as_of(self):
        """datetime型 as_of_date の正規化と eps=0 / 極小EPS / 'nan' / 'inf' 異常値ガードを検証"""
        import math

        for label, raw_eps, raw_bps, expected_eps, expected_bps, expected_per, expected_pbr in [
            ("zero_eps", "0", "2000.0", 0.0, 2000.0, 0.0, 0.5),
            ("tiny_eps", "1e-310", "2000.0", 1e-310, 2000.0, 0.0, 0.5),
            ("nan_str", "nan", "NaN", 0.0, 0.0, 0.0, 0.0),
            ("inf_str", "inf", "-inf", 0.0, 0.0, 0.0, 0.0),
        ]:
            with self.subTest(case=label):
                with tempfile.TemporaryDirectory() as tmpdir:
                    storage = StorageManager(base_dir=tmpdir)
                    collector = DataCollector(storage=storage)
                    bs_2024 = {
                        "item": {
                            "7203": ["2024/03", "1000000", "500000", "450000", "300000", "10000", "20000", raw_bps, "45.0"]
                        }
                    }
                    pl_2024 = {
                        "item": {
                            "7203": ["2024/03", "100000", "15000", "16000", "10000", raw_eps, "12.0", "5.0"]
                        }
                    }
                    (storage.financial_dir / "0024-fy-balance-sheet.json").write_text(
                        json.dumps(bs_2024), encoding="utf-8"
                    )
                    (storage.financial_dir / "0024-fy-profit-and-loss.json").write_text(
                        json.dumps(pl_2024), encoding="utf-8"
                    )

                    fin = collector.collect_financial_data(
                        "7203.T",
                        fiscal_year=2024,
                        as_of_date=datetime(2024, 9, 30, 15, 0, 0),
                        allow_download=False,
                        latest_close=1000.0,
                        read_only=True,
                    )
                    self.assertIsNotNone(fin)
                    self.assertTrue(math.isfinite(fin.eps))
                    self.assertTrue(math.isfinite(fin.bps))
                    self.assertTrue(math.isfinite(fin.per))
                    self.assertTrue(math.isfinite(fin.pbr))
                    self.assertAlmostEqual(fin.eps, expected_eps)
                    self.assertAlmostEqual(fin.bps, expected_bps)
                    self.assertAlmostEqual(fin.per, expected_per)
                    self.assertAlmostEqual(fin.pbr, expected_pbr)

    @staticmethod
    def _make_isolated_collector(tmpdir: str) -> tuple[DataCollector, StorageManager]:
        """テスト用に IR BANK キャッシュ先まで完全に隔離した DataCollector を生成する"""
        tmp_path = Path(tmpdir)
        storage = StorageManager(base_dir=tmp_path / "data")
        local_irbank = tmp_path / "local_irbank"
        user_irbank = tmp_path / "user_irbank"
        local_irbank.mkdir(parents=True, exist_ok=True)
        user_irbank.mkdir(parents=True, exist_ok=True)
        collector = DataCollector(
            storage=storage,
            cache_dir=str(tmp_path / "cache"),
            local_irbank_dir=str(local_irbank),
            user_irbank_dir=str(user_irbank),
        )
        return collector, storage

    def test_collect_financial_data_and_snapshot_extra_bs_pl_columns(self):
        """BS/PL 未抽出列が collect_financial_data / load_financial_snapshot の双方で正しく設定・欠損時 None になる"""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector, storage = self._make_isolated_collector(tmpdir)

            bs_2024 = {
                "meta": {"type": "BS"},
                "item": {
                    # ["年度","総資産","純資産","株主資本","利益剰余金","短期借入金","長期借入金","BPS","自己資本比率"]
                    "7203": ["2024/03", "1000000", "500000", "450000", "300000", "0", "20000", "2000.0", "45.0"],
                    "9984": ["2024/03", "800000", "-", "nan", "inf", "-inf", "-", "1500.0", "30.0"],
                },
            }
            pl_2024 = {
                "meta": {"type": "PL"},
                "item": {
                    # ["年度","売上高","営業利益","経常利益","当期純利益","EPS","ROE","ROA"]
                    "7203": ["2024/03", "100000", "15000", "16500", "10000", "100.0", "12.0", "5.0"],
                    "9984": ["2024/03", "50000", "5000", "-", "3000", "50.0", "8.0", "3.0"],
                },
            }
            # load_financial_snapshot が CF / 配当を読まないことも併せて検証するため破損ファイルを置く
            (storage.financial_dir / "0024-fy-balance-sheet.json").write_text(json.dumps(bs_2024), encoding="utf-8")
            (storage.financial_dir / "0024-fy-profit-and-loss.json").write_text(json.dumps(pl_2024), encoding="utf-8")
            (storage.financial_dir / "0000-fy-cash-flow-statement.json").write_text("{corrupt", encoding="utf-8")
            (storage.financial_dir / "0024-fy-stock-dividend.json").write_text("{corrupt", encoding="utf-8")

            fin_7203 = collector.collect_financial_data(
                "7203.T",
                fiscal_year=2024,
                as_of_date=date(2024, 9, 30),
                allow_download=False,
                latest_close=1000.0,
                read_only=True,
            )
            self.assertIsNotNone(fin_7203)
            self.assertEqual(fin_7203.net_assets, 500000.0)
            self.assertEqual(fin_7203.shareholders_equity, 450000.0)
            self.assertEqual(fin_7203.retained_earnings, 300000.0)
            self.assertEqual(fin_7203.short_term_debt, 0.0)
            self.assertEqual(fin_7203.long_term_debt, 20000.0)
            self.assertEqual(fin_7203.ordinary_profit, 16500.0)

            fin_9984 = collector.collect_financial_data(
                "9984.T",
                fiscal_year=2024,
                as_of_date=date(2024, 9, 30),
                allow_download=False,
                latest_close=1000.0,
                read_only=True,
            )
            self.assertIsNotNone(fin_9984)
            self.assertIsNone(fin_9984.net_assets)
            self.assertIsNone(fin_9984.shareholders_equity)
            self.assertIsNone(fin_9984.retained_earnings)
            self.assertIsNone(fin_9984.short_term_debt)
            self.assertIsNone(fin_9984.long_term_debt)
            self.assertIsNone(fin_9984.ordinary_profit)

            # load_financial_snapshot は CF / 配当を参照せず高速取得する
            with patch.object(collector, "_load_irbank_json", wraps=collector._load_irbank_json) as spy_load:
                snap = collector.load_financial_snapshot(
                    fiscal_year=2024,
                    as_of_date=date(2024, 9, 30),
                )
            loaded_types = {call_args.args[1] for call_args in spy_load.call_args_list}
            self.assertNotIn(collector.CASH_FLOW_FILE_NAME, loaded_types)
            self.assertNotIn(collector.STOCK_DIVIDEND_FILE_NAME, loaded_types)

            self.assertIn("7203", snap)
            self.assertEqual(snap["7203"].net_assets, 500000.0)
            self.assertEqual(snap["7203"].shareholders_equity, 450000.0)
            self.assertEqual(snap["7203"].retained_earnings, 300000.0)
            self.assertEqual(snap["7203"].short_term_debt, 0.0)
            self.assertEqual(snap["7203"].long_term_debt, 20000.0)
            self.assertEqual(snap["7203"].ordinary_profit, 16500.0)

            self.assertIn("9984", snap)
            self.assertIsNone(snap["9984"].net_assets)
            self.assertIsNone(snap["9984"].shareholders_equity)
            self.assertIsNone(snap["9984"].retained_earnings)
            self.assertIsNone(snap["9984"].short_term_debt)
            self.assertIsNone(snap["9984"].long_term_debt)
            self.assertIsNone(snap["9984"].ordinary_profit)

    def test_collect_financial_data_cash_flow_resolution_and_fcf(self):
        """CF 取得：年度別欠損時の0000フォールバック、capex負値・正値でのFCF計算、欠損時Noneを検証"""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector, storage = self._make_isolated_collector(tmpdir)

            bs_2024 = {
                "item": {
                    "7203": ["2024/03", "1000000", "500000", "450000", "300000", "10000", "20000", "2000.0", "45.0"],
                    "6758": ["2024/03", "900000", "400000", "350000", "200000", "5000", "10000", "1500.0", "40.0"],
                    "9984": ["2024/03", "800000", "300000", "250000", "150000", "5000", "10000", "1200.0", "35.0"],
                }
            }
            pl_2024 = {
                "item": {
                    "7203": ["2024/03", "100000", "15000", "16000", "10000", "100.0", "12.0", "5.0"],
                    "6758": ["2024/03", "80000", "12000", "13000", "8000", "80.0", "10.0", "4.0"],
                    "9984": ["2024/03", "60000", "9000", "9500", "6000", "60.0", "8.0", "3.0"],
                }
            }
            # 年度別 CF は 6758 のみ持つ（capex が正値で格納されているケースをテスト）
            cf_2024 = {
                "meta": {"type": "CF"},
                "item": {
                    "6758": ["2024/03", "12000", "-4000", "-3000", "2500", "50000", "15.0"],
                },
            }
            # 最新期 CF (0000): 7203 は capex が負値（IR BANK 実データ準拠）、9984 は capex 欠損 "-"
            # 6758 も 0000 にあるが、年度別 0024 が優先されること
            cf_0000 = {
                "meta": {"type": "CF"},
                "item": {
                    "7203": ["2024/03", "10000", "-3000", "-2000", "-2000", "40000", "10.5"],
                    "6758": ["2024/03", "99999", "-9999", "-9999", "-9999", "99999", "99.9"],
                    "9984": ["2024/03", "8000", "-1000", "500", "-", "20000", "nan"],
                },
            }
            (storage.financial_dir / "0024-fy-balance-sheet.json").write_text(json.dumps(bs_2024), encoding="utf-8")
            (storage.financial_dir / "0024-fy-profit-and-loss.json").write_text(json.dumps(pl_2024), encoding="utf-8")
            (storage.financial_dir / "0024-fy-cash-flow-statement.json").write_text(json.dumps(cf_2024), encoding="utf-8")
            (storage.financial_dir / "0000-fy-cash-flow-statement.json").write_text(json.dumps(cf_0000), encoding="utf-8")

            # 1) 7203: 年度別不在 -> 0000 フォールバック、capex=-2000 -> FCF = 10000 - abs(-2000) = 8000
            fin_7203 = collector.collect_financial_data(
                "7203.T",
                fiscal_year=2024,
                as_of_date=date(2024, 9, 30),
                allow_download=False,
                latest_close=1000.0,
                read_only=True,
            )
            self.assertIsNotNone(fin_7203)
            self.assertEqual(fin_7203.operating_cf, 10000.0)
            self.assertEqual(fin_7203.investing_cf, -3000.0)
            self.assertEqual(fin_7203.financing_cf, -2000.0)
            self.assertEqual(fin_7203.capex, -2000.0)
            self.assertEqual(fin_7203.free_cash_flow, 8000.0)
            self.assertEqual(fin_7203.cash_and_equivalents, 40000.0)
            self.assertEqual(fin_7203.operating_cf_margin, 10.5)

            # 2) 6758: 年度別優先、capex=2500（正値）でも FCF = 12000 - abs(2500) = 9500
            fin_6758 = collector.collect_financial_data(
                "6758.T",
                fiscal_year=2024,
                as_of_date=date(2024, 9, 30),
                allow_download=False,
                latest_close=1000.0,
                read_only=True,
            )
            self.assertIsNotNone(fin_6758)
            self.assertEqual(fin_6758.operating_cf, 12000.0)
            self.assertEqual(fin_6758.capex, 2500.0)
            self.assertEqual(fin_6758.free_cash_flow, 9500.0)
            self.assertEqual(fin_6758.operating_cf_margin, 15.0)

            # 3) 9984: capex="-" のため free_cash_flow は None、operating_cf_margin="nan" も None
            fin_9984 = collector.collect_financial_data(
                "9984.T",
                fiscal_year=2024,
                as_of_date=date(2024, 9, 30),
                allow_download=False,
                latest_close=1000.0,
                read_only=True,
            )
            self.assertIsNotNone(fin_9984)
            self.assertEqual(fin_9984.operating_cf, 8000.0)
            self.assertIsNone(fin_9984.capex)
            self.assertIsNone(fin_9984.free_cash_flow)
            self.assertIsNone(fin_9984.operating_cf_margin)

    def test_collect_financial_data_cf_and_dividend_lookahead_and_type_guard(self):
        """CF / 配当の未来決算・未開示データ・meta.type 不一致が無視されることを検証"""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector, storage = self._make_isolated_collector(tmpdir)

            # 2025/03 は 2025-05-15 時点で未開示 -> 2024/03 (adopted_year=2024, fiscal_date=2024-03-31) を採用する状況
            bs_2025 = {"item": {"7203": ["2025/03", "1100000", "0", "0", "0", "0", "0", "2200.0", "46.0"]}}
            pl_2025 = {"item": {"7203": ["2025/03", "110000", "16000", "17000", "11000", "110.0", "13.0", "5.5"]}}
            bs_2024 = {"item": {"7203": ["2024/03", "1000000", "0", "0", "0", "0", "0", "2000.0", "45.0"]}}
            pl_2024 = {"item": {"7203": ["2024/03", "100000", "15000", "16000", "10000", "100.0", "12.0", "5.0"]}}

            # Case A: 0000 CF / 0000 配当に未来期 2025/03 が入っている -> fiscal_date (2024-03-31) と不一致のため遮断
            cf_0000_future = {
                "meta": {"type": "CF"},
                "item": {"7203": ["2025/03", "99999", "-1000", "-1000", "-500", "88888", "25.0"]},
            }
            div_0000_future = {
                "meta": {"type": "配当"},
                "item": {"7203": ["2025/03", "150.0", "15000", "5000", "35.0", "50.0", "3.0"]},
            }
            # 過去期 0023 配当にもし同日(2024/03)が誤混入していた場合も upper_bound により弾かれる
            div_2023_dup = {
                "meta": {"type": "配当"},
                "item": {"7203": ["2024/03", "100.0", "10000", "2000", "30.0", "40.0", "2.5"]},
            }
            # Case B: 0024 配当が meta.type 不一致 ("PL") -> 無視されること
            div_2024_wrong_type = {
                "meta": {"type": "PL"},
                "item": {"7203": ["2024/03", "120.0", "12000", "3000", "31.0", "41.0", "2.6"]},
            }
            # Case C: 0024 CF が meta.type 不一致 ("配当") -> 無視され 0000 へフォールバック（それも未来期なので最終的に None）
            cf_2024_wrong_type = {
                "meta": {"type": "配当"},
                "item": {"7203": ["2024/03", "10000", "-2000", "-1000", "-1000", "30000", "10.0"]},
            }

            (storage.financial_dir / "0025-fy-balance-sheet.json").write_text(json.dumps(bs_2025), encoding="utf-8")
            (storage.financial_dir / "0025-fy-profit-and-loss.json").write_text(json.dumps(pl_2025), encoding="utf-8")
            (storage.financial_dir / "0024-fy-balance-sheet.json").write_text(json.dumps(bs_2024), encoding="utf-8")
            (storage.financial_dir / "0024-fy-profit-and-loss.json").write_text(json.dumps(pl_2024), encoding="utf-8")
            (storage.financial_dir / "0024-fy-cash-flow-statement.json").write_text(
                json.dumps(cf_2024_wrong_type), encoding="utf-8"
            )
            (storage.financial_dir / "0000-fy-cash-flow-statement.json").write_text(
                json.dumps(cf_0000_future), encoding="utf-8"
            )
            (storage.financial_dir / "0024-fy-stock-dividend.json").write_text(
                json.dumps(div_2024_wrong_type), encoding="utf-8"
            )
            (storage.financial_dir / "0000-fy-stock-dividend.json").write_text(
                json.dumps(div_0000_future), encoding="utf-8"
            )
            (storage.financial_dir / "0023-fy-stock-dividend.json").write_text(
                json.dumps(div_2023_dup), encoding="utf-8"
            )

            fin = collector.collect_financial_data(
                "7203.T",
                fiscal_year=2025,
                as_of_date=date(2025, 5, 15),
                disclosure_lag_days=60,
                allow_download=False,
                latest_close=1000.0,
                read_only=True,
            )
            self.assertIsNotNone(fin)
            self.assertEqual(fin.fiscal_date, date(2024, 3, 31))
            # CF は型不一致 & 未来期によりすべて None
            self.assertIsNone(fin.operating_cf)
            self.assertIsNone(fin.free_cash_flow)
            self.assertIsNone(fin.operating_cf_margin)
            # 配当も型不一致 & 未来期 & 同日付異常によりすべて None
            self.assertIsNone(fin.dividend_per_share)
            self.assertIsNone(fin.total_dividends)
            self.assertIsNone(fin.share_buyback)
            self.assertIsNone(fin.consecutive_dividend_increase_years)
            self.assertIsNone(fin.consecutive_non_decrease_years)
            self.assertIsNone(fin.buyback_count_3y)

            # さらに、disclosure_lag_days 未満の未開示データのみが存在する場合も個別メソッドで遮断されることを直接確認
            with tempfile.TemporaryDirectory() as tmpdir_unreleased:
                collector_unrel, storage_unrel = self._make_isolated_collector(tmpdir_unreleased)
                (storage_unrel.financial_dir / "0025-fy-cash-flow-statement.json").write_text(
                    json.dumps(cf_0000_future), encoding="utf-8"
                )
                cf_unreleased = collector_unrel._resolve_cash_flow_entry(
                    code="7203",
                    adopted_year=2025,
                    fiscal_date=date(2025, 3, 31),
                    as_of_date=date(2025, 5, 15),
                    disclosure_lag_days=60,
                    allow_download=False,
                    read_only=True,
                )
                self.assertIsNone(cf_unreleased)

                (storage_unrel.financial_dir / "0025-fy-stock-dividend.json").write_text(
                    json.dumps(div_0000_future), encoding="utf-8"
                )
                div_unreleased = collector_unrel._collect_dividend_metrics(
                    code="7203",
                    adopted_year=2025,
                    fiscal_date=date(2025, 3, 31),
                    as_of_date=date(2025, 5, 15),
                    disclosure_lag_days=60,
                    allow_download=False,
                    read_only=True,
                )
                self.assertIsNone(div_unreleased["dividend_per_share"])
                self.assertIsNone(div_unreleased["buyback_count_3y"])

    def test_collect_financial_data_dividend_history_and_momentum(self):
        """配当履歴・連続増配/連続非減配（横ばい含む）・直近3期自社株買い・株式分割補正を検証"""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector, storage = self._make_isolated_collector(tmpdir)

            bs_2025 = {
                "item": {
                    "1001": ["2025/03", "100000", "0", "0", "0", "0", "0", "1000.0", "40.0"],  # 横ばい含む非減配 + 自社株買い2回 + 0000フォールバック
                    "1002": ["2025/03", "100000", "0", "0", "0", "0", "0", "1000.0", "40.0"],  # 連続増配 + 自社株買い3回
                    "1003": ["2025/03", "100000", "0", "0", "0", "0", "0", "1000.0", "40.0"],  # 株式分割（見かけ半減だが配当総額維持）
                    "1004": ["2025/03", "100000", "0", "0", "0", "0", "0", "1000.0", "40.0"],  # 株式分割＋総配当増配
                    "1005": ["2025/03", "100000", "0", "0", "0", "0", "0", "1000.0", "40.0"],  # 実減配（総配当も半減）
                    "1006": ["2025/03", "100000", "0", "0", "0", "0", "0", "1000.0", "40.0"],  # 無配継続 (0 -> 0)
                    "1007": ["2025/03", "100000", "0", "0", "0", "0", "0", "1000.0", "40.0"],  # 前年比較不可（当期のみ）
                    "1008": ["2025/03", "100000", "0", "0", "0", "0", "0", "1000.0", "40.0"],  # 当期欠損だが直近3期に過去期自社株買いあり
                }
            }
            pl_2025 = {
                "item": {
                    code: ["2025/03", "50000", "5000", "5200", "3500", "100.0", "10.0", "5.0"]
                    for code in bs_2025["item"]
                }
            }
            (storage.financial_dir / "0025-fy-balance-sheet.json").write_text(json.dumps(bs_2025), encoding="utf-8")
            (storage.financial_dir / "0025-fy-profit-and-loss.json").write_text(json.dumps(pl_2025), encoding="utf-8")

            # 年度別配当データ（1001 は 0025 に存在せず 0000 へフォールバックさせる）
            div_by_year = {
                2025: {
                    "meta": {"type": "配当"},
                    "item": {
                        "1002": ["2025/03", "130.0", "13000", "500", "30.0", "45.0", "3.0"],
                        "1003": ["2025/03", "50.0", "10000", "0", "25.0", "25.0", "2.0"],
                        "1004": ["2025/03", "55.0", "11000", "-", "28.0", "28.0", "2.2"],
                        "1005": ["2025/03", "50.0", "5000", "0", "20.0", "20.0", "1.5"],
                        "1006": ["2025/03", "0", "0", "0", "0", "0", "0"],
                        "1007": ["2025/03", "80.0", "8000", "0", "25.0", "25.0", "2.0"],
                    },
                },
                0: {
                    "meta": {"type": "配当"},
                    "item": {
                        "1001": ["2025/03", "100.0", "10000", "1200", "32.0", "48.0", "2.8"],
                    },
                },
                2024: {
                    "meta": {"type": "配当"},
                    "item": {
                        "1001": ["2024/03", "100.0", "10000", "0"],
                        "1002": ["2024/03", "120.0", "12000", "400"],
                        "1003": ["2024/03", "100.0", "10000", "0"],
                        "1004": ["2024/03", "100.0", "10000", "0"],
                        "1005": ["2024/03", "100.0", "10000", "0"],
                        "1006": ["2024/03", "0", "0", "0"],
                        "1008": ["2024/03", "60.0", "6000", "300"],
                    },
                },
                2023: {
                    "meta": {"type": "配当"},
                    "item": {
                        "1001": ["2023/03", "90.0", "9000", "800"],
                        "1002": ["2023/03", "110.0", "11000", "300"],
                        "1003": ["2023/03", "90.0", "9000", "0"],
                        "1004": ["2023/03", "90.0", "9000", "0"],
                        "1008": ["2023/03", "50.0", "5000", "0"],
                    },
                },
                2022: {
                    "meta": {"type": "配当"},
                    "item": {
                        "1001": ["2022/03", "80.0", "8000", "0"],
                        "1002": ["2022/03", "110.0", "11000", "0"],  # 2023==2022 のため増配はここで止まる
                    },
                },
                2021: {
                    "meta": {"type": "配当"},
                    "item": {
                        "1001": ["2021/03", "85.0", "8500", "0"],  # 2022<2021 なので非減配は3年で止まる
                    },
                },
            }
            for yr, payload in div_by_year.items():
                suffix = "0000" if yr == 0 else f"00{str(yr)[-2:]}"
                (storage.financial_dir / f"{suffix}-fy-stock-dividend.json").write_text(
                    json.dumps(payload), encoding="utf-8"
                )

            as_of = date(2025, 9, 30)
            # 1001: 0000 フォールバック、2025(100)==2024(100)>2023(90)>2022(80)<2021(85)
            # -> 連続増配=0, 連続非減配=3, buyback_count_3y=2 (2025:1200, 2023:800)
            f1001 = collector.collect_financial_data(
                "1001.T", fiscal_year=2025, as_of_date=as_of, allow_download=False, latest_close=1000.0, read_only=True
            )
            self.assertEqual(f1001.dividend_per_share, 100.0)
            self.assertEqual(f1001.total_dividends, 10000.0)
            self.assertEqual(f1001.share_buyback, 1200.0)
            self.assertEqual(f1001.payout_ratio, 32.0)
            self.assertEqual(f1001.total_payout_ratio, 48.0)
            self.assertEqual(f1001.doe, 2.8)
            self.assertEqual(f1001.consecutive_dividend_increase_years, 0)
            self.assertEqual(f1001.consecutive_non_decrease_years, 3)
            self.assertEqual(f1001.buyback_count_3y, 2)

            # 1002: 2025(130)>2024(120)>2023(110)==2022(110)
            # -> 連続増配=2, 連続非減配=3, buyback_count_3y=3
            f1002 = collector.collect_financial_data(
                "1002.T", fiscal_year=2025, as_of_date=as_of, allow_download=False, latest_close=1000.0, read_only=True
            )
            self.assertEqual(f1002.consecutive_dividend_increase_years, 2)
            self.assertEqual(f1002.consecutive_non_decrease_years, 3)
            self.assertEqual(f1002.buyback_count_3y, 3)

            # 1003: 株式分割で dps 100 -> 50 だが total 10000 -> 10000 維持（さらに 2024>2023）
            # -> 連続増配=0, 連続非減配=2
            f1003 = collector.collect_financial_data(
                "1003.T", fiscal_year=2025, as_of_date=as_of, allow_download=False, latest_close=1000.0, read_only=True
            )
            self.assertEqual(f1003.consecutive_dividend_increase_years, 0)
            self.assertEqual(f1003.consecutive_non_decrease_years, 2)

            # 1004: 株式分割で dps 100 -> 55 だが total 10000 -> 11000 増加（2024>2023）
            # -> 連続増配=2, 連続非減配=2
            f1004 = collector.collect_financial_data(
                "1004.T", fiscal_year=2025, as_of_date=as_of, allow_download=False, latest_close=1000.0, read_only=True
            )
            self.assertEqual(f1004.consecutive_dividend_increase_years, 2)
            self.assertEqual(f1004.consecutive_non_decrease_years, 2)

            # 1005: 実減配 (dps 100->50, total 10000->5000) -> 連続増配=0, 連続非減配=0
            f1005 = collector.collect_financial_data(
                "1005.T", fiscal_year=2025, as_of_date=as_of, allow_download=False, latest_close=1000.0, read_only=True
            )
            self.assertEqual(f1005.consecutive_dividend_increase_years, 0)
            self.assertEqual(f1005.consecutive_non_decrease_years, 0)

            # 1006: 無配継続 (0 -> 0) -> 連続増配=0, 連続非減配=0 (curr_val > 0 ガード)
            f1006 = collector.collect_financial_data(
                "1006.T", fiscal_year=2025, as_of_date=as_of, allow_download=False, latest_close=1000.0, read_only=True
            )
            self.assertEqual(f1006.consecutive_dividend_increase_years, 0)
            self.assertEqual(f1006.consecutive_non_decrease_years, 0)

            # 1007: 当期のみ -> 連続増配=None, 連続非減配=None, buyback_count_3y=0
            f1007 = collector.collect_financial_data(
                "1007.T", fiscal_year=2025, as_of_date=as_of, allow_download=False, latest_close=1000.0, read_only=True
            )
            self.assertIsNone(f1007.consecutive_dividend_increase_years)
            self.assertIsNone(f1007.consecutive_non_decrease_years)
            self.assertEqual(f1007.buyback_count_3y, 0)

            # 1008: 当期欠損だが 2024 に自社株買いあり -> 連続系は None, buyback_count_3y=1
            f1008 = collector.collect_financial_data(
                "1008.T", fiscal_year=2025, as_of_date=as_of, allow_download=False, latest_close=1000.0, read_only=True
            )
            self.assertIsNone(f1008.dividend_per_share)
            self.assertIsNone(f1008.consecutive_dividend_increase_years)
            self.assertIsNone(f1008.consecutive_non_decrease_years)
            self.assertEqual(f1008.buyback_count_3y, 1)

    def test_collect_financial_data_cf_and_dividend_read_only_and_no_download(self):
        """read_only=True / allow_download=False 時に CF・配当ファイルで DL や破損JSON削除が呼ばれないことを検証"""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector, storage = self._make_isolated_collector(tmpdir)

            bs_2024 = {"item": {"7203": ["2024/03", "1000000", "500000", "450000", "300000", "10000", "20000", "2000.0", "45.0"]}}
            pl_2024 = {"item": {"7203": ["2024/03", "100000", "15000", "16000", "10000", "100.0", "12.0", "5.0"]}}
            (storage.financial_dir / "0024-fy-balance-sheet.json").write_text(json.dumps(bs_2024), encoding="utf-8")
            (storage.financial_dir / "0024-fy-profit-and-loss.json").write_text(json.dumps(pl_2024), encoding="utf-8")

            corrupt_cf = storage.financial_dir / "0000-fy-cash-flow-statement.json"
            corrupt_div = storage.financial_dir / "0024-fy-stock-dividend.json"
            corrupt_cf.write_text("{corrupt cf", encoding="utf-8")
            corrupt_div.write_text("{corrupt div", encoding="utf-8")

            # 1) read_only=True（allow_download=True を渡しても DL・破損削除しない）
            with patch.object(collector, "_download_irbank_file") as mock_dl:
                fin_ro = collector.collect_financial_data(
                    "7203.T",
                    fiscal_year=2024,
                    as_of_date=date(2024, 9, 30),
                    allow_download=True,
                    latest_close=1000.0,
                    read_only=True,
                )
            self.assertIsNotNone(fin_ro)
            self.assertIsNone(fin_ro.operating_cf)
            self.assertIsNone(fin_ro.dividend_per_share)
            mock_dl.assert_not_called()
            self.assertTrue(corrupt_cf.exists())
            self.assertTrue(corrupt_div.exists())

            # 2) allow_download=False（ファイル未存在状態でも DL しない）
            corrupt_cf.unlink()
            corrupt_div.unlink()
            collector._irbank_json_cache.clear()
            collector._irbank_failed_downloads.clear()

            with patch.object(collector, "_download_irbank_file") as mock_dl:
                fin_nodl = collector.collect_financial_data(
                    "7203.T",
                    fiscal_year=2024,
                    as_of_date=date(2024, 9, 30),
                    allow_download=False,
                    latest_close=1000.0,
                    read_only=False,
                )
            self.assertIsNotNone(fin_nodl)
            mock_dl.assert_not_called()

    def test_collect_financial_data_dividend_requires_exact_fiscal_date_for_current_year(self):
        """当期年度別配当の決算期が fiscal_date と異なる旧期の場合は無視し、0000一致採用または None とする"""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector, storage = self._make_isolated_collector(tmpdir)

            bs_2025 = {
                "item": {
                    "2001": ["2025/03", "100000", "0", "0", "0", "0", "0", "1000.0", "40.0"],
                    "2002": ["2025/03", "100000", "0", "0", "0", "0", "0", "1000.0", "40.0"],
                }
            }
            pl_2025 = {
                "item": {
                    "2001": ["2025/03", "50000", "5000", "5200", "3500", "100.0", "10.0", "5.0"],
                    "2002": ["2025/03", "50000", "5000", "5200", "3500", "100.0", "10.0", "5.0"],
                }
            }
            # 0025 配当には両銘柄とも旧決算期 (2024/12) が入っている
            div_2025_old_period = {
                "meta": {"type": "配当"},
                "item": {
                    "2001": ["2024/12", "40.0", "4000", "0", "20.0", "20.0", "1.5"],
                    "2002": ["2024/12", "50.0", "5000", "100", "22.0", "25.0", "1.8"],
                },
            }
            # 0000 配当: 2001 は 2025/03 一致データあり、2002 は 2024/12 のみで一致データなし
            div_0000 = {
                "meta": {"type": "配当"},
                "item": {
                    "2001": ["2025/03", "120.0", "12000", "500", "35.0", "45.0", "3.0"],
                    "2002": ["2024/12", "50.0", "5000", "100", "22.0", "25.0", "1.8"],
                },
            }
            (storage.financial_dir / "0025-fy-balance-sheet.json").write_text(json.dumps(bs_2025), encoding="utf-8")
            (storage.financial_dir / "0025-fy-profit-and-loss.json").write_text(json.dumps(pl_2025), encoding="utf-8")
            (storage.financial_dir / "0025-fy-stock-dividend.json").write_text(
                json.dumps(div_2025_old_period), encoding="utf-8"
            )
            (storage.financial_dir / "0000-fy-stock-dividend.json").write_text(json.dumps(div_0000), encoding="utf-8")

            as_of = date(2025, 9, 30)
            # 1) 0025 が旧決算期でも、0000 に 2025/03 一致データがあれば 0000 側を採用する
            fin_2001 = collector.collect_financial_data(
                "2001.T", fiscal_year=2025, as_of_date=as_of, allow_download=False, latest_close=1000.0, read_only=True
            )
            self.assertIsNotNone(fin_2001)
            self.assertEqual(fin_2001.dividend_per_share, 120.0)
            self.assertEqual(fin_2001.total_dividends, 12000.0)
            self.assertEqual(fin_2001.share_buyback, 500.0)
            self.assertEqual(fin_2001.payout_ratio, 35.0)
            self.assertEqual(fin_2001.total_payout_ratio, 45.0)
            self.assertEqual(fin_2001.doe, 3.0)
            self.assertEqual(fin_2001.buyback_count_3y, 1)

            # 2) 0025 にも 0000 にも 2025/03 一致データが無ければ旧期データを誤採用せず None とする
            fin_2002 = collector.collect_financial_data(
                "2002.T", fiscal_year=2025, as_of_date=as_of, allow_download=False, latest_close=1000.0, read_only=True
            )
            self.assertIsNotNone(fin_2002)
            self.assertIsNone(fin_2002.dividend_per_share)
            self.assertIsNone(fin_2002.total_dividends)
            self.assertIsNone(fin_2002.share_buyback)
            self.assertIsNone(fin_2002.payout_ratio)
            self.assertIsNone(fin_2002.total_payout_ratio)
            self.assertIsNone(fin_2002.doe)
            self.assertIsNone(fin_2002.consecutive_dividend_increase_years)
            self.assertIsNone(fin_2002.consecutive_non_decrease_years)
            self.assertIsNone(fin_2002.buyback_count_3y)

    def test_collect_benchmark_ohlcv_and_failure_fallback(self):
        """collect_benchmark_ohlcv が基準日分離して取得でき、失敗時は例外にせず空リストへフォールバックする"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            collector = DataCollector(storage=storage)
            df = pd.DataFrame(
                [
                    {
                        "date": date(2025, 1, 6),
                        "open": 2500.0,
                        "high": 2520.0,
                        "low": 2490.0,
                        "close": 2510.0,
                        "volume": 500_000,
                    },
                    {
                        "date": date(2025, 1, 7),
                        "open": 2510.0,
                        "high": 2530.0,
                        "low": 2500.0,
                        "close": 2525.0,
                        "volume": 520_000,
                    },
                ]
            )
            storage.save_parquet(df, "price/1306.T.parquet")

            bars = collector.collect_benchmark_ohlcv(
                date(2025, 1, 6),
                date(2025, 1, 7),
                as_of_date=date(2025, 1, 6),
                read_only=True,
            )
            self.assertEqual(len(bars), 1)
            self.assertEqual(bars[0].symbol, "1306.T")
            self.assertEqual(bars[0].date, date(2025, 1, 6))

            with patch.object(
                collector, "collect_ohlcv_data", side_effect=RuntimeError("network error")
            ):
                fallback = collector.collect_benchmark_ohlcv(
                    date(2025, 1, 6),
                    date(2025, 1, 7),
                )
            self.assertEqual(fallback, [])

if __name__ == '__main__':
    unittest.main()
