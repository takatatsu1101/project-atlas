import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import os

from src.common.storage import StorageManager
from src.data_collector.collector import DataCollector, collect_ohlcv_data, collect_financial_data
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
                return bs_2025 if "balance-sheet" in fy_type else pl_2025
            if year == 2024:
                return bs_2024 if "balance-sheet" in fy_type else pl_2024
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
                return bs_2025 if "balance-sheet" in fy_type else pl_2025
            if year == 2024:
                return bs_2024 if "balance-sheet" in fy_type else pl_2024
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
                return bs_2025 if "balance-sheet" in fy_type else pl_2025
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
                return bs_2025 if "balance-sheet" in fy_type else pl_2025
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
        mock_load_json.side_effect = (
            lambda year, fy_type, allow_download=True: (
                (bs_2025 if "balance-sheet" in fy_type else pl_2025) if year == 2025 else None
            )
        )

        with patch("src.data_collector.collector.data_collector.collect_ohlcv_data") as mock_ohlcv:
            fin = collect_financial_data("7203.T", fiscal_year=2025, latest_close=0.0)

        mock_ohlcv.assert_not_called()
        self.assertIsNotNone(fin)
        self.assertEqual(fin.per, 0.0)
        self.assertEqual(fin.pbr, 0.0)

if __name__ == '__main__':
    unittest.main()
