import unittest
from datetime import date

from src.pattern_detector.patterns.reversal.double_top import DoubleTopPattern
from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternResultModel

class TestDoubleTopPattern(unittest.TestCase):

    def setUp(self):
        self.pattern_detector = DoubleTopPattern()
        self.symbol = "TEST"

    def test_pattern_properties(self):
        self.assertEqual(self.pattern_detector.pattern_id, "R002_DoubleTop")
        self.assertEqual(self.pattern_detector.pattern_name, "ダブルトップ")
        self.assertEqual(self.pattern_detector.pattern_category, "Reversal")

    def test_detect_valid_double_top(self):
        # 典型的なダブルトップが形成される16日分のOHLCVデータを構成
        # 1〜3日：上昇
        # 4日目：山1（高値120.0）
        # 5〜7日：一時下落
        # 8日目：ネックライン（安値100.0）
        # 9〜11日：再び上昇
        # 12日目：山2（高値119.5。山1から0.4%の差）
        # 13〜15日：下落
        # 16日目：ネックライン下抜け（終値98.0）
        prices = [
            (100, 102, 98, 101),   # 1
            (105, 108, 103, 107),  # 2
            (110, 115, 108, 114),  # 3
            (115, 120, 114, 118),  # 4 (山1: index 3)
            (112, 115, 108, 110),  # 5
            (105, 108, 102, 104),  # 6
            (101, 104, 100, 102),  # 7
            (100, 102, 100, 101),  # 8 (ネック: index 7)
            (103, 108, 102, 107),  # 9
            (110, 114, 108, 113),  # 10
            (114, 118, 112, 117),  # 11
            (116, 119.5, 115, 117),# 12 (山2: index 11)
            (112, 115, 108, 110),  # 13
            (105, 108, 102, 104),  # 14
            (101, 103, 99, 100),   # 15
            (99, 100, 95, 98.0),   # 16 (終値 98.0 < ネック安 100.0 下抜け!)
        ]

        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, idx+1), open=p[0], high=p[1], low=p[2], close=p[3], volume=1000)
            for idx, p in enumerate(prices)
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=d.date, indicators={}) for d in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        self.assertGreaterEqual(len(results), 1)
        # 16日目（最後のデータ）で検知されることを確認
        self.assertEqual(results[-1].metadata["date"], date(2025, 1, 16))
        self.assertGreaterEqual(results[-1].confidence, 80.0) # 下抜け直後なので非常に高信頼度

    def test_detect_forming_double_top(self):
        # 形成途中（ネックラインに届いていないが、山2から下落中）
        # 山1: 120, ネック安: 100, 山2: 119.5, 終値: 110.0 (下落中)
        prices = [
            (100, 102, 98, 101),   # 1
            (105, 108, 103, 107),  # 2
            (110, 115, 108, 114),  # 3
            (115, 120, 114, 118),  # 4 (山1: index 3)
            (112, 115, 108, 110),  # 5
            (105, 108, 102, 104),  # 6
            (101, 104, 100, 102),  # 7
            (100, 102, 100, 101),  # 8 (ネック: index 7)
            (103, 108, 102, 107),  # 9
            (110, 114, 108, 113),  # 10
            (114, 118, 112, 117),  # 11
            (116, 119.5, 115, 117),# 12 (山2: index 11)
            (113, 117, 112, 115),  # 13
            (111, 114, 108, 112),  # 14
            (108, 111, 106, 110.0),# 15 (終値 110.0 で下落中。index 14)
        ]

        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, idx+1), open=p[0], high=p[1], low=p[2], close=p[3], volume=1000)
            for idx, p in enumerate(prices)
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=d.date, indicators={}) for d in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[-1].metadata["date"], date(2025, 1, 15))
        # ネックラインの上なので、完成よりは信頼度が低い
        self.assertTrue(40.0 <= results[-1].confidence <= 75.0)

    def test_broken_double_top(self):
        # 抵抗線上抜け（山2の高値をさらに上抜けて上昇。不成立）
        prices = [
            (100, 102, 98, 101),   # 1
            (105, 108, 103, 107),  # 2
            (110, 115, 108, 114),  # 3
            (115, 120, 114, 118),  # 4 (山1: index 3)
            (112, 115, 108, 110),  # 5
            (105, 108, 102, 104),  # 6
            (101, 104, 100, 102),  # 7
            (100, 102, 100, 101),  # 8 (ネック)
            (103, 108, 102, 107),  # 9
            (110, 114, 108, 113),  # 10
            (114, 118, 112, 117),  # 11
            (116, 119.5, 115, 117),# 12 (山2)
            (118, 123, 116, 122.0),# 13 (天井 119.5 を上抜けて急騰。不成立)
        ]

        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, idx+1), open=p[0], high=p[1], low=p[2], close=p[3], volume=1000)
            for idx, p in enumerate(prices)
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=d.date, indicators={}) for d in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        # 上抜けした日は検知されない
        if len(results) > 0:
            self.assertNotEqual(results[-1].metadata["date"], date(2025, 1, 13))

    def test_insufficient_data(self):
        # 15日未満のデータ
        results = self.pattern_detector.detect([], [])
        self.assertEqual(len(results), 0)

if __name__ == '__main__':
    unittest.main()
