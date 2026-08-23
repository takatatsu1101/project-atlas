
import unittest
from datetime import date
from unittest.mock import patch, MagicMock
import pandas as pd

from src.data_collector.collector import DataCollector, collect_ohlcv_data, collect_financial_data
from src.model.data_models import OhlcvModel, FinancialModel

class TestDataCollector(unittest.TestCase):

    def setUp(self):
        self.collector = DataCollector()
        self.symbol = "1234.T"
        self.start_date = date(2025, 1, 1)
        self.end_date = date(2025, 1, 5)
        self.mock_df_data = {
            "Date": [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 4), date(2025, 1, 5)],
            "Open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "High": [105.0, 106.0, 107.0, 108.0, 109.0],
            "Low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "Close": [104.0, 105.0, 106.0, 107.0, 108.0],
            "Volume": [1000, 1100, 1200, 1300, 1400]
        }

    @patch("yfinance.Ticker")
    def test_collect_ohlcv_data_success(self, mock_ticker):
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.history.return_value = pd.DataFrame(self.mock_df_data).set_index("Date")

        ohlcv_list = self.collector.collect_ohlcv_data(self.symbol, self.start_date, self.end_date)
        
        self.assertIsInstance(ohlcv_list, list)
        self.assertEqual(len(ohlcv_list), 5)
        self.assertIsInstance(ohlcv_list[0], OhlcvModel)
        self.assertEqual(ohlcv_list[0].symbol, self.symbol)
        self.assertEqual(ohlcv_list[0].date, date(2025, 1, 1))
        self.assertEqual(ohlcv_list[0].close, 104.0)

    @patch("yfinance.Ticker")
    def test_collect_ohlcv_data_empty(self, mock_ticker):
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        mock_instance.history.return_value = pd.DataFrame() # 空のDataFrameを返す

        ohlcv_list = self.collector.collect_ohlcv_data(self.symbol, self.start_date, self.end_date)
        self.assertEqual(len(ohlcv_list), 0)

    def test_collect_financial_data(self):
        financial_data = self.collector.collect_financial_data(self.symbol, 2025)
        
        self.assertIsInstance(financial_data, FinancialModel)
        self.assertEqual(financial_data.symbol, self.symbol)
        self.assertEqual(financial_data.fiscal_date, date(2025, 3, 31)) # ダミーデータの日付
        self.assertIsNotNone(financial_data.eps)
        self.assertIsNotNone(financial_data.roe)

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
