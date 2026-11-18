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
        # 最も評価が高い状態 (100.0)
        # 10日目のデータ：
        # - 今日の出来高: 200 (平均100の2倍 -> 40点)
        # - VMA5: 200/VMA25: 110 (1.3倍超 -> 35点)
        # - 陽線且つ出来高増: (終値102 > 始値100) & (出来高200 > 平均110 -> 25点)
        # 合計 100点
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100, volume=100)
            for d in range(1, 10)
        ]
        # 10日目は出来高急増、陽線
        ohlcv.append(OhlcvModel(symbol=self.symbol, date=date(2025, 1, 10), open=100, high=103, low=99, close=102, volume=1000))
        
        results = self.feature.calculate(ohlcv, self.indicator_data)
        self.assertEqual(results[9].score, 100.0)

    def test_low_volume_and_bearish(self):
        # 低い評価の閑散・陰線下落ケース
        # 10日目のデータ：
        # - 出来高: 40 (平均94の0.5倍未満 -> 0点)
        # - VMA5: 88 / VMA25: 94 (< 1.0倍 -> 15点)
        # - 陰線且つ出来高が平均以下: (終値98 < 始値100) & (出来高40 < 平均94 -> 15点)
        # 合計 30点
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=101, low=99, close=100, volume=100)
            for d in range(1, 10)
        ]
        # 10日目は出来高40、陰線
        ohlcv.append(OhlcvModel(symbol=self.symbol, date=date(2025, 1, 10), open=100, high=101, low=97, close=98, volume=40))

        results = self.feature.calculate(ohlcv, self.indicator_data)
        self.assertEqual(results[9].score, 30.0)

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
        self.assertEqual(results[25].score, 100.0)

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
        # volume_ratio=0 (0点) + vma5=80/vma25=100 (15点) + 同値 (10点) = 25点
        self.assertAlmostEqual(res_today_zero[9].score, 25.0)

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
