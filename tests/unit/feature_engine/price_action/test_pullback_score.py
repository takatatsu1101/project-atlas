import unittest
from datetime import date

from src.feature_engine.features.price_action.pullback_score import PullbackScore
from src.model.data_models import OhlcvModel, IndicatorSetModel

class TestPullbackScore(unittest.TestCase):

    def setUp(self):
        self.feature = PullbackScore()
        self.symbol = "TEST"

        # 基本的なOHLCVデータのモック
        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=100, low=100, close=100, volume=0),
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "P001_PullbackScore")
        self.assertEqual(self.feature.feature_name, "押し目評価")
        self.assertEqual(self.feature.feature_category, "PriceAction")

    def test_ideal_pullback_on_sma25_with_rebound_candle(self):
        # パターンA: SMA25の直上 (0%〜3%) + 陽線転換・下ヒゲ・CLV>=0.6・SMA5上抜け
        # base=100 * 0.7 = 70.0 + 30.0 = 100.0
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 99.5, "SMA25": 100, "SMA75": 90}),
        ]
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=99.0, high=100.5, low=95.0, close=100.0, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertAlmostEqual(results[0].score, 100.0, places=4)
        self.assertTrue(results[0].metadata["is_bullish"])
        self.assertTrue(results[0].metadata["above_sma5"])
        self.assertGreaterEqual(results[0].metadata["lower_wick_ratio"], 0.35)
        self.assertGreaterEqual(results[0].metadata["clv"], 0.6)

        # 大陰線・安値引けの場合は減点される (SMA5=102 の下で陰線安値引け -> 70 - 15 = 55.0)
        indicator_bear = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 102.0, "SMA25": 100, "SMA75": 90}),
        ]
        ohlcv_bear = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=105.0, high=105.5, low=100.0, close=100.0, volume=1000)
        ]
        results_bear = self.feature.calculate(ohlcv_bear, indicator_bear)
        self.assertLess(results_bear[0].score, 60.0)
        self.assertFalse(results_bear[0].metadata["is_bullish"])

    def test_deep_pullback_below_sma25(self):
        # パターンB: SMA25をわずかに割り込んでいる (-2%〜0%未満)
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 98, "SMA25": 100, "SMA75": 90}),
        ]
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=98.5, high=99.5, low=98.0, close=99.0, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        # base=70*0.7=49 + 陽線(+10) + above_sma5(+8) + clv=0.667(+5) = 72.0
        self.assertAlmostEqual(results[0].score, 72.0, places=4)

    def test_shallow_pullback_above_sma25(self):
        # パターンC: まだ押し目が浅い (3%を超える上昇継続中)
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 108, "SMA25": 100, "SMA75": 90}),
        ]
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=106.5, high=108.0, low=106.5, close=106.5, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        # base=60*0.7=42 + 0 = 42.0
        self.assertAlmostEqual(results[0].score, 42.0, places=4)

        # 終値 115.0 のとき: 乖離率 15.0% (> 10%) -> base=40*0.7=28.0
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=115.0, high=120.0, low=110.0, close=115.0, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        # base=28 + above_sma5(+8) + lower_wick(+7) = 43.0
        self.assertAlmostEqual(results[0].score, 43.0, places=4)

    def test_pullback_on_sma75_support(self):
        # パターンD: SMA25を大きく割り込んでいるが、SMA75の直上でサポートされている場合
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 92, "SMA25": 100, "SMA75": 90}),
        ]
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=90.9, high=92.0, low=90.0, close=90.9, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        # base=60*0.7=42.0
        self.assertAlmostEqual(results[0].score, 42.0, places=4)

    def test_no_uptrend_or_broken_support(self):
        # 上昇トレンドではない (SMA25 <= SMA75) または 長期線を割り込んでいる場合
        # SMA25: 90, SMA75: 100 (下降トレンド) -> スコア 10.0
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 88, "SMA25": 90, "SMA75": 100}),
        ]
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=102, low=85, close=90.0, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertEqual(results[0].score, 10.0)

        # 上昇トレンドだが長期線を割り込んでいる
        # SMA25: 100, SMA75: 90, 終値 85.0 -> スコア 10.0
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 92, "SMA25": 100, "SMA75": 90}),
        ]
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=102, low=80, close=85.0, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertEqual(results[0].score, 10.0)

    def test_missing_data(self):
        # データ不足時 -> スコア 30.0
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 100}), # SMA25, SMA75がない
        ]
        results = self.feature.calculate(self.ohlcv_data, indicator_data)
        self.assertEqual(results[0].score, 30.0)

    def test_zero_range_and_zero_sma75_boundary(self):
        # high == low かつ sma75 == 0 でもゼロ除算せず安全に計算できる
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 100, "SMA25": 100, "SMA75": 0}),
        ]
        results = self.feature.calculate(self.ohlcv_data, indicator_data)
        self.assertEqual(results[0].score, 30.0)
        self.assertEqual(results[0].metadata["clv"], 0.5)
        self.assertEqual(results[0].metadata["lower_wick_ratio"], 0.0)

if __name__ == '__main__':
    unittest.main()
