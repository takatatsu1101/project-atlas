import unittest
from datetime import date

from src.feature_engine.features.volume.volume_score import VolumeScore
from src.model.data_models import OhlcvModel, IndicatorSetModel

class TestVolumeScore(unittest.TestCase):

    def setUp(self):
        self.feature = VolumeScore()
        self.symbol = "TEST"

        # 過去10日分のOHLCVデータをモック（通常は出来高100とする）
        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100, volume=100)
            for d in range(1, 11)
        ]
        self.indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, d), indicators={})
            for d in range(1, 11)
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "V001_VolumeScore")
        self.assertEqual(self.feature.feature_name, "出来高評価")
        self.assertEqual(self.feature.feature_category, "Volume")

    def test_insufficient_data(self):
        # 5日未満のデータで中立(50.0)になるか
        results = self.feature.calculate(self.ohlcv_data[:4], self.indicator_data[:4])
        self.assertEqual(results[3].score, 50.0)

    def test_high_volume_and_bullish(self):
        # 出来高急増・陽線・上昇日出来高優位で高スコア
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100 + d * 0.1, volume=100)
            for d in range(1, 10)
        ]
        # 10日目は出来高急増、陽線
        ohlcv.append(OhlcvModel(symbol=self.symbol, date=date(2025, 1, 10), open=101, high=104, low=100, close=103, volume=1000))

        results = self.feature.calculate(ohlcv, self.indicator_data)
        self.assertGreater(results[9].score, 85.0)
        self.assertGreater(results[9].metadata["up_down_volume_ratio"], 1.5)

    def test_low_volume_and_bearish(self):
        # 閑散・陰線下落ケースで低スコア
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100 - d * 0.1, volume=100)
            for d in range(1, 10)
        ]
        ohlcv.append(OhlcvModel(symbol=self.symbol, date=date(2025, 1, 10), open=99, high=100, low=97, close=98, volume=40))

        results = self.feature.calculate(ohlcv, self.indicator_data)
        self.assertLess(results[9].score, 30.0)
        self.assertLess(results[9].metadata["up_down_volume_ratio"], 0.8)

    def test_pullback_dryup_rebound(self):
        """押し目売り枯れ(t-4〜t-1細り)→当日陽線+出来高増で pullback_dryup_rebound=True"""
        from datetime import timedelta

        base = date(2025, 1, 1)
        ohlcv = []
        # 0〜19日目: 出来高1000、緩やかな上昇
        for idx in range(20):
            ohlcv.append(
                OhlcvModel(
                    symbol=self.symbol,
                    date=base + timedelta(days=idx),
                    open=100,
                    high=102,
                    low=99,
                    close=100 + idx * 0.2,
                    volume=1000,
                )
            )
        # 20〜23日目(t-4〜t-1): 出来高400に売り枯れ（avg_volume_25 * 0.8 以下）
        for idx in range(20, 24):
            ohlcv.append(
                OhlcvModel(
                    symbol=self.symbol,
                    date=base + timedelta(days=idx),
                    open=103,
                    high=103,
                    low=101,
                    close=102,
                    volume=400,
                )
            )
        # 24日目(当日): 陽線＋出来高1200へ増加
        ohlcv.append(
            OhlcvModel(
                symbol=self.symbol,
                date=base + timedelta(days=24),
                open=102,
                high=106,
                low=101,
                close=105,
                volume=1200,
            )
        )
        inds = [IndicatorSetModel(symbol=self.symbol, date=b.date, indicators={}) for b in ohlcv]
        results = self.feature.calculate(ohlcv, inds)
        self.assertTrue(results[-1].metadata["pullback_dryup_rebound"])
        self.assertGreater(results[-1].score, 75.0)

    def test_avg_volume_25_excludes_today(self):
        # 当日 i を除外し t-25 〜 t-1 のみで avg_volume_25 / vma25 を算出することを検証
        from datetime import timedelta

        base = date(2025, 1, 1)
        ohlcv = [
            OhlcvModel(
                symbol=self.symbol,
                date=base + timedelta(days=idx),
                open=100,
                high=101,
                low=99,
                close=100,
                volume=100,
            )
            for idx in range(25)
        ]
        # 26日目（インデックス25）だけ出来高1000の急増陽線
        ohlcv.append(
            OhlcvModel(
                symbol=self.symbol,
                date=base + timedelta(days=25),
                open=100,
                high=103,
                low=99,
                close=102,
                volume=1000,
            )
        )
        inds = [
            IndicatorSetModel(symbol=self.symbol, date=b.date, indicators={})
            for b in ohlcv
        ]

        results = self.feature.calculate(ohlcv, inds)
        meta_25 = results[25].metadata
        self.assertEqual(meta_25["volume"], 1000)
        self.assertAlmostEqual(meta_25["avg_volume_25"], 100.0)
        self.assertAlmostEqual(meta_25["vma25"], 100.0)
        # vma5 は当日を含む直近5日: (100*4 + 1000) / 5 = 280.0
        self.assertAlmostEqual(meta_25["vma5"], 280.0)
        self.assertGreater(results[25].score, 85.0)

        # min_past_days=5 境界（インデックス5）でも当日を除外した t-5〜t-1 が使われる
        ohlcv_edge = list(ohlcv[:5]) + [
            OhlcvModel(
                symbol=self.symbol,
                date=base + timedelta(days=5),
                open=100,
                high=103,
                low=99,
                close=102,
                volume=500,
            )
        ]
        inds_edge = [
            IndicatorSetModel(symbol=self.symbol, date=b.date, indicators={})
            for b in ohlcv_edge
        ]
        res_edge = self.feature.calculate(ohlcv_edge, inds_edge)
        self.assertAlmostEqual(res_edge[5].metadata["avg_volume_25"], 100.0)
        self.assertAlmostEqual(res_edge[5].metadata["vma5"], (100 * 4 + 500) / 5.0)

    def test_zero_volume_boundary(self):
        """当日 volume=0 および過去平均 volume=0 の境界ケースでゼロ除算せず有限スコアを返す"""
        # 1) 過去平均 > 0 かつ当日 volume = 0
        ohlcv_today_zero = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100, volume=100)
            for d in range(1, 10)
        ] + [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 10), open=100, high=101, low=99, close=100, volume=0)
        ]
        res_today_zero = self.feature.calculate(ohlcv_today_zero, self.indicator_data)
        self.assertEqual(res_today_zero[9].metadata["volume"], 0)
        self.assertAlmostEqual(res_today_zero[9].metadata["avg_volume_25"], 100.0)
        self.assertGreaterEqual(res_today_zero[9].score, 0.0)
        self.assertLessEqual(res_today_zero[9].score, 100.0)

        # 2) 過去平均 volume = 0（全期間出来高0）
        ohlcv_all_zero = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100, volume=0)
            for d in range(1, 11)
        ]
        res_all_zero = self.feature.calculate(ohlcv_all_zero, self.indicator_data)
        self.assertAlmostEqual(res_all_zero[9].metadata["avg_volume_25"], 0.0)
        self.assertAlmostEqual(res_all_zero[9].score, 50.0)

if __name__ == '__main__':
    unittest.main()
