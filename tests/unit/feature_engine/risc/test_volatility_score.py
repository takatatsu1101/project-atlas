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

    def test_vcp_contraction_and_healthy_atr_high_score(self):
        """VCP収縮(ATR5/ATR20 <= 0.65) + 適正ATR% + リスクリワード余地で高スコア"""
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100, volume=100)
            for d in range(1, 11)
        ]
        ind = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, d),
                indicators={"ATR5": 1.2, "ATR14": 2.0, "ATR20": 2.0, "HIGHEST_HIGH_20": 106.0},
            )
            for d in range(1, 11)
        ]
        results = self.feature.calculate(ohlcv, ind)
        last = results[-1]
        # contraction=0.6 -> 40点, atr_pct=0.02 -> 30点, rr=3.0 -> 30点 => 100.0
        self.assertAlmostEqual(last.score, 100.0, places=4)
        self.assertIn("volatility_ratio", last.metadata)
        self.assertAlmostEqual(last.metadata["atr_contraction"], 0.6, places=4)
        self.assertAlmostEqual(last.metadata["atr_pct"], 0.02, places=4)
        self.assertAlmostEqual(last.metadata["reward_risk_ratio"], 3.0, places=4)

    def test_high_volatility_expansion_low_score(self):
        """ボラティリティ拡大(ATR5/ATR20 > 1.4) + 過大ATR%(>8%)で低スコア"""
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100, volume=100)
            for d in range(1, 10)
        ]
        ohlcv.append(OhlcvModel(symbol=self.symbol, date=date(2025, 1, 10), open=100, high=110, low=90, close=100, volume=100))
        ind = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, d),
                indicators={"ATR5": 9.0, "ATR14": 9.0, "ATR20": 5.0, "HIGHEST_HIGH_20": 100.0},
            )
            for d in range(1, 11)
        ]
        results = self.feature.calculate(ohlcv, ind)
        last = results[-1]
        self.assertLessEqual(last.score, 10.0)
        self.assertIsNotNone(last.metadata["volatility_ratio"])

    def test_zero_atr_and_flat_ohlcv_boundary(self):
        """atr20 == 0 かつ全日同値(TR=0)でもゼロ除算せず安全に計算できる"""
        flat_ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=100, low=100, close=100, volume=100)
            for d in range(1, 11)
        ]
        zero_ind = [
            IndicatorSetModel(
                symbol=self.symbol,
                date=date(2025, 1, d),
                indicators={"ATR5": 0.0, "ATR14": 0.0, "ATR20": 0.0, "HIGHEST_HIGH_20": 100.0},
            )
            for d in range(1, 11)
        ]
        results = self.feature.calculate(flat_ohlcv, zero_ind)
        last = results[-1]
        self.assertIsNone(last.metadata["volatility_ratio"])
        self.assertIsNone(last.metadata["atr_contraction"])
        self.assertAlmostEqual(last.score, 40.0, places=4)

    def test_legacy_metadata_keys_preserved_without_new_indicators(self):
        """新指標(ATR5/14/20)欠損時も既存互換キーを保持しフォールバックする"""
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data)
        meta = results[9].metadata
        self.assertIn("close", meta)
        self.assertIn("tr_today", meta)
        self.assertIn("avg_atr", meta)
        self.assertIn("volatility_ratio", meta)
        self.assertAlmostEqual(meta["volatility_ratio"], meta["tr_today"] / meta["avg_atr"], places=6)

if __name__ == '__main__':
    unittest.main()
