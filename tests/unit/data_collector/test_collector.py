import unittest
from datetime import date
from unittest.mock import patch, MagicMock
import pandas as pd
import os

from src.data_collector.collector import DataCollector, collect_ohlcv_data, collect_financial_data
from src.model.data_models import OhlcvModel, FinancialModel

class TestDataCollector(unittest.TestCase):

    def setUp(self):
        self.collector = DataCollector()
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
        def side_effect(year, fy_type):
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

if __name__ == '__main__':
    unittest.main()
