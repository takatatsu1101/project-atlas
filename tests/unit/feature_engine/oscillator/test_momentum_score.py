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
        # 適正帯RSI14(60 -> 50点) + MACD加速(40点) + RSI5反転上昇(40->55 -> 10点) = 100.0点
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"RSI14": 55, "RSI5": 40, "MACD": {"macd": 1.5, "signal": 1.0, "histogram": 0.5}}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 2), indicators={"RSI14": 60, "RSI5": 55, "MACD": {"macd": 2.0, "signal": 1.0, "histogram": 1.0}}),
        ]
        results = self.feature.calculate(self.ohlcv_data[:2], indicator_data)
        self.assertAlmostEqual(results[1].score, 100.0, places=4)
        self.assertEqual(results[1].metadata["short_rsi"], 55)
        self.assertEqual(results[1].metadata["prev_short_rsi"], 40)

    def test_overheated_rsi14_penalized(self):
        # RSI14 > 80 の過熱は適正帯 (55〜65) より減点される
        ind_healthy = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"RSI14": 60, "RSI5": 55, "MACD": None}),
        ]
        ind_overheated = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"RSI14": 90, "RSI5": 55, "MACD": None}),
        ]
        s_healthy = self.feature.calculate(self.ohlcv_data[:1], ind_healthy)[0].score
        s_hot = self.feature.calculate(self.ohlcv_data[:1], ind_overheated)[0].score
        self.assertGreater(s_healthy, s_hot)

    def test_weak_momentum(self):
        # 弱い・下降モメンタム (RSI14=20, MACD下降加速, RSI5下落)
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"RSI14": 30, "RSI5": 40, "MACD": {"macd": 0.8, "signal": 1.3, "histogram": -0.5}}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 2), indicators={"RSI14": 20, "RSI5": 25, "MACD": {"macd": 0.5, "signal": 1.5, "histogram": -1.0}}),
        ]
        results = self.feature.calculate(self.ohlcv_data[:2], indicator_data)
        self.assertLess(results[1].score, 30.0)

    def test_missing_macd_detail(self):
        # MACDが辞書でない場合: RSI14=60(50点) + MACD中立(20点) + RSI5欠損中立(5点) = 75.0点
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"RSI14": 60, "MACD": None}),
        ]
        results = self.feature.calculate(self.ohlcv_data[:1], indicator_data)
        self.assertAlmostEqual(results[0].score, 75.0, places=4)

    def test_insufficient_data(self):
        # RSIがない場合、中立 (50.0)
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={}),
        ]
        results = self.feature.calculate(self.ohlcv_data[:1], indicator_data)
        self.assertEqual(results[0].score, 50.0)

if __name__ == '__main__':
    unittest.main()
