import unittest
from datetime import date

from src.feature_engine.features.oscillator.momentum_score import MomentumScore
from src.model.data_models import OhlcvModel, IndicatorSetModel

class TestMomentumScore(unittest.TestCase):

    def setUp(self):
        self.feature = MomentumScore()
        self.symbol = "TEST"

        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100, volume=100)
            for d in range(1, 4)
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "O001_MomentumScore")
        self.assertEqual(self.feature.feature_name, "モメンタムスコア")
        self.assertEqual(self.feature.feature_category, "Oscillator")

    def test_strong_momentum(self):
        # 強い上昇モメンタム
        # RSI14 = 80 (40点)
        # MACD = {"macd": 2.0, "signal": 1.0, "histogram": 1.0} (前日 0.5 より大きいため加速 -> 30 + 20 = 50点)
        # 合計 90.0点
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"RSI14": 70, "MACD": {"macd": 1.5, "signal": 1.0, "histogram": 0.5}}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 2), indicators={"RSI14": 80, "MACD": {"macd": 2.0, "signal": 1.0, "histogram": 1.0}}),
        ]
        results = self.feature.calculate(self.ohlcv_data[:2], indicator_data)
        self.assertEqual(results[1].score, 90.0)

    def test_weak_momentum(self):
        # 弱い・下降モメンタム
        # RSI14 = 30 (15点)
        # MACD = {"macd": 0.5, "signal": 1.5, "histogram": -1.0} (前日 -0.5 より小さいため下降加速 -> 10 + 0 = 10点)
        # 合計 25.0点
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"RSI14": 40, "MACD": {"macd": 0.8, "signal": 1.3, "histogram": -0.5}}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 2), indicators={"RSI14": 30, "MACD": {"macd": 0.5, "signal": 1.5, "histogram": -1.0}}),
        ]
        results = self.feature.calculate(self.ohlcv_data[:2], indicator_data)
        self.assertEqual(results[1].score, 25.0)

    def test_missing_macd_detail(self):
        # MACDが辞書でない、またはデータが不十分な場合
        # RSI14 = 60 (30点) + MACD中立 (25点) = 55.0点
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"RSI14": 60, "MACD": None}),
        ]
        results = self.feature.calculate(self.ohlcv_data[:1], indicator_data)
        self.assertAlmostEqual(results[0].score, 55.0, places=4)

    def test_insufficient_data(self):
        # RSIがない場合、中立 (50.0)
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={}),
        ]
        results = self.feature.calculate(self.ohlcv_data[:1], indicator_data)
        self.assertEqual(results[0].score, 50.0)

if __name__ == '__main__':
    unittest.main()
