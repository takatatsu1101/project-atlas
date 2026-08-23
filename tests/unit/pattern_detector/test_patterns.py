
import unittest
from datetime import date
from typing import List, Dict, Any
import pandas as pd

from src.pattern_detector.patterns.candlestick import HammerPattern
from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternResultModel

class TestHammerPattern(unittest.TestCase):

    def setUp(self):
        self.pattern_detector = HammerPattern()
        self.symbol = "TEST"

    def test_pattern_properties(self):
        self.assertEqual(self.pattern_detector.pattern_id, "P001_Hammer")
        self.assertEqual(self.pattern_detector.pattern_name, "ハンマー")
        self.assertEqual(self.pattern_detector.pattern_category, "Candlestick")

    def test_detect_valid_hammer(self):
        # 典型的なハンマーパターンデータ
        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=102, low=90, close=101, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=95, high=100, low=80, close=98, volume=1500), # ハンマー
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={}) for _ in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], PatternResultModel)
        self.assertEqual(results[0].pattern_id, self.pattern_detector.pattern_id)
        self.assertGreaterEqual(results[0].confidence, 0)
        self.assertLessEqual(results[0].confidence, 100)
        self.assertEqual(results[0].metadata["date"], date(2025, 1, 2))

    def test_detect_no_hammer(self):
        # ハンマーではないデータ（長い上ヒゲ）
        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=110, low=95, close=101, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=95, high=110, low=96, close=97, volume=1500), # 上ヒゲが長い
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={}) for _ in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        self.assertEqual(len(results), 0)

    def test_detect_inverted_hammer(self):
        # 逆ハンマー（下ヒゲが短い）
        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=110, low=98, close=101, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=95, high=110, low=90, close=97, volume=1500), # 逆ハンマー
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={}) for _ in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        self.assertEqual(len(results), 0) # ハンマーとしては検出されない

    def test_detect_empty_data(self):
        results = self.pattern_detector.detect([], [])
        self.assertEqual(len(results), 0)

    def test_calculate_confidence(self):
        # 理想的なハンマー
        conf1 = self.pattern_detector._calculate_confidence({"body": 1, "lower_shadow": 5, "upper_shadow": 0.1, "open": 100})
        self.assertGreater(conf1, 80)
        
        # 下ヒゲは長いが上ヒゲも少しある
        conf2 = self.pattern_detector._calculate_confidence({"body": 1, "lower_shadow": 3, "upper_shadow": 1, "open": 100})
        self.assertLess(conf2, conf1)
        self.assertGreater(conf2, 50)

        # 実体なし、下ヒゲあり
        conf3 = self.pattern_detector._calculate_confidence({"body": 0, "lower_shadow": 10, "upper_shadow": 0, "open": 100})
        self.assertEqual(conf3, 100.0) # bodyが0でも高信頼度

if __name__ == '__main__':
    unittest.main()
