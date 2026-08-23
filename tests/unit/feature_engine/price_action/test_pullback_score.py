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

    def test_ideal_pullback_on_sma25(self):
        # パターンA: SMA25の直上 (0%〜3%の範囲。最も理想的な押し目)
        # SMA25: 100, SMA75: 90 (上昇トレンド)
        # 終値 100 のとき: 乖離率 0.0 -> スコア 100.0
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 102, "SMA25": 100, "SMA75": 90}),
        ]
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=105, low=99, close=100, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertEqual(results[0].score, 100.0)

        # 終値 101.5 のとき: 乖離率 1.5% -> スコア 90.0
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=105, low=99, close=101.5, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertEqual(results[0].score, 90.0)

    def test_deep_pullback_below_sma25(self):
        # パターンB: SMA25をわずかに割り込んでいる (-2%〜0%未満。深めの押し目)
        # SMA25: 100, SMA75: 90
        # 終値 99.0 のとき: 乖離率 -1.0% -> スコア 70.0
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 98, "SMA25": 100, "SMA75": 90}),
        ]
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=105, low=98, close=99.0, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertEqual(results[0].score, 70.0)

    def test_shallow_pullback_above_sma25(self):
        # パターンC: まだ押し目が浅い (3%を超える上昇継続中)
        # SMA25: 100, SMA75: 90
        # 終値 106.5 のとき: 乖離率 6.5% -> スコア 60.0
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 108, "SMA25": 100, "SMA75": 90}),
        ]
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=110, low=105, close=106.5, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertAlmostEqual(results[0].score, 60.0, places=4)

        # 終値 115.0 のとき: 乖離率 15.0% (> 10%) -> スコア 40.0
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=120, low=110, close=115.0, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertEqual(results[0].score, 40.0)

    def test_pullback_on_sma75_support(self):
        # パターンD: SMA25を大きく割り込んでいるが、SMA75の直上でサポートされている場合
        # SMA25: 100, SMA75: 90
        # 終値 90.9 のとき: SMA25乖離率 -9.1% (パターンDへ), SMA75乖離率 1.0% -> スコア 60.0
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 92, "SMA25": 100, "SMA75": 90}),
        ]
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=102, low=90, close=90.9, volume=1000)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertAlmostEqual(results[0].score, 60.0, places=4)

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

if __name__ == '__main__':
    unittest.main()
