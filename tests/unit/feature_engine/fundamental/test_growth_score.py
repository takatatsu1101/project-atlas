import unittest
from datetime import date

from src.feature_engine.features.fundamental.growth_score import GrowthScore
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel

class TestGrowthScore(unittest.TestCase):

    def setUp(self):
        self.feature = GrowthScore()
        self.symbol = "TEST"
        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=101, low=99, close=100, volume=100)
        ]
        self.indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={})
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "F002_GrowthScore")
        self.assertEqual(self.feature.feature_name, "成長性スコア")
        self.assertEqual(self.feature.feature_category, "Fundamental")

    def test_high_growth_5y_avg(self):
        # 5年平均高成長ケース (100.0点)
        # 売上高5年平均: 16%, 純利益5年平均: 21%
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2024, 12, 31),
            revenue_growth_5y_avg=16.0,
            net_profit_growth_5y_avg=21.0
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(results[0].score, 100.0)

    def test_medium_growth_3y_avg(self):
        # 3年平均中成長ケース
        # 売上高3年平均: 7% (30点), 純利益3年平均: 12% (40点) -> 合計 70.0点
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2024, 12, 31),
            revenue_growth_3y_avg=7.0,
            net_profit_growth_3y_avg=12.0
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(results[0].score, 70.0)

    def test_low_growth(self):
        # 低成長・減収減益ケース (0.0点)
        # 売上高成長: -2%, 純利益成長: -10%
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2024, 12, 31),
            revenue_growth=-2.0,
            net_profit_growth=-10.0
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(results[0].score, 0.0)

    def test_missing_growth_data(self):
        # 成長データが全くない場合、中立の50.0点
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2024, 12, 31)
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(results[0].score, 50.0)

if __name__ == '__main__':
    unittest.main()
