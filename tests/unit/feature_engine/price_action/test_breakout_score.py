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
        # パターンA-1: 健全な上抜け初動 (0%〜5%の範囲) + 高CLV(0.83) + 60日高値ブレイク
        # base=95 + hh60(+8) + clv(+5) -> 100.0 (クリップ)
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=100, high=103, low=100, close=102.5, volume=100)
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertAlmostEqual(results[20].score, 100.0, places=4)
        self.assertEqual(results[20].metadata["highest_high"], 100.0)
        self.assertEqual(results[20].metadata["highest_high_60"], 100.0)
        self.assertAlmostEqual(results[20].metadata["clv"], 2.5 / 3.0, places=4)
        self.assertAlmostEqual(results[20].metadata["gap_pct"], 0.0, places=4)

    def test_upper_wick_fake_breakout_and_gap_up_penalty(self):
        # 上ヒゲだまし (upper_wick_ratio >= 0.4, clv < 0.4) は減点される
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=100, high=110, low=100, close=102.0, volume=100)
        results_wick = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertLess(results_wick[20].score, 85.0)
        self.assertGreaterEqual(results_wick[20].metadata["upper_wick_ratio"], 0.4)

        # 大幅ギャップアップ (gap_pct > 0.07) も過熱減点される
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=110, high=112, low=109, close=111.0, volume=100)
        results_gap = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertGreater(results_gap[20].metadata["gap_pct"], 0.07)
        self.assertLess(results_gap[20].score, 85.0)

    def test_late_breakout(self):
        # パターンA-2: 強いブレイク（少し買い遅れ、5%超〜15%以下）
        # base=80 + hh60(+8) + clv(+5) = 93.0
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=100, high=111, low=100, close=110.0, volume=100)
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertAlmostEqual(results[20].score, 93.0, places=4)

    def test_overheated_breakout(self):
        # パターンA-3: 急騰しすぎ、高値掴み警戒 (> 15%)
        # base=50 + hh60(+8) + clv(+5) = 63.0
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=100, high=121, low=100, close=120.0, volume=100)
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertAlmostEqual(results[20].score, 63.0, places=4)

    def test_near_breakout(self):
        # パターンB-1: ブレイク目前 (2%以内の近さ)
        # base=80 + hh60_near(+3) + clv>=0.6(+5) = 88.0
        self.ohlcv_data[20] = OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=98.5, high=99.3, low=98.5, close=99.0, volume=100)
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        self.assertAlmostEqual(results[20].score, 88.0, places=4)

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

    def test_zero_range_and_zero_prev_close_boundary(self):
        # high == low かつ prev_close == 0 でもゼロ除算せず安全に計算できる
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=0, high=0, low=0, close=0, volume=100)
            for d in range(1, 21)
        ]
        ohlcv.append(OhlcvModel(symbol=self.symbol, date=date(2025, 1, 21), open=100, high=100, low=100, close=100, volume=100))
        results = self.feature.calculate(ohlcv, self.indicator_data)
        self.assertEqual(results[20].score, 30.0)
        self.assertEqual(results[20].metadata["clv"], 0.5)
        self.assertEqual(results[20].metadata["upper_wick_ratio"], 0.0)
        self.assertIsNone(results[20].metadata["gap_pct"])

if __name__ == '__main__':
    unittest.main()
