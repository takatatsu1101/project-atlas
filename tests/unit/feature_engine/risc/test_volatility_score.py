import unittest
from datetime import date

from src.feature_engine.features.risc.volatility_score import VolatilityScore
from src.model.data_models import OhlcvModel, IndicatorSetModel

class TestVolatilityScore(unittest.TestCase):

    def setUp(self):
        self.feature = VolatilityScore()
        self.symbol = "TEST"

        # 過去10日分のOHLCVデータをモック（通常は高値101, 安値99, 終値100、TR=2とする）
        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100, volume=100)
            for d in range(1, 11)
        ]
        self.indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, d), indicators={})
            for d in range(1, 11)
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "R001_VolatilityScore")
        self.assertEqual(self.feature.feature_name, "ボラティリティスコア")
        self.assertEqual(self.feature.feature_category, "Risk")

    def test_insufficient_data(self):
        # 5日未満のデータで中立(50.0)になるか
        results = self.feature.calculate(self.ohlcv_data[:4], self.indicator_data[:4])
        self.assertEqual(results[3].score, 50.0)

    def test_high_volatility(self):
        # ボラティリティ急増 (2倍以上)
        # 10日目のデータ：
        # - High: 110, Low: 90 (TR=20)
        # - 過去10日間のTR平均: (2 * 9 + 20) / 10 = 3.8
        # - 今日のTR (20) / 平均 (3.8) = 5.26 (>= 2.0 -> スコア 100.0)
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100, volume=100)
            for d in range(1, 10)
        ]
        ohlcv.append(OhlcvModel(symbol=self.symbol, date=date(2025, 1, 10), open=100, high=110, low=90, close=100, volume=100))

        results = self.feature.calculate(ohlcv, self.indicator_data)
        self.assertAlmostEqual(results[9].score, 100.0, places=4)

    def test_low_volatility(self):
        # ボラティリティ減少 (0.5倍以下)
        # 10日目のデータ：
        # - High: 100.2, Low: 99.8 (TR=0.4)
        # - 過去10日間のTR平均: (2 * 9 + 0.4) / 10 = 1.84
        # - 今日のTR (0.4) / 平均 (1.84) = 0.217 (< 0.5 -> スコア 20.0)
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100, volume=100)
            for d in range(1, 10)
        ]
        ohlcv.append(OhlcvModel(symbol=self.symbol, date=date(2025, 1, 10), open=100, high=100.2, low=99.8, close=100, volume=100))

        results = self.feature.calculate(ohlcv, self.indicator_data)
        self.assertAlmostEqual(results[9].score, 20.0, places=4)

if __name__ == '__main__':
    unittest.main()
