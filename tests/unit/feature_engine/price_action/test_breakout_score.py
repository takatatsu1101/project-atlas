import unittest
from datetime import date

from src.feature_engine.features.price_action.breakout_score import BreakoutScore
from src.model.data_models import OhlcvModel, IndicatorSetModel

class TestBreakoutScore(unittest.TestCase):

    def setUp(self):
        self.feature = BreakoutScore()
        self.symbol = "TEST"

        # 過去20日間のOHLCVデータをモック（すべて高値100、終値100、安値100）
        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=100, low=100, close=100, volume=100)
            for d in range(1, 22) # 21日間
        ]
        # インジケータデータ
        self.indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, d), indicators={})
            for d in range(1, 22)
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "P002_BreakoutScore")
        self.assertEqual(self.feature.feature_name, "ブレイクアウト評価")
        self.assertEqual(self.feature.feature_category, "PriceAction")

    def test_insufficient_data(self):
        # 過去データが最小基準（5日）に満たない場合
        # インデックス4（5日目）は過去4日分しかないのでデータ不足で30.0を期待
        results = self.feature.calculate(self.ohlcv_data[:5], self.indicator_data[:5])
        self.assertEqual(results[4].score, 30.0)

    def test_healthy_breakout(self):
        # パターンA-1: 健全な上抜け初動 (0%〜5%の範囲)
        # 21日目（インデックス20）の計算：過去20日間の最高値は100.0
        # 今日の終値を102.5とする。上抜け率 2.5% -> スコア 95.0
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=100, high=103, low=100, close=102.5, volume=100)
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertAlmostEqual(results[20].score, 95.0, places=4)

    def test_late_breakout(self):
        # パターンA-2: 強いブレイク（少し買い遅れ、5%超〜15%以下）
        # 過去最高値 100.0
        # 今日の終値を110.0とする。上抜け率 10.0% -> スコア 80.0
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=100, high=111, low=100, close=110.0, volume=100)
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertAlmostEqual(results[20].score, 80.0, places=4)

    def test_overheated_breakout(self):
        # パターンA-3: 急騰しすぎ、高値掴み警戒 (> 15%)
        # 過去最高値 100.0
        # 今日の終値を120.0とする。上抜け率 20.0% -> スコア 50.0
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=100, high=121, low=100, close=120.0, volume=100)
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertEqual(results[20].score, 50.0)

    def test_near_breakout(self):
        # パターンB-1: ブレイク目前 (2%以内の近さ)
        # 過去最高値 100.0
        # 今日の終値を99.0とする。距離 1.0% -> スコア 80.0
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=100, high=100, low=98, close=99.0, volume=100)
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertAlmostEqual(results[20].score, 80.0, places=4)

    def test_range_breakout_shoot_zone(self):
        # パターンB-2: 射程圏内 (2%超〜5%以下)
        # 過去最高値 100.0
        # 今日の終値を96.5とする。距離 3.5% -> スコア 60.0
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=100, high=98, low=95, close=96.5, volume=100)
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertAlmostEqual(results[20].score, 60.0, places=4)

    def test_far_from_breakout(self):
        # パターンB-3: まだ遠い (5%を超える距離)
        # 過去最高値 100.0
        # 今日の終値を92.5とする。距離 7.5% -> スコア 35.0
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=100, high=95, low=90, close=92.5, volume=100)
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertAlmostEqual(results[20].score, 35.0, places=4)

        # 今日の終値を85.0とする。距離 15.0% (> 10%) -> スコア 20.0
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=100, high=90, low=80, close=85.0, volume=100)
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertEqual(results[20].score, 20.0)

if __name__ == '__main__':
    unittest.main()
