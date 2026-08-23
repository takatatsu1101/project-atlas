import unittest
from datetime import date

from src.feature_engine.features.fundamental.valuation_score import ValuationScore
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel

class TestValuationScore(unittest.TestCase):

    def setUp(self):
        self.feature = ValuationScore()
        self.symbol = "TEST"
        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=101, low=99, close=100, volume=100)
        ]
        self.indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={})
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "F003_ValuationScore")
        self.assertEqual(self.feature.feature_name, "割安性スコア")
        self.assertEqual(self.feature.feature_category, "Fundamental")

    def test_highly_undervalued(self):
        # 100.0点満点の非常に割安なケース
        # PER: 8.0 (50点), PBR: 0.6 (50点)
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2024, 12, 31),
            per=8.0,
            pbr=0.6
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(results[0].score, 100.0)

    def test_overvalued(self):
        # 非常に割高・または赤字ケース (10.0点)
        # PER: -5.0 (5点), PBR: 5.0 (5点) -> 合計10点
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2024, 12, 31),
            per=-5.0,
            pbr=5.0
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(results[0].score, 10.0)

    def test_missing_data(self):
        # 財務データがない場合、中立の50.0点
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, None)
        self.assertEqual(results[0].score, 50.0)

if __name__ == '__main__':
    unittest.main()
