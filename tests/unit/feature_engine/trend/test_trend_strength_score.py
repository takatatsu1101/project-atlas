import unittest
from datetime import date

from src.feature_engine.features.trend import TrendStrengthScore
from src.model.data_models import OhlcvModel, IndicatorSetModel

class TestTrendStrengthScore(unittest.TestCase):

    def setUp(self):
        self.feature = TrendStrengthScore()
        self.symbol = "TEST"

        # 10日分のOHLCVデータをモック（徐々に値上がりする上昇相場）
        self.ohlcv_data_up = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100+d, high=102+d, low=99+d, close=101+d, volume=100)
            for d in range(1, 11)
        ]
        # 徐々に値下がりする下降相場
        self.ohlcv_data_down = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100-d, high=101-d, low=98-d, close=99-d, volume=100)
            for d in range(1, 11)
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "T001_TrendStrengthScore")
        self.assertEqual(self.feature.feature_name, "トレンド強度")
        self.assertEqual(self.feature.feature_category, "Trend")

    def test_strong_uptrend(self):
        # 完璧な強い上昇トレンド
        # 10日目のデータ：
        # - SMA並び: 5日 > 25日 > 75日 (40点) (SMA5: 110, SMA25: 105, SMA75: 100)
        # - 傾き: 5日前(SMA5: 105, SMA25: 100, SMA75: 95)よりすべて高い (30点)
        # - 株価位置: 終値115 > 105(SMA25) 且つ 115 > 100(SMA75) (20点)
        # - 高値安値: 5日前の高値安値(High: 106, Low: 103)より高い(High: 116, Low: 113) (10点)
        # 合計 100点
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=100+d*2, low=98+d*2, close=100+d*2, volume=100)
            for d in range(1, 11)
        ]
        indicator_data = [
            # 1〜5日目
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 101, "SMA25": 96, "SMA75": 91}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 2), indicators={"SMA5": 102, "SMA25": 97, "SMA75": 92}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 3), indicators={"SMA5": 103, "SMA25": 98, "SMA75": 93}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 4), indicators={"SMA5": 104, "SMA25": 99, "SMA75": 94}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 5), indicators={"SMA5": 105, "SMA25": 100, "SMA75": 95}),
            # 6〜10日目
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 6), indicators={"SMA5": 106, "SMA25": 101, "SMA75": 96}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 7), indicators={"SMA5": 107, "SMA25": 102, "SMA75": 97}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 8), indicators={"SMA5": 108, "SMA25": 103, "SMA75": 98}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 9), indicators={"SMA5": 109, "SMA25": 104, "SMA75": 99}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 10), indicators={"SMA5": 110, "SMA25": 105, "SMA75": 100}),
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertEqual(results[9].score, 100.0)

    def test_strong_downtrend(self):
        # 完璧な強い下降トレンド (0点)
        # 10日目のデータ：
        # - SMA並び: SMA5 < SMA25 < SMA75 (0点) (SMA5: 90, SMA25: 95, SMA75: 100)
        # - 傾き: すべて下向き (0点) (SMA5_prev: 95, SMA25_prev: 100, SMA75_prev: 105)
        # - 株価位置: 終値80 < SMA25(95) 且つ < SMA75(100) (0点)
        # - 高値安値: 5日前より切り下げ (0点)
        ohlcv = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, d), open=100, high=100-d*2, low=98-d*2, close=100-d*2, volume=100)
            for d in range(1, 11)
        ]
        indicator_data = [
            # 1〜5日目
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 99, "SMA25": 104, "SMA75": 109}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 2), indicators={"SMA5": 98, "SMA25": 103, "SMA75": 108}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 3), indicators={"SMA5": 97, "SMA25": 102, "SMA75": 107}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 4), indicators={"SMA5": 96, "SMA25": 101, "SMA75": 106}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 5), indicators={"SMA5": 95, "SMA25": 100, "SMA75": 105}),
            # 6〜10日目
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 6), indicators={"SMA5": 94, "SMA25": 99, "SMA75": 104}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 7), indicators={"SMA5": 93, "SMA25": 98, "SMA75": 103}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 8), indicators={"SMA5": 92, "SMA25": 97, "SMA75": 102}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 9), indicators={"SMA5": 91, "SMA25": 96, "SMA75": 101}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 10), indicators={"SMA5": 90, "SMA25": 95, "SMA75": 100}),
        ]
        results = self.feature.calculate(ohlcv, indicator_data)
        self.assertEqual(results[9].score, 0.0)

    def test_missing_data(self):
        # 必要な指標がない場合、一律50点
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 100}),
        ]
        results = self.feature.calculate(self.ohlcv_data_up[:1], indicator_data)
        self.assertEqual(results[0].score, 50.0)

if __name__ == '__main__':
    unittest.main()
