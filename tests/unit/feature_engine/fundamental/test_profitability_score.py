import unittest
from datetime import date

from src.feature_engine.features.fundamental.profitability_score import ProfitabilityScore
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel

class TestProfitabilityScore(unittest.TestCase):

    def setUp(self):
        self.feature = ProfitabilityScore()
        self.symbol = "TEST"
        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=101, low=99, close=100, volume=100)
        ]
        self.indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={})
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "F001_ProfitabilityScore")
        self.assertEqual(self.feature.feature_name, "収益性スコア")
        self.assertEqual(self.feature.feature_category, "Fundamental")

    def test_high_profitability(self):
        # 100点満点の超高収益ケース
        # ROE: 16%, ROA: 11%, 売上: 1000, 営業利益: 200 (利益率20%)
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2024, 12, 31),
            roe=16.0,
            roa=11.0,
            revenue=1000.0,
            operating_profit=200.0
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(results[0].score, 100.0)

    def test_low_profitability(self):
        # 赤字・低収益ケース (0点)
        # ROE: -5%, ROA: -2%, 売上: 1000, 営業利益: -50 (利益率-5%)
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2024, 12, 31),
            roe=-5.0,
            roa=-2.0,
            revenue=1000.0,
            operating_profit=-50.0
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(results[0].score, 0.0)

    def test_missing_financial_data(self):
        # 財務データがない場合、中立の50点
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, None)
        self.assertEqual(results[0].score, 50.0)

if __name__ == '__main__':
    unittest.main()
