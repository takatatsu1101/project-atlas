import unittest
from datetime import date, timedelta

from src.feature_engine.features.trend import TrendStrengthScore
from src.model.data_models import IndicatorSetModel, OhlcvModel


class TestTrendStrengthScore(unittest.TestCase):
    def setUp(self):
        self.feature = TrendStrengthScore()
        self.symbol = "TEST"

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "T001_TrendStrengthScore")
        self.assertEqual(self.feature.feature_name, "トレンド強度")
        self.assertEqual(self.feature.feature_category, "Trend")

    def test_strong_uptrend_with_long_term_base(self):
        """適正なSMA75乖離(+10%) + 52週高値圏 + 長期基盤(SMA200)で高スコア"""
        ohlcv = [
            OhlcvModel(
                symbol=self.symbol,
                date=date(2025, 1, 1) + timedelta(days=i),
                open=108.0,
                high=111.0,
                low=107.0,
                close=110.0,
                volume=1000,
            )
            for i in range(10)
        ]
        indicator_data = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, 1) + timedelta(days=i),
                indicators={
                    "SMA5": 109.0,
                    "SMA25": 105.0,
                    "SMA75": 100.0,
                    "SMA200": 90.0,
                    "HIGHEST_HIGH_20": 110.0,
                    "HIGHEST_HIGH_60": 110.0,
                    "HIGHEST_HIGH_250": 111.0,
                },
            )
            for i in range(10)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        last = results[-1]
        self.assertGreater(last.score, 90.0)
        self.assertAlmostEqual(last.metadata["sma75_dev"], 0.10, places=4)
        self.assertAlmostEqual(last.metadata["high_250_ratio"], 110.0 / 111.0, places=4)
        self.assertEqual(last.metadata["highest_high_60"], 110.0)
        self.assertEqual(last.metadata["highest_high_250"], 111.0)

    def test_overheated_sma75_dev_penalized(self):
        """SMA75から+40%超の過熱状態は適正帯(+10%)よりスコアが低い"""
        ohlcv_healthy = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=110, high=111, low=109, close=110, volume=100)
        ]
        ind_healthy = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, 1),
                indicators={
                    "SMA5": 109,
                    "SMA25": 105,
                    "SMA75": 100,
                    "SMA200": 90,
                    "HIGHEST_HIGH_250": 110,
                },
            )
        ]
        ohlcv_hot = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=140, high=141, low=139, close=140, volume=100)
        ]
        ind_hot = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, 1),
                indicators={
                    "SMA5": 135,
                    "SMA25": 120,
                    "SMA75": 100,
                    "SMA200": 90,
                    "HIGHEST_HIGH_250": 140,
                },
            )
        ]
        s_healthy = self.feature.calculate(ohlcv_healthy, ind_healthy)[0].score
        s_hot = self.feature.calculate(ohlcv_hot, ind_hot)[0].score
        self.assertGreater(s_healthy, s_hot)

    def test_strong_downtrend(self):
        """SMA75・SMA200割れかつ52週高値から大きく下落で低スコア"""
        ohlcv = [
            OhlcvModel(
                symbol=self.symbol,
                date=date(2025, 1, 1) + timedelta(days=i),
                open=70.0,
                high=71.0,
                low=69.0,
                close=70.0,
                volume=100,
            )
            for i in range(6)
        ]
        indicator_data = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, 1) + timedelta(days=i),
                indicators={
                    "SMA5": 75.0,
                    "SMA25": 85.0,
                    "SMA75": 100.0 - i * 0.5,
                    "SMA200": 110.0,
                    "HIGHEST_HIGH_20": 90.0,
                    "HIGHEST_HIGH_60": 105.0,
                    "HIGHEST_HIGH_250": 120.0,
                },
            )
            for i in range(6)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertLess(results[-1].score, 10.0)

    def test_fallback_without_sma200_and_hh250(self):
        """SMA200・HIGHEST_HIGH_250 欠損時でもフォールバックで評価できる"""
        ohlcv = [
            OhlcvModel(
                symbol=self.symbol,
                date=date(2025, 1, 1) + timedelta(days=i),
                open=108.0,
                high=111.0,
                low=107.0,
                close=110.0,
                volume=100,
            )
            for i in range(6)
        ]
        indicator_data = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, 1) + timedelta(days=i),
                indicators={
                    "SMA5": 109.0,
                    "SMA25": 105.0,
                    "SMA75": 100.0 + i * 0.5,
                    "HIGHEST_HIGH_60": 112.0,
                },
            )
            for i in range(6)
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertGreater(results[-1].score, 75.0)
        self.assertIsNone(results[-1].metadata["sma200"])

    def test_missing_data(self):
        """必要な指標がない場合、一律50点"""
        ohlcv = [OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=102, low=98, close=101, volume=100)]
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 100}),
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertEqual(results[0].score, 50.0)


if __name__ == '__main__':
    unittest.main()
