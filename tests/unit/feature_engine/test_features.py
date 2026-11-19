
import tempfile
import unittest
from datetime import date, timedelta
from typing import List
from unittest.mock import patch
import numpy as np

import src.feature_engine
from src.common.storage import StorageManager
from src.feature_engine.interfaces import IFeature
from src.feature_engine.manager import FeatureManager
from src.indicator_calculator.calculator import IndicatorCalculator
from src.model.data_models import (
    FeatureResultModel,
    FinancialModel,
    IndicatorSetModel,
    OhlcvModel,
)


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
            net_assets=27_000_000_000.0,
            shareholders_equity=26_500_000_000.0,
            retained_earnings=20_000_000_000.0,
            short_term_debt=2_000_000_000.0,
            long_term_debt=4_000_000_000.0,
            ordinary_profit=3_600_000_000.0,
            operating_cf=4_000_000_000.0,
            investing_cf=-1_500_000_000.0,
            financing_cf=-1_000_000_000.0,
            capex=-1_200_000_000.0,
            free_cash_flow=2_800_000_000.0,
            cash_and_equivalents=8_000_000_000.0,
            operating_cf_margin=13.3,
            dividend_per_share=90.0,
            total_dividends=900_000_000.0,
            share_buyback=300_000_000.0,
            payout_ratio=36.0,
            total_payout_ratio=48.0,
            doe=3.4,
            consecutive_dividend_increase_years=3,
            consecutive_non_decrease_years=5,
            buyback_count_3y=2,
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
        from src.feature_engine.features.moving_average.ma_alignment_score import MAAlignmentScore
        from src.feature_engine.features.oscillator.momentum_score import MomentumScore
        from src.feature_engine.features.price_action.breakout_score import BreakoutScore
        from src.feature_engine.features.price_action.pullback_score import PullbackScore
        from src.feature_engine.features.risc.volatility_score import VolatilityScore
        from src.feature_engine.features.trend import TrendStrengthScore
        from src.feature_engine.features.volume.volume_score import VolumeScore

        # 1. 個別特徴量クラスの単体呼び出しで len(ohlcv) < len(indicator) でも IndexError にならない
        short_ohlcv = self.ohlcv[:10]
        long_ind = self.indicators[:25]
        for feat_cls in (
            MAAlignmentScore,
            TrendStrengthScore,
            PullbackScore,
            BreakoutScore,
            VolatilityScore,
            VolumeScore,
            MomentumScore,
        ):
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

    def test_260_bars_with_sma200_and_hh250_latest_only_matches_full(self):
        """260本データ(SMA200・HIGHEST_HIGH_250有効時)で latest_only=True と False の最終日が一致する"""
        start = date(2024, 1, 1)
        long_ohlcv = []
        for i in range(260):
            close = 1000.0 + i * 2.0 + (i % 7) * 3.0
            long_ohlcv.append(
                OhlcvModel(
                    symbol=self.symbol,
                    date=start + timedelta(days=i),
                    open=close - 3.0,
                    high=close + 7.0,
                    low=close - 7.0,
                    close=close,
                    volume=120_000 + i * 500,
                )
            )
        long_ind = self.ind_calc.calculate_indicators(long_ohlcv, use_cache=False)
        self.assertIn("SMA200", long_ind[-1].indicators)
        self.assertIn("HIGHEST_HIGH_250", long_ind[-1].indicators)

        full_sets = self.manager.calculate_features(
            long_ohlcv, long_ind, self.fin, use_cache=False, latest_only=False
        )
        latest_sets = self.manager.calculate_features(
            long_ohlcv, long_ind, self.fin, use_cache=False, latest_only=True
        )
        self.assertEqual(len(latest_sets), 1)
        full_by_id = {r.feature_id: r for r in full_sets[-1].results}
        latest_by_id = {r.feature_id: r for r in latest_sets[0].results}
        self.assertEqual(set(latest_by_id.keys()), set(full_by_id.keys()))
        for fid, full_res in full_by_id.items():
            lat_res = latest_by_id[fid]
            self.assertAlmostEqual(lat_res.score, full_res.score, places=12)
            self.assertAlmostEqual(lat_res.raw_value, full_res.raw_value, places=12)
            self.assertEqual(lat_res.metadata, full_res.metadata)

if __name__ == '__main__':
    unittest.main()
