
import unittest
from datetime import date, timedelta

from src.feature_engine.features.moving_average.ma_alignment_score import MAAlignmentScore
from src.model.data_models import IndicatorSetModel, OhlcvModel


class TestMAAlignmentScore(unittest.TestCase):
    def setUp(self):
        self.feature = MAAlignmentScore()
        self.symbol = "TEST"
        self.ohlcv_data = [
            OhlcvModel(
                symbol=self.symbol,
                date=date(2025, 1, 1) + timedelta(days=i),
                open=100,
                high=100,
                low=100,
                close=100,
                volume=0,
            )
            for i in range(25)
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "M001_MAAlignmentScore")
        self.assertEqual(self.feature.feature_name, "移動平均線の並び評価")
        self.assertEqual(self.feature.feature_category, "Moving Average")

    def test_perfect_order_with_positive_slopes(self):
        """パーフェクトオーダー + 上向き傾き + 適正スプレッドで高スコア"""
        indicator_data = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, 1) + timedelta(days=i),
                indicators={
                    "SMA5": 110.0 + i * 0.8,
                    "SMA25": 100.0 + i * 0.5,
                    "SMA75": 95.0 + i * 0.3,
                    "SMA200": 90.0 + i * 0.1,
                },
            )
            for i in range(25)
        ]
        results = self.feature.calculate(self.ohlcv_data, indicator_data)
        last = results[-1]
        self.assertGreater(last.score, 85.0)
        self.assertIsNotNone(last.metadata["sma200"])
        self.assertIsNotNone(last.metadata["sma25_slope_5d"])
        self.assertIsNotNone(last.metadata["sma25_slope_20d"])
        self.assertIsNotNone(last.metadata["sma75_slope_20d"])

    def test_strong_downtrend_with_negative_slopes(self):
        """完全下降配列 + 下向き傾きで低スコア"""
        indicator_data = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, 1) + timedelta(days=i),
                indicators={
                    "SMA5": 90.0 - i * 0.8,
                    "SMA25": 100.0 - i * 0.5,
                    "SMA75": 110.0 - i * 0.3,
                    "SMA200": 120.0 - i * 0.1,
                },
            )
            for i in range(25)
        ]
        results = self.feature.calculate(self.ohlcv_data, indicator_data)
        self.assertLess(results[-1].score, 15.0)

    def test_slope_continuity_and_spread_attenuation(self):
        """傾きが大きいほど高く、スプレッド過拡散(+25%超)は適正帯より減衰する"""
        # 適正スプレッド (+6%)
        healthy = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, 1),
                indicators={"SMA5": 110.0, "SMA25": 106.0, "SMA75": 100.0, "SMA200": 90.0},
            )
        ]
        # 過拡散スプレッド (+35%)
        over_spread = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, 1),
                indicators={"SMA5": 140.0, "SMA25": 135.0, "SMA75": 100.0, "SMA200": 90.0},
            )
        ]
        res_healthy = self.feature.calculate(self.ohlcv_data[:1], healthy)[0]
        res_over = self.feature.calculate(self.ohlcv_data[:1], over_spread)[0]
        self.assertGreater(res_healthy.score, res_over.score)
        # i < 5 では傾きは None（中立点フォールバック）
        self.assertIsNone(res_healthy.metadata["sma25_slope_5d"])

    def test_missing_sma200_and_missing_core_sma(self):
        """SMA200欠損時は3本で評価し、必須SMA欠損時は50.0"""
        no_200 = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, 1),
                indicators={"SMA5": 110.0, "SMA25": 105.0, "SMA75": 100.0},
            )
        ]
        res_no_200 = self.feature.calculate(self.ohlcv_data[:1], no_200)[0]
        self.assertGreater(res_no_200.score, 65.0)
        self.assertIsNone(res_no_200.metadata["sma200"])

        missing = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 100}),
        ]
        results = self.feature.calculate(self.ohlcv_data[:1], missing)
        self.assertEqual(results[0].score, 50.0)

    def test_calculate_empty_indicator_data(self):
        results = self.feature.calculate(self.ohlcv_data, [])
        self.assertEqual(len(results), 0)

    def test_normalize_score(self):
        self.assertEqual(self.feature._normalize_score(50, 0, 100), 50.0)
        self.assertEqual(self.feature._normalize_score(0, 0, 100), 0.0)
        self.assertEqual(self.feature._normalize_score(100, 0, 100), 100.0)
        self.assertEqual(self.feature._normalize_score(10, 0, 50), 20.0)
        self.assertEqual(self.feature._normalize_score(50, 50, 50), 50.0)
        self.assertEqual(self.feature._normalize_score(-10, 0, 100), 0.0)
        self.assertEqual(self.feature._normalize_score(110, 0, 100), 100.0)


if __name__ == '__main__':
    unittest.main()
