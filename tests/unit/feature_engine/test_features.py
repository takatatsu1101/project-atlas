
import tempfile
import unittest
from datetime import date, timedelta
from typing import List
from unittest.mock import patch
import numpy as np

import src.feature_engine
from src.common.storage import StorageManager
from src.feature_engine.features.trend import TrendStrengthFeature
from src.feature_engine.interfaces import IFeature
from src.feature_engine.manager import FeatureManager
from src.indicator_calculator.calculator import IndicatorCalculator
from src.model.data_models import (
    FeatureResultModel,
    FinancialModel,
    IndicatorSetModel,
    OhlcvModel,
)

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


class TestFeatureLatestOnlyAndCacheIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = StorageManager(base_dir=self.temp_dir.name)
        self.manager = FeatureManager()
        self.manager.storage = self.storage
        self.ind_calc = IndicatorCalculator()
        self.ind_calc.storage = self.storage
        self.symbol = "7203.T"

        start = date(2025, 1, 1)
        self.ohlcv = []
        for i in range(90):
            close = 1000.0 + i * 3.0 + (i % 5) * 4.0
            self.ohlcv.append(
                OhlcvModel(
                    symbol=self.symbol,
                    date=start + timedelta(days=i),
                    open=close - 4.0,
                    high=close + 8.0,
                    low=close - 8.0,
                    close=close,
                    volume=100_000 + i * 2_000,
                )
            )
        self.indicators = self.ind_calc.calculate_indicators(self.ohlcv, use_cache=False)
        self.fin = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            eps=120.0,
            bps=1100.0,
            roe=14.0,
            roa=7.5,
            per=11.0,
            pbr=1.1,
            revenue=30_000_000_000.0,
            operating_profit=3_500_000_000.0,
            net_profit=2_500_000_000.0,
            revenue_growth=12.0,
            net_profit_growth=16.0,
            revenue_growth_3y_avg=11.0,
            net_profit_growth_3y_avg=13.0,
            total_assets=60_000_000_000.0,
            equity_ratio=45.0,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_all_13_features_latest_only_matches_full_last_day(self):
        """全13特徴量について latest_only=True が latest_only=False の最終日と完全一致する"""
        registered = self.manager.registry.list_features()
        self.assertEqual(len(registered), 13)

        full_sets = self.manager.calculate_features(
            self.ohlcv, self.indicators, self.fin, use_cache=False, latest_only=False
        )
        latest_sets = self.manager.calculate_features(
            self.ohlcv, self.indicators, self.fin, use_cache=False, latest_only=True
        )

        self.assertEqual(len(full_sets), len(self.ohlcv))
        self.assertEqual(len(latest_sets), 1)
        self.assertEqual(latest_sets[0].date, full_sets[-1].date)
        self.assertEqual(len(latest_sets[0].results), 13)

        full_by_id = {r.feature_id: r for r in full_sets[-1].results}
        latest_by_id = {r.feature_id: r for r in latest_sets[0].results}
        self.assertEqual(set(latest_by_id.keys()), set(full_by_id.keys()))
        for fid, full_res in full_by_id.items():
            lat_res = latest_by_id[fid]
            self.assertEqual(lat_res.date, full_res.date)
            self.assertAlmostEqual(lat_res.score, full_res.score, places=12)
            self.assertAlmostEqual(lat_res.raw_value, full_res.raw_value, places=12)
            self.assertEqual(lat_res.metadata, full_res.metadata)

    def test_latest_only_does_not_overwrite_or_create_full_cache_and_extracts_on_hit(self):
        """latest_only=True / target_indices は全日付キャッシュを作らず・壊さず、既存ヒット時は対象日だけ抽出する"""
        cache_path = f"cache/features_{self.symbol}_all.json"
        cache_file = self.storage.base_dir / cache_path

        # 1. キャッシュ未存在時に latest_only=True を呼んでも全日付キャッシュを作成しない
        res_miss = self.manager.calculate_features(
            self.ohlcv, self.indicators, self.fin, use_cache=True, latest_only=True
        )
        self.assertEqual(len(res_miss), 1)
        self.assertFalse(cache_file.exists())

        # 2. latest_only=False で全日付キャッシュを生成
        full_res = self.manager.calculate_features(
            self.ohlcv, self.indicators, self.fin, use_cache=True, latest_only=False
        )
        self.assertTrue(cache_file.exists())
        saved_before = cache_file.read_text(encoding="utf-8")

        # 3. 既存全日付キャッシュがヒットした場合は計算せず対象日のみ抽出し、キャッシュファイルを変更しない
        with patch.object(
            self.manager.registry.get_feature("P002_BreakoutScore"),
            "calculate",
            side_effect=AssertionError("キャッシュヒット時は再計算されないはず"),
        ):
            hit_latest = self.manager.calculate_features(
                self.ohlcv, self.indicators, self.fin, use_cache=True, latest_only=True
            )
            hit_targets = self.manager.calculate_features(
                self.ohlcv,
                self.indicators,
                self.fin,
                use_cache=True,
                target_indices=[10, -1],
            )

        self.assertEqual(len(hit_latest), 1)
        self.assertEqual(hit_latest[0].date, full_res[-1].date)
        self.assertEqual([fs.date for fs in hit_targets], [full_res[10].date, full_res[-1].date])
        self.assertEqual(cache_file.read_text(encoding="utf-8"), saved_before)

    def test_legacy_feature_without_target_indices_fallback(self):
        """target_indices 非対応のカスタム特徴量でも対象日付のみにフィルタされる"""
        class LegacyFeature(IFeature):
            feature_id = "LEGACY_F"
            feature_name = "レガシー特徴量"
            feature_category = "Custom"

            def calculate(self, ohlcv_data, indicator_data, financial_data=None):
                return [
                    FeatureResultModel(
                        feature_id=self.feature_id,
                        feature_name=self.feature_name,
                        score=50.0,
                        raw_value=50.0,
                        metadata={},
                        date=ind.date,
                    )
                    for ind in indicator_data
                ]

            def _normalize_score(self, raw_value, min_val, max_val):
                return raw_value

        with patch.object(self.manager.registry, "get_feature", return_value=LegacyFeature()):
            res = self.manager.calculate_features(
                self.ohlcv,
                self.indicators,
                self.fin,
                feature_ids=["LEGACY_F"],
                use_cache=False,
                latest_only=True,
            )
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].date, self.indicators[-1].date)

    def test_mismatched_ohlcv_and_indicator_lengths_safe_and_consistent(self):
        """ohlcv_data と indicator_data の長さが異なっても IndexError にならず共通長基準で評価・キャッシュされる"""
        from src.feature_engine.features.price_action.breakout_score import BreakoutScore
        from src.feature_engine.features.risc.volatility_score import VolatilityScore
        from src.feature_engine.features.volume.volume_score import VolumeScore

        # 1. 個別特徴量クラスの単体呼び出しで len(ohlcv) < len(indicator) でも IndexError にならない
        short_ohlcv = self.ohlcv[:10]
        long_ind = self.indicators[:25]
        for feat_cls in (BreakoutScore, VolatilityScore, VolumeScore):
            res_single = feat_cls().calculate(short_ohlcv, long_ind, self.fin)
            self.assertEqual(len(res_single), len(long_ind))

        # 2. FeatureManager: len(ohlcv) < len(indicator)
        res_mgr_short_full = self.manager.calculate_features(
            short_ohlcv, long_ind, self.fin, use_cache=True, latest_only=False
        )
        self.assertEqual(len(res_mgr_short_full), 10)
        self.assertEqual(res_mgr_short_full[-1].date, long_ind[9].date)
        raw_cache = self.storage.load_json(f"cache/features_{self.symbol}_all.json")
        self.assertEqual(len(raw_cache["meta"]["dates"]), 10)
        self.assertEqual(len(raw_cache["items"]), 10)

        res_mgr_short_latest = self.manager.calculate_features(
            short_ohlcv, long_ind, self.fin, use_cache=False, latest_only=True
        )
        self.assertEqual(len(res_mgr_short_latest), 1)
        self.assertEqual(res_mgr_short_latest[0].date, long_ind[9].date)

        # 3. FeatureManager: len(ohlcv) > len(indicator)
        long_ohlcv = self.ohlcv[:25]
        short_ind = self.indicators[:12]
        res_mgr_long_latest = self.manager.calculate_features(
            long_ohlcv, short_ind, self.fin, use_cache=False, latest_only=True
        )
        self.assertEqual(len(res_mgr_long_latest), 1)
        self.assertEqual(res_mgr_long_latest[0].date, short_ind[11].date)

if __name__ == '__main__':
    unittest.main()
