import unittest
from datetime import date

from src.pattern_detector.patterns.reversal.double_bottom import DoubleBottomPattern
from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternResultModel

class TestDoubleBottomPattern(unittest.TestCase):

    def setUp(self):
        self.pattern_detector = DoubleBottomPattern()
        self.symbol = "TEST"

    def test_pattern_properties(self):
        self.assertEqual(self.pattern_detector.pattern_id, "R001_DoubleBottom")
        self.assertEqual(self.pattern_detector.pattern_name, "ダブルボトム")
        self.assertEqual(self.pattern_detector.pattern_category, "Reversal")

    def test_detect_valid_double_bottom(self):
        # 典型的なダブルボトムが形成される16日分のOHLCVデータを構成
        # 1〜3日：下降
        # 4日目：谷1（底値80.0）
        # 5〜7日：一時反発
        # 8日目：ネックライン（高値100.0）
        # 9〜11日：再び下落
        # 12日目：谷2（底値80.5。谷1から0.6%の差）
        # 13〜15日：反発上昇
        # 16日目：ネックライン上抜け（終値102.0）
        prices = [
            (100, 102, 98, 99),   # 1
            (95, 97, 92, 93),     # 2
            (90, 92, 85, 86),     # 3
            (82, 85, 80, 81),     # 4 (谷1: index 3)
            (85, 90, 84, 88),     # 5
            (90, 95, 88, 93),     # 6
            (95, 98, 93, 96),     # 7
            (98, 100, 95, 97),    # 8 (ネック: index 7)
            (95, 97, 90, 92),     # 9
            (90, 92, 84, 85),     # 10
            (83, 85, 81, 82),     # 11
            (81, 84, 80.5, 83),   # 12 (谷2: index 11)
            (85, 90, 82, 89),     # 13
            (90, 95, 88, 94),     # 14
            (95, 100, 93, 98),    # 15
            (100, 103, 99, 102),  # 16 (終値 102.0 > ネック高 100.0 上抜け!)
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
        self.assertGreaterEqual(results[-1].confidence, 80.0) # 上抜け直後なので非常に高信頼度

    def test_detect_forming_double_bottom(self):
        # 形成途中（ネックラインに届いていないが、谷2から反発中）
        # 谷1: 80, ネック高: 100, 谷2: 80.5, 終値: 90.0 (反発中)
        prices = [
            (100, 102, 98, 99),   # 1
            (95, 97, 92, 93),     # 2
            (90, 92, 85, 86),     # 3
            (82, 85, 80, 81),     # 4 (谷1: index 3)
            (85, 90, 84, 88),     # 5
            (90, 95, 88, 93),     # 6
            (95, 98, 93, 96),     # 7
            (98, 100, 95, 97),    # 8 (ネック: index 7)
            (95, 97, 90, 92),     # 9
            (90, 92, 84, 85),     # 10
            (83, 85, 81, 82),     # 11
            (81, 84, 80.5, 83),   # 12 (谷2: index 11)
            (83, 86, 81, 84),     # 13
            (84, 88, 82, 86),     # 14
            (86, 92, 83, 90.0),   # 15 (終値 90.0 で反発上昇中。index 14)
        ]

        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, idx+1), open=p[0], high=p[1], low=p[2], close=p[3], volume=1000)
            for idx, p in enumerate(prices)
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=d.date, indicators={}) for d in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[-1].metadata["date"], date(2025, 1, 15))
        # ネックラインの下なので、完成よりは信頼度が低い
        self.assertTrue(40.0 <= results[-1].confidence <= 75.0)

    def test_broken_double_bottom(self):
        # サポート割れ（谷2の安値を割り込んで下落）
        prices = [
            (100, 102, 98, 99),   # 1
            (95, 97, 92, 93),     # 2
            (90, 92, 85, 86),     # 3
            (82, 85, 80, 81),     # 4 (谷1: index 3)
            (85, 90, 84, 88),     # 5
            (90, 95, 88, 93),     # 6
            (95, 98, 93, 96),     # 7
            (98, 100, 95, 97),    # 8 (ネック)
            (95, 97, 90, 92),     # 9
            (90, 92, 84, 85),     # 10
            (83, 85, 81, 82),     # 11
            (81, 84, 80.5, 83),   # 12 (谷2)
            (81, 83, 78, 79.0),   # 13 (サポート 80.5 を大きく割り込んで下落。不成立)
        ]

        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, idx+1), open=p[0], high=p[1], low=p[2], close=p[3], volume=1000)
            for idx, p in enumerate(prices)
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=d.date, indicators={}) for d in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        # サポートを割り込んだ日は検知されない
        if len(results) > 0:
            self.assertNotEqual(results[-1].metadata["date"], date(2025, 1, 13))

    def test_insufficient_data(self):
        # 15日未満のデータ
        results = self.pattern_detector.detect(self.ohlcv_data_insufficient if hasattr(self, 'ohlcv_data_insufficient') else [], [])
        self.assertEqual(len(results), 0)

if __name__ == '__main__':
    unittest.main()
