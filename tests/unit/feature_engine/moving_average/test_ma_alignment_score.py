
import unittest
from datetime import date
from typing import List

from src.feature_engine.features.moving_average.ma_alignment_score import MAAlignmentScore
from src.model.data_models import OhlcvModel, IndicatorSetModel, FeatureResultModel

class TestMAAlignmentScore(unittest.TestCase):

    def setUp(self):
        self.feature = MAAlignmentScore()
        self.symbol = "TEST"

        # OHLCVデータはここでは直接利用しないが、FeatureResultModelに日付情報などを持たせるために必要
        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=100, low=100, close=100, volume=0),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=100, high=100, low=100, close=100, volume=0),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 3), open=100, high=100, low=100, close=100, volume=0),
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "M001_MAAlignmentScore")
        self.assertEqual(self.feature.feature_name, "移動平均線の並び評価")
        self.assertEqual(self.feature.feature_category, "Moving Average")

    def test_calculate_strong_uptrend(self):
        # 短期 > 中期 > 長期
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 100, "SMA25": 90, "SMA75": 80}),
        ]
        results = self.feature.calculate(self.ohlcv_data, indicator_data)
        self.assertEqual(results[0].score, 100.0)
        self.assertEqual(results[0].raw_value, 100.0)

    def test_calculate_strong_downtrend(self):
        # 短期 < 中期 < 長期
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 80, "SMA25": 90, "SMA75": 100}),
        ]
        results = self.feature.calculate(self.ohlcv_data, indicator_data)
        self.assertEqual(results[0].score, 0.0)
        self.assertEqual(results[0].raw_value, 0.0)

    def test_calculate_uptrend_bias(self):
        # 短期 > 中期 かつ 短期 > 長期 だが、中期 <= 長期 の場合 (上昇基調)
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 95, "SMA25": 88, "SMA75": 90}),
        ]
        results = self.feature.calculate(self.ohlcv_data, indicator_data)
        self.assertEqual(results[0].score, 75.0)
        self.assertEqual(results[0].raw_value, 75.0)

    def test_calculate_downtrend_bias(self):
        # 短期 < 中期, 長期との関係が複雑な場合 (下降基調)
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 85, "SMA25": 90, "SMA75": 88}), # SMA5 < SMA25 < SMA75 ではないが下降基調
        ]
        results = self.feature.calculate(self.ohlcv_data, indicator_data)
        self.assertEqual(results[0].score, 25.0)
        self.assertEqual(results[0].raw_value, 25.0)

    def test_calculate_neutral_complex_1(self):
        # 短期 > 中期, 中期 < 長期 (レンジ)
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 90, "SMA25": 85, "SMA75": 95}), # 短期 > 中期, 中期 < 長期
        ]
        results = self.feature.calculate(self.ohlcv_data, indicator_data)
        self.assertEqual(results[0].score, 50.0)
        self.assertEqual(results[0].raw_value, 50.0)

    def test_calculate_neutral_complex_2(self):
        # 短期 < 中期, 中期 > 長期 (レンジ)
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 90, "SMA25": 95, "SMA75": 85}), # 短期 < 中期, 中期 > 長期
        ]
        results = self.feature.calculate(self.ohlcv_data, indicator_data)
        self.assertEqual(results[0].score, 50.0)
        self.assertEqual(results[0].raw_value, 50.0)

    def test_calculate_missing_sma_data(self):
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 100}), # SMA25, SMA75がない
        ]
        results = self.feature.calculate(self.ohlcv_data, indicator_data)
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
