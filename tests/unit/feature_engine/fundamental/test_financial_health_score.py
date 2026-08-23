import unittest
from datetime import date

from src.feature_engine.features.fundamental.financial_health_score import FinancialHealthScore
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel

class TestFinancialHealthScore(unittest.TestCase):

    def setUp(self):
        self.feature = FinancialHealthScore()
        self.symbol = "TEST"
        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=101, low=99, close=100, volume=100)
        ]
        self.indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={})
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "F004_FinancialHealthScore")
        self.assertEqual(self.feature.feature_name, "財務健全性スコア")
        self.assertEqual(self.feature.feature_category, "Fundamental")

    def test_healthy_financials(self):
        # 健全性の極めて高いケース (100.0点)
        # BPS: 1000 > EPS: 50 且つ 営業利益: 100 > 0 且つ 純利益: 50 > 0
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2024, 12, 31),
            eps=50.0,
            bps=1000.0,
            operating_profit=100.0,
            net_profit=50.0
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(results[0].score, 100.0)

    def test_unhealthy_financials(self):
        # 脆弱ケース (0.0点)
        # BPS: -10 <= EPS: 10 且つ ともに赤字 (営業利益: -50, 純利益: -80)
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2024, 12, 31),
            eps=10.0,
            bps=-10.0,
            operating_profit=-50.0,
            net_profit=-80.0
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(results[0].score, 0.0)

    def test_missing_data(self):
        # 財務データがない場合、中立の50.0点
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, None)
        self.assertEqual(results[0].score, 50.0)

if __name__ == '__main__':
    unittest.main()
