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

if __name__ == '__main__':
    unittest.main()
