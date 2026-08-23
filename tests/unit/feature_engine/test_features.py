
import unittest
from datetime import date
from typing import List
import numpy as np

from src.feature_engine.features.trend import TrendStrengthFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FeatureResultModel

class TestTrendStrengthFeature(unittest.TestCase):

    def setUp(self):
        self.feature = TrendStrengthFeature()
        self.symbol = "TEST"

        # テスト用のOHLCVデータ
        self.ohlcv_data: List[OhlcvModel] = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=110, low=90, close=100, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=100, high=115, low=95, close=105, volume=1100),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 3), open=105, high=120, low=100, close=110, volume=1200),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 4), open=110, high=125, low=105, close=115, volume=1300),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 5), open=115, high=130, low=110, close=120, volume=1400),
        ]

        # テスト用のIndicatorSetデータ (SMA5, SMA25, SMA75 を定義)
        self.indicator_data: List[IndicatorSetModel] = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 100, "SMA25": 90, "SMA75": 80}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 2), indicators={"SMA5": 102, "SMA25": 92, "SMA75": 82}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 3), indicators={"SMA5": 105, "SMA25": 95, "SMA75": 85}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 4), indicators={"SMA5": 110, "SMA25": 100, "SMA75": 90}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 5), indicators={"SMA5": 115, "SMA25": 105, "SMA75": 95}),
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "F001_TrendStrength")
        self.assertEqual(self.feature.feature_name, "トレンド強度スコア")
        self.assertEqual(self.feature.feature_category, "Trend")

    def test_calculate_strong_uptrend(self):
        # close > SMA5 > SMA25 > SMA75 の場合
        # 5日目のデータがこれに該当するように調整
        ohlcv_data = [
            self.ohlcv_data[0],
            self.ohlcv_data[1],
            self.ohlcv_data[2],
            self.ohlcv_data[3],
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 5), open=115, high=130, low=110, close=120, volume=1400), # close 120
        ]
        indicator_data = [
            self.indicator_data[0],
            self.indicator_data[1],
            self.indicator_data[2],
            self.indicator_data[3],
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 5), indicators={"SMA5": 118, "SMA25": 110, "SMA75": 100}), # SMA5=118, SMA25=110, SMA75=100
        ]

        results = self.feature.calculate(ohlcv_data, indicator_data)
        last_result = results[-1]
        self.assertIsInstance(last_result, FeatureResultModel)
        self.assertEqual(last_result.feature_id, self.feature.feature_id)
        self.assertEqual(last_result.score, 100.0) # 強い上昇トレンド
        self.assertEqual(last_result.raw_value, 100.0)

    def test_calculate_strong_downtrend(self):
        # close < SMA5 < SMA25 < SMA75 の場合
        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=110, low=90, close=80, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=80, high=90, low=70, close=70, volume=1100),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 3), open=70, high=80, low=60, close=60, volume=1200),
        ]
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 90, "SMA25": 100, "SMA75": 110}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 2), indicators={"SMA5": 80, "SMA25": 90, "SMA75": 100}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 3), indicators={"SMA5": 70, "SMA25": 80, "SMA75": 90}),
        ]
        results = self.feature.calculate(ohlcv_data, indicator_data)
        last_result = results[-1]
        self.assertEqual(last_result.score, 0.0) # 強い下降トレンド
        self.assertEqual(last_result.raw_value, 0.0)

    def test_calculate_uptrend(self):
        # SMA5 > SMA25 > SMA75 の場合
        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=110, low=90, close=100, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=100, high=115, low=95, close=105, volume=1100),
        ]
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 105, "SMA25": 100, "SMA75": 95}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 2), indicators={"SMA5": 108, "SMA25": 102, "SMA75": 98}),
        ]
        results = self.feature.calculate(ohlcv_data, indicator_data)
        last_result = results[-1]
        self.assertEqual(last_result.score, 75.0) # 上昇トレンド
        self.assertEqual(last_result.raw_value, 75.0)

    def test_calculate_downtrend(self):
        # SMA5 < SMA25 < SMA75 の場合
        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=110, low=90, close=100, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=100, high=115, low=95, close=105, volume=1100),
        ]
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 95, "SMA25": 100, "SMA75": 105}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 2), indicators={"SMA5": 92, "SMA25": 98, "SMA75": 102}),
        ]
        results = self.feature.calculate(ohlcv_data, indicator_data)
        last_result = results[-1]
        self.assertEqual(last_result.score, 25.0) # 下降トレンド
        self.assertEqual(last_result.raw_value, 25.0)

    def test_calculate_range(self):
        # それ以外（レンジ）の場合
        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=110, low=90, close=100, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=100, high=115, low=95, close=105, volume=1100),
        ]
        indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={"SMA5": 100, "SMA25": 95, "SMA75": 105}),
            IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 2), indicators={"SMA5": 105, "SMA25": 100, "SMA75": 100}), # SMAが全て同じでレンジ
        ]
        results = self.feature.calculate(ohlcv_data, indicator_data)
        last_result = results[-1]
        # このケースではSMAの並び順が複雑なため、レンジまたは複雑な状況に該当し50.0となるはず
        self.assertEqual(last_result.score, 50.0) 
        self.assertEqual(last_result.raw_value, 50.0)

    def test_calculate_empty_indicator_data(self):
        results = self.feature.calculate(self.ohlcv_data, [])
        self.assertEqual(len(results), 0)

    def test_normalize_score(self):
        self.assertEqual(self.feature._normalize_score(50, 0, 100), 50.0)
        self.assertEqual(self.feature._normalize_score(0, 0, 100), 0.0)
        self.assertEqual(self.feature._normalize_score(100, 0, 100), 100.0)
        self.assertEqual(self.feature._normalize_score(10, 0, 50), 20.0)
        self.assertEqual(self.feature._normalize_score(50, 50, 50), 50.0) # min_val == max_val
        self.assertEqual(self.feature._normalize_score(-10, 0, 100), 0.0) # 範囲外の下限
        self.assertEqual(self.feature._normalize_score(110, 0, 100), 100.0) # 範囲外の上限

if __name__ == '__main__':
    unittest.main()
