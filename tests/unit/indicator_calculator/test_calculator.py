
import unittest
from datetime import date
import pandas as pd
import numpy as np

from src.indicator_calculator.calculator import IndicatorCalculator, calculate_indicators
from src.model.data_models import OhlcvModel, IndicatorSetModel

class TestIndicatorCalculator(unittest.TestCase):

    def setUp(self):
        self.calculator = IndicatorCalculator()
        self.symbol = "TEST"
        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100.0, high=105.0, low=98.0, close=103.0, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=103.0, high=107.0, low=102.0, close=106.0, volume=1100),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 3), open=106.0, high=110.0, low=105.0, close=109.0, volume=1200),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 4), open=109.0, high=112.0, low=108.0, close=111.0, volume=1300),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 5), open=111.0, high=115.0, low=110.0, close=114.0, volume=1400),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 6), open=114.0, high=118.0, low=113.0, close=117.0, volume=1500),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 7), open=117.0, high=120.0, low=116.0, close=119.0, volume=1600),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 8), open=119.0, high=123.0, low=118.0, close=122.0, volume=1700),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 9), open=122.0, high=125.0, low=121.0, close=124.0, volume=1800),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 10), open=124.0, high=127.0, low=123.0, close=126.0, volume=1900),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 11), open=126.0, high=129.0, low=125.0, close=128.0, volume=2000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 12), open=128.0, high=131.0, low=127.0, close=130.0, volume=2100),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 13), open=130.0, high=133.0, low=129.0, close=132.0, volume=2200),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 14), open=132.0, high=135.0, low=131.0, close=134.0, volume=2300),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 15), open=134.0, high=137.0, low=133.0, close=136.0, volume=2400),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 16), open=136.0, high=139.0, low=135.0, close=138.0, volume=2500),
        ]

    def test_calculate_sma(self):
        sma_5 = self.calculator.calculate_sma(self.ohlcv_data, 5)
        self.assertEqual(len(sma_5), len(self.ohlcv_data))
        # SMAは最初のperiod-1個はNaNになることを確認
        for i in range(4):
            self.assertTrue(np.isnan(sma_5[i]))
        self.assertFalse(np.isnan(sma_5[4]))
        # 期待値との比較 (手動で計算)
        self.assertAlmostEqual(sma_5[4], (103.0 + 106.0 + 109.0 + 111.0 + 114.0) / 5.0)
        self.assertAlmostEqual(sma_5[5], (106.0 + 109.0 + 111.0 + 114.0 + 117.0) / 5.0)

    def test_calculate_rsi(self):
        rsi_14 = self.calculator.calculate_rsi(self.ohlcv_data, 14)
        self.assertEqual(len(rsi_14), len(self.ohlcv_data))
        # RSIの具体的な値は計算が複雑なため、NaNでないことと範囲内であることを確認
        self.assertFalse(np.isnan(rsi_14[-1]))
        self.assertGreaterEqual(rsi_14[-1], 0)
        self.assertLessEqual(rsi_14[-1], 100)

    def test_calculate_macd(self):
        macd_data = self.calculator.calculate_macd(self.ohlcv_data)
        self.assertEqual(len(macd_data), len(self.ohlcv_data))
        self.assertIn("macd", macd_data[-1])
        self.assertIn("signal", macd_data[-1])
        self.assertIn("histogram", macd_data[-1])

    def test_calculate_indicators_integration(self):
        indicator_sets = self.calculator.calculate_indicators(self.ohlcv_data)
        self.assertEqual(len(indicator_sets), len(self.ohlcv_data))
        self.assertIsInstance(indicator_sets[0], IndicatorSetModel)
        self.assertIn("SMA5", indicator_sets[-1].indicators)
        self.assertIn("RSI14", indicator_sets[-1].indicators)
        self.assertIn("MACD", indicator_sets[-1].indicators)

    def test_calculate_indicators_empty_data(self):
        indicator_sets = self.calculator.calculate_indicators([])
        self.assertEqual(len(indicator_sets), 0)

if __name__ == '__main__':
    unittest.main()
