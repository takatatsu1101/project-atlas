import unittest
from datetime import date

from src.feature_engine.features.fundamental.earnings_quality_score import EarningsQualityScore
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel

class TestEarningsQualityScore(unittest.TestCase):

    def setUp(self):
        self.feature = EarningsQualityScore()
        self.symbol = "TEST"
        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=101, low=99, close=100, volume=100)
        ]
        self.indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={})
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "F005_EarningsQualityScore")
        self.assertEqual(self.feature.feature_name, "利益の質スコア")
        self.assertEqual(self.feature.feature_category, "Fundamental")

    def test_high_quality(self):
        # 利益の質が極めて高いケース (100.0点)
        # 営業利益: 100, 純利益: 90 -> 整合性 0.9 (50点)
        # ROE: 15%, ROA: 10% -> レバレッジ 1.5 (50点)
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2024, 12, 31),
            roe=15.0,
            roa=10.0,
            operating_profit=100.0,
            net_profit=90.0
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(results[0].score, 100.0)

    def test_low_quality(self):
        # 利益の質が低いケース (20.0点)
        # 営業利益: 10, 純利益: 100 (本業の10倍。特別利益依存) -> 整合性 10.0 (10点)
        # ROE: 30%, ROA: 5% -> レバレッジ 6.0 (過度な負債依存) -> (10点)
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2024, 12, 31),
            roe=30.0,
            roa=5.0,
            operating_profit=10.0,
            net_profit=100.0
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(results[0].score, 20.0)

    def test_missing_data(self):
        # 財務データがない場合、中立の50.0点
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, None)
        self.assertEqual(results[0].score, 50.0)

if __name__ == '__main__':
    unittest.main()
