import unittest
from datetime import date
from typing import Dict, List, Optional

import src.score_engine  # レジストリ登録を確認するためパッケージをインポート
from src.model.data_models import (
    FeatureResultModel,
    FeatureSetModel,
    IndicatorSetModel,
    OhlcvModel,
    PatternResultModel,
    PatternSetModel,
)
from src.score_engine.manager import ScoreManager
from src.score_engine.registry import score_registry
from src.score_engine.scores.strategy import (
    FUNDAMENTAL_FEATURE_IDS,
    StrategyScoreCalculator,
    StrategyScoreConfig,
)


class TestStrategyScoreCalculator(unittest.TestCase):
    def setUp(self):
        self.calculator = StrategyScoreCalculator()
        self.symbol = "7203.T"
        self.target_date = date(2025, 2, 1)

    def _build_feature_set(
        self,
        scores: Dict[str, float],
        metadata_map: Optional[Dict[str, Dict]] = None,
    ) -> FeatureSetModel:
        metadata_map = metadata_map or {}
        results = [
            FeatureResultModel(
                feature_id=fid,
                feature_name=fid,
                score=val,
                raw_value=val,
                metadata=metadata_map.get(fid, {}),
                date=self.target_date,
            )
            for fid, val in scores.items()
        ]
        return FeatureSetModel(symbol=self.symbol, date=self.target_date, results=results)

    def _build_pattern_set(self, patterns: Dict[str, float]) -> PatternSetModel:
        results = [
            PatternResultModel(
                pattern_id=pid,
                pattern_name=pid,
                confidence=conf,
                metadata={"date": self.target_date},
            )
            for pid, conf in patterns.items()
        ]
        return PatternSetModel(symbol=self.symbol, date=self.target_date, results=results)

    def test_missing_core_features_returns_watch_zero(self):
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 90.0,
                "T001_TrendStrengthScore": 85.0,
                "P001_PullbackScore": 80.0,
                # P002_BreakoutScore を意図的に欠損させる
            }
        )
        results = self.calculator.calculate([fs], [])
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.score_id, "S002_StrategyScore")
        self.assertEqual(res.total_score, 0.0)
        self.assertEqual(res.strategy_type, "watch")
        self.assertTrue(any("P002_BreakoutScore" in r for r in res.reasons))

    def test_gate1_failed_by_low_trend_env_score(self):
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 30.0,
                "T001_TrendStrengthScore": 40.0,  # trend_env = 35.0 < 50.0
                "P001_PullbackScore": 90.0,
                "P002_BreakoutScore": 90.0,
                "O001_MomentumScore": 80.0,
                "V001_VolumeScore": 80.0,
            }
        )
        res = self.calculator.calculate([fs], [])[0]
        self.assertEqual(res.strategy_type, "watch")
        self.assertLessEqual(res.total_score, 35.0)
        self.assertFalse(res.metadata["gate1_passed"])

    def test_gate1_failed_by_close_below_sma75(self):
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 80.0,
                "T001_TrendStrengthScore": 80.0,  # trend_env = 80.0
                "P001_PullbackScore": 90.0,
                "P002_BreakoutScore": 90.0,
            },
            metadata_map={
                "P001_PullbackScore": {
                    "close": 950.0,
                    "sma5": 980.0,
                    "sma25": 990.0,
                    "sma75": 1000.0,
                }
            },
        )
        res = self.calculator.calculate([fs], [])[0]
        self.assertEqual(res.strategy_type, "watch")
        self.assertLessEqual(res.total_score, 35.0)
        self.assertFalse(res.metadata["gate1_passed"])
        self.assertTrue(any("75日移動平均線" in r for r in res.reasons))

    def test_double_top_normal_penalty(self):
        base_scores = {
            "M001_MAAlignmentScore": 80.0,
            "T001_TrendStrengthScore": 80.0,
            "P001_PullbackScore": 85.0,
            "P002_BreakoutScore": 60.0,
            "O001_MomentumScore": 70.0,
            "V001_VolumeScore": 70.0,
            "R001_VolatilityScore": 50.0,
        }
        fs = self._build_feature_set(base_scores)
        no_dt_res = self.calculator.calculate([fs], [])[0]

        ps = self._build_pattern_set({"R002_DoubleTop": 50.0})
        dt_res = self.calculator.calculate([fs], [ps])[0]

        expected_penalty = 50.0 * 0.35
        self.assertAlmostEqual(dt_res.sub_scores["penalty_score"], expected_penalty)
        self.assertAlmostEqual(dt_res.total_score, no_dt_res.total_score - expected_penalty)

    def test_double_top_high_confidence_cap_and_watch(self):
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 90.0,
                "T001_TrendStrengthScore": 90.0,
                "P001_PullbackScore": 95.0,
                "P002_BreakoutScore": 95.0,
                "O001_MomentumScore": 90.0,
                "V001_VolumeScore": 90.0,
            }
        )
        ps = self._build_pattern_set({"R002_DoubleTop": 80.0})
        res = self.calculator.calculate([fs], [ps])[0]

        self.assertAlmostEqual(res.sub_scores["penalty_score"], 80.0 * 0.35)
        self.assertLessEqual(res.total_score, 40.0)
        self.assertEqual(res.strategy_type, "watch")

    def test_extreme_volatility_penalty(self):
        # 新R001は高いほど安定・低リスクのため、低スコア(<=10.0)で異常過熱ペナルティが発動する
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 80.0,
                "T001_TrendStrengthScore": 80.0,
                "P001_PullbackScore": 80.0,
                "P002_BreakoutScore": 80.0,
                "R001_VolatilityScore": 8.0,
            }
        )
        res = self.calculator.calculate([fs], [])[0]
        self.assertAlmostEqual(res.sub_scores["penalty_score"], 10.0)
        self.assertAlmostEqual(res.metadata["volatility_stability"], 8.0)
        self.assertTrue(any("異常ボラティリティ" in r for r in res.reasons))

    def test_extreme_volatility_penalty_by_volatility_ratio(self):
        # R001スコアが中程度でも volatility_ratio >= 2.0 なら異常過熱ペナルティが発動する
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 80.0,
                "T001_TrendStrengthScore": 80.0,
                "P001_PullbackScore": 80.0,
                "P002_BreakoutScore": 80.0,
                "R001_VolatilityScore": 60.0,
            },
            metadata_map={
                "R001_VolatilityScore": {"volatility_ratio": 2.2},
            },
        )
        res = self.calculator.calculate([fs], [])[0]
        self.assertAlmostEqual(res.sub_scores["penalty_score"], 10.0)
        self.assertAlmostEqual(res.metadata["volatility_stability"], 60.0)
        self.assertTrue(any("異常ボラティリティ" in r for r in res.reasons))

    def test_pullback_strategy_dominant_with_bonuses(self):
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 90.0,
                "T001_TrendStrengthScore": 80.0,  # trend_env = 85.0
                "P001_PullbackScore": 90.0,
                "P002_BreakoutScore": 40.0,
                "O001_MomentumScore": 70.0,
                "V001_VolumeScore": 50.0,
                "R001_VolatilityScore": 50.0,  # vol_stability = 50.0
                "F001_ProfitabilityScore": 80.0,
                "F002_GrowthScore": 80.0,
            }
        )
        ps = self._build_pattern_set(
            {
                "R001_DoubleBottom": 80.0,  # +8.0
                "P001_Hammer": 60.0,  # +3.0
            }
        )
        res = self.calculator.calculate([fs], [ps])[0]
        self.assertEqual(res.strategy_type, "pullback")
        self.assertAlmostEqual(res.sub_scores["pullback_strategy_score"], 89.9)
        self.assertAlmostEqual(res.sub_scores["breakout_strategy_score"], 55.5)
        self.assertAlmostEqual(res.total_score, 89.9)

    def test_breakout_strategy_dominant(self):
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 80.0,
                "T001_TrendStrengthScore": 80.0,  # trend_env = 80.0
                "P001_PullbackScore": 40.0,
                "P002_BreakoutScore": 95.0,
                "O001_MomentumScore": 80.0,
                "V001_VolumeScore": 90.0,
                "R001_VolatilityScore": 50.0,
                "F001_ProfitabilityScore": 70.0,
            }
        )
        res = self.calculator.calculate([fs], [])[0]
        self.assertEqual(res.strategy_type, "breakout")
        self.assertAlmostEqual(res.sub_scores["breakout_strategy_score"], 87.5)
        self.assertAlmostEqual(res.sub_scores["pullback_strategy_score"], 61.3)
        self.assertAlmostEqual(res.total_score, 87.5)

    def test_missing_fundamentals_neutral_50(self):
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 80.0,
                "T001_TrendStrengthScore": 80.0,
                "P001_PullbackScore": 80.0,
                "P002_BreakoutScore": 60.0,
            }
        )
        res = self.calculator.calculate([fs], [])[0]
        self.assertAlmostEqual(res.sub_scores["fundamental_score"], 50.0)
        self.assertTrue(any("中立値(50.0)" in r for r in res.reasons))

    def test_key_levels_and_risk_metrics_with_ohlcv_and_indicators(self):
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 80.0,
                "T001_TrendStrengthScore": 80.0,
                "P001_PullbackScore": 80.0,
                "P002_BreakoutScore": 70.0,
                "R001_VolatilityScore": 60.0,
            },
            metadata_map={
                "R001_VolatilityScore": {"tr_today": 30.0, "avg_atr": 20.0},
            },
        )
        ohlcv = OhlcvModel(
            symbol=self.symbol,
            date=self.target_date,
            open=1080.0,
            high=1120.0,
            low=1070.0,
            close=1100.0,
            volume=3000,
        )
        ind_set = IndicatorSetModel(
            symbol=self.symbol,
            date=self.target_date,
            indicators={
                "SMA5": 1050.0,
                "SMA25": 1000.0,
                "SMA75": 950.0,
                "HIGHEST_HIGH_20": 1150.0,
                "LOWEST_LOW_20": 920.0,
                "ATR14": 22.0,
                "VOLUME_RATIO": 1.8,
            },
        )
        res = self.calculator.calculate([fs], [], ohlcv_data=[ohlcv], indicator_sets=[ind_set])[0]
        self.assertAlmostEqual(res.key_levels["close"], 1100.0)
        self.assertAlmostEqual(res.key_levels["sma25"], 1000.0)
        self.assertAlmostEqual(res.key_levels["highest_high"], 1150.0)
        self.assertAlmostEqual(res.key_levels["lowest_low"], 920.0)
        self.assertAlmostEqual(res.key_levels["sma25_deviation_pct"], 10.0)
        self.assertAlmostEqual(res.risk_metrics["atr"], 22.0)
        self.assertAlmostEqual(res.risk_metrics["atr_pct"], (22.0 / 1100.0) * 100.0)
        self.assertAlmostEqual(res.risk_metrics["volatility_ratio"], 1.5)
        self.assertAlmostEqual(res.risk_metrics["volume_ratio"], 1.8)

    def test_key_levels_and_risk_metrics_fallback_from_metadata(self):
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 80.0,
                "T001_TrendStrengthScore": 80.0,
                "P001_PullbackScore": 80.0,
                "P002_BreakoutScore": 70.0,
                "V001_VolumeScore": 75.0,
                "R001_VolatilityScore": 60.0,
            },
            metadata_map={
                "P001_PullbackScore": {
                    "close": 1020.0,
                    "sma5": 1010.0,
                    "sma25": 1000.0,
                    "sma75": 900.0,
                },
                "P002_BreakoutScore": {
                    "close": 1020.0,
                    "highest_high": 1050.0,
                },
                "R001_VolatilityScore": {
                    "close": 1020.0,
                    "tr_today": 24.0,
                    "avg_atr": 20.0,
                },
                "V001_VolumeScore": {
                    "volume": 2000,
                    "avg_volume_25": 1000.0,
                },
            },
        )
        res = self.calculator.calculate([fs], [])[0]
        self.assertAlmostEqual(res.key_levels["close"], 1020.0)
        self.assertAlmostEqual(res.key_levels["sma25"], 1000.0)
        self.assertAlmostEqual(res.key_levels["highest_high"], 1050.0)
        self.assertIsNone(res.key_levels["lowest_low"])
        self.assertAlmostEqual(res.key_levels["sma25_deviation_pct"], 2.0)
        self.assertAlmostEqual(res.risk_metrics["atr"], 20.0)
        self.assertAlmostEqual(res.risk_metrics["atr_pct"], (20.0 / 1020.0) * 100.0)
        self.assertAlmostEqual(res.risk_metrics["volatility_ratio"], 1.2)
        self.assertAlmostEqual(res.risk_metrics["volume_ratio"], 2.0)

    def test_score_manager_integration_and_registry(self):
        registered_ids = [s["score_id"] for s in score_registry.list_score_calculators()]
        self.assertIn("S001_OverallScore", registered_ids)
        self.assertIn("S002_StrategyScore", registered_ids)

        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 85.0,
                "T001_TrendStrengthScore": 85.0,
                "P001_PullbackScore": 85.0,
                "P002_BreakoutScore": 65.0,
            }
        )
        ps = self._build_pattern_set({"R001_DoubleBottom": 50.0})
        ohlcv = OhlcvModel(
            symbol=self.symbol,
            date=self.target_date,
            open=1000.0,
            high=1030.0,
            low=990.0,
            close=1020.0,
            volume=1500,
        )
        ind_set = IndicatorSetModel(
            symbol=self.symbol,
            date=self.target_date,
            indicators={
                "SMA5": 1010.0,
                "SMA25": 1000.0,
                "SMA75": 950.0,
                "HIGHEST_HIGH_20": 1050.0,
                "LOWEST_LOW_20": 930.0,
                "ATR14": 18.0,
                "VOLUME_RATIO": 1.3,
            },
        )

        manager = ScoreManager()
        all_results = manager.calculate_scores(
            [fs], [ps], ohlcv_data=[ohlcv], indicator_sets=[ind_set]
        )
        result_ids = {r.score_id for r in all_results}
        self.assertEqual(result_ids, {"S001_OverallScore", "S002_StrategyScore"})

        strategy_only = manager.calculate_scores(
            [fs],
            [ps],
            score_ids=["S002_StrategyScore"],
            ohlcv_data=[ohlcv],
            indicator_sets=[ind_set],
        )
        self.assertEqual(len(strategy_only), 1)
        self.assertAlmostEqual(strategy_only[0].key_levels["lowest_low"], 930.0)
        self.assertAlmostEqual(strategy_only[0].risk_metrics["volume_ratio"], 1.3)

    def test_gate2_only_breakout_eligible_uses_breakout_score_as_total(self):
        # 押し目スコアの方が高く見えても P001 < 55 で押し目不成立、P002 >= 55 でブレイクアウト成立時は breakout スコアを採用
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 100.0,
                "T001_TrendStrengthScore": 100.0,
                "P001_PullbackScore": 50.0,   # < 55 (押し目セットアップ未達)
                "P002_BreakoutScore": 65.0,   # >= 55 (ブレイクアウト成立)
                "V001_VolumeScore": 75.0,
                "O001_MomentumScore": 90.0,
                "R001_VolatilityScore": 50.0,
                "F001_ProfitabilityScore": 90.0,
            }
        )
        # DoubleBottom と Hammer で押し目スコアを意図的にブレイクアウトより高く押し上げる
        ps = self._build_pattern_set({"R001_DoubleBottom": 100.0, "P001_Hammer": 100.0})
        res = self.calculator.calculate([fs], [ps])[0]
        self.assertGreater(res.sub_scores["pullback_strategy_score"], res.sub_scores["breakout_strategy_score"])
        self.assertEqual(res.strategy_type, "breakout")
        self.assertAlmostEqual(res.total_score, res.sub_scores["breakout_strategy_score"])

    def test_gate2_both_setups_ineligible_returns_watch_and_capped_score(self):
        # トレンド環境・ファンダが良好でも P001 < 55 かつ P002 < 55 なら watch かつ watch_score_cap(59.0) 以下
        fs = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 100.0,
                "T001_TrendStrengthScore": 100.0,
                "P001_PullbackScore": 50.0,   # < 55
                "P002_BreakoutScore": 50.0,   # < 55
                "V001_VolumeScore": 90.0,
                "O001_MomentumScore": 90.0,
                "R001_VolatilityScore": 50.0,
                "F001_ProfitabilityScore": 90.0,
            }
        )
        ps = self._build_pattern_set({"R001_DoubleBottom": 100.0})
        res = self.calculator.calculate([fs], [ps])[0]
        self.assertEqual(res.strategy_type, "watch")
        self.assertLessEqual(res.total_score, self.calculator.config.watch_score_cap)
        self.assertTrue(any("主軸セットアップ条件" in r for r in res.reasons))

    def test_strategy_specific_rsi_bell_and_overheat_penalty(self):
        base_scores = {
            "M001_MAAlignmentScore": 80.0,
            "T001_TrendStrengthScore": 80.0,
            "P001_PullbackScore": 75.0,
            "P002_BreakoutScore": 75.0,
            "O001_MomentumScore": 60.0,
            "V001_VolumeScore": 70.0,
            "R001_VolatilityScore": 60.0,
        }
        # RSI14=48 (押し目理想帯 40〜60 内、ブレイク理想帯 55〜75 未満)
        fs_pullback_rsi = self._build_feature_set(
            base_scores,
            metadata_map={"O001_MomentumScore": {"rsi14": 48.0}},
        )
        res_pb = self.calculator.calculate([fs_pullback_rsi], [])[0]

        # RSI14=70 (ブレイク理想帯 55〜75 内、押し目理想帯超え)
        fs_breakout_rsi = self._build_feature_set(
            base_scores,
            metadata_map={"O001_MomentumScore": {"rsi14": 70.0}},
        )
        res_bo = self.calculator.calculate([fs_breakout_rsi], [])[0]

        self.assertGreater(
            res_pb.sub_scores["pullback_strategy_score"],
            res_bo.sub_scores["pullback_strategy_score"],
        )
        self.assertGreater(
            res_bo.sub_scores["breakout_strategy_score"],
            res_pb.sub_scores["breakout_strategy_score"],
        )

        # indicator_set フォールバック＋RSI14 > 80 過熱減点
        fs_no_meta_rsi = self._build_feature_set(base_scores)
        ind_overheat = IndicatorSetModel(
            symbol=self.symbol,
            date=self.target_date,
            indicators={"RSI14": 85.0},
        )
        res_overheat = self.calculator.calculate(
            [fs_no_meta_rsi], [], indicator_sets=[ind_overheat]
        )[0]
        self.assertAlmostEqual(
            res_overheat.sub_scores["penalty_score"],
            self.calculator.config.rsi_overheat_penalty,
        )
        self.assertTrue(any("RSI過熱" in r for r in res_overheat.reasons))

    def test_short_rsi_rebound_bonus(self):
        base_scores = {
            "M001_MAAlignmentScore": 80.0,
            "T001_TrendStrengthScore": 80.0,
            "P001_PullbackScore": 75.0,
            "P002_BreakoutScore": 75.0,
            "O001_MomentumScore": 65.0,
            "V001_VolumeScore": 65.0,
            "R001_VolatilityScore": 60.0,
        }
        fs_no_rebound = self._build_feature_set(
            base_scores,
            metadata_map={"O001_MomentumScore": {"prev_short_rsi": 40.0, "short_rsi": 50.0}},
        )
        fs_rebound = self._build_feature_set(
            base_scores,
            metadata_map={"O001_MomentumScore": {"prev_short_rsi": 30.0, "short_rsi": 42.0}},
        )
        res_base = self.calculator.calculate([fs_no_rebound], [])[0]
        res_reb = self.calculator.calculate([fs_rebound], [])[0]

        self.assertAlmostEqual(
            res_reb.sub_scores["pullback_strategy_score"] - res_base.sub_scores["pullback_strategy_score"],
            self.calculator.config.short_rsi_rebound_bonus,
        )
        self.assertAlmostEqual(
            res_reb.sub_scores["breakout_strategy_score"],
            res_base.sub_scores["breakout_strategy_score"],
        )
        self.assertTrue(any("短期RSI反転" in r for r in res_reb.reasons))

    def test_pullback_dryup_rebound_bonus(self):
        base_scores = {
            "M001_MAAlignmentScore": 80.0,
            "T001_TrendStrengthScore": 80.0,
            "P001_PullbackScore": 75.0,
            "P002_BreakoutScore": 75.0,
            "O001_MomentumScore": 65.0,
            "V001_VolumeScore": 65.0,
            "R001_VolatilityScore": 60.0,
        }
        fs_normal = self._build_feature_set(
            base_scores,
            metadata_map={"V001_VolumeScore": {"pullback_dryup_rebound": False}},
        )
        fs_dryup = self._build_feature_set(
            base_scores,
            metadata_map={"V001_VolumeScore": {"pullback_dryup_rebound": True}},
        )
        res_normal = self.calculator.calculate([fs_normal], [])[0]
        res_dryup = self.calculator.calculate([fs_dryup], [])[0]

        self.assertAlmostEqual(
            res_dryup.sub_scores["pullback_strategy_score"] - res_normal.sub_scores["pullback_strategy_score"],
            self.calculator.config.pullback_dryup_rebound_bonus,
        )
        self.assertAlmostEqual(
            res_dryup.sub_scores["breakout_strategy_score"],
            res_normal.sub_scores["breakout_strategy_score"],
        )
        self.assertTrue(any("押し目売り枯れ" in r for r in res_dryup.reasons))

    def test_sma75_dev_overheat_penalty(self):
        base_scores = {
            "M001_MAAlignmentScore": 80.0,
            "T001_TrendStrengthScore": 80.0,
            "P001_PullbackScore": 75.0,
            "P002_BreakoutScore": 75.0,
            "O001_MomentumScore": 70.0,
            "V001_VolumeScore": 70.0,
            "R001_VolatilityScore": 60.0,
        }
        # 乖離率 (1150 - 1000)/1000 = 15% <= 25% (ペナルティなし)
        fs_ok = self._build_feature_set(
            base_scores,
            metadata_map={"P001_PullbackScore": {"close": 1150.0, "sma75": 1000.0}},
        )
        # 乖離率 (1300 - 1000)/1000 = 30% > 25% (ペナルティあり)
        fs_overheat = self._build_feature_set(
            base_scores,
            metadata_map={"P001_PullbackScore": {"close": 1300.0, "sma75": 1000.0}},
        )
        res_ok = self.calculator.calculate([fs_ok], [])[0]
        res_oh = self.calculator.calculate([fs_overheat], [])[0]

        expected_pen = self.calculator.config.sma75_dev_overheat_penalty
        self.assertAlmostEqual(res_oh.sub_scores["penalty_score"], expected_pen)
        self.assertAlmostEqual(
            res_ok.sub_scores["pullback_strategy_score"] - res_oh.sub_scores["pullback_strategy_score"],
            expected_pen,
        )
        self.assertAlmostEqual(
            res_ok.sub_scores["breakout_strategy_score"] - res_oh.sub_scores["breakout_strategy_score"],
            expected_pen,
        )
        self.assertTrue(any("75日線乖離過熱" in r for r in res_oh.reasons))

    def test_gap_up_overheat_penalty(self):
        base_scores = {
            "M001_MAAlignmentScore": 80.0,
            "T001_TrendStrengthScore": 80.0,
            "P001_PullbackScore": 75.0,
            "P002_BreakoutScore": 80.0,
            "O001_MomentumScore": 70.0,
            "V001_VolumeScore": 75.0,
            "R001_VolatilityScore": 60.0,
        }
        fs_normal = self._build_feature_set(
            base_scores,
            metadata_map={"P002_BreakoutScore": {"gap_pct": 0.03}},
        )
        fs_gap = self._build_feature_set(
            base_scores,
            metadata_map={"P002_BreakoutScore": {"gap_pct": 0.09}},
        )
        res_normal = self.calculator.calculate([fs_normal], [])[0]
        res_gap = self.calculator.calculate([fs_gap], [])[0]

        self.assertAlmostEqual(
            res_normal.sub_scores["breakout_strategy_score"] - res_gap.sub_scores["breakout_strategy_score"],
            self.calculator.config.gap_up_overheat_penalty,
        )
        # 押し目戦略には影響しない
        self.assertAlmostEqual(
            res_gap.sub_scores["pullback_strategy_score"],
            res_normal.sub_scores["pullback_strategy_score"],
        )
        self.assertTrue(any("大幅ギャップアップ過熱" in r for r in res_gap.reasons))

    def test_nan_and_inf_guards(self):
        # _calc_rsi_bell_score に NaN/inf を渡しても満点にならず中立 50.0 を返す
        self.assertEqual(self.calculator._calc_rsi_bell_score(float("nan"), 40.0, 60.0), 50.0)
        self.assertEqual(self.calculator._calc_rsi_bell_score(float("inf"), 40.0, 60.0), 50.0)

        # metadata に NaN/inf が混入しても None として安全にフォールバックし例外・不正満点にならない
        fs_nan = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 80.0,
                "T001_TrendStrengthScore": 80.0,
                "P001_PullbackScore": 75.0,
                "P002_BreakoutScore": 75.0,
                "O001_MomentumScore": 60.0,
                "V001_VolumeScore": 70.0,
                "R001_VolatilityScore": 60.0,
            },
            metadata_map={
                "O001_MomentumScore": {
                    "rsi14": float("nan"),
                    "short_rsi": float("inf"),
                    "prev_short_rsi": 20.0,
                },
                "P002_BreakoutScore": {"gap_pct": float("nan")},
                "R001_VolatilityScore": {"volatility_ratio": float("inf")},
            },
        )
        fs_plain = self._build_feature_set(
            {
                "M001_MAAlignmentScore": 80.0,
                "T001_TrendStrengthScore": 80.0,
                "P001_PullbackScore": 75.0,
                "P002_BreakoutScore": 75.0,
                "O001_MomentumScore": 60.0,
                "V001_VolumeScore": 70.0,
                "R001_VolatilityScore": 60.0,
            }
        )
        res_nan = self.calculator.calculate([fs_nan], [])[0]
        res_plain = self.calculator.calculate([fs_plain], [])[0]
        self.assertAlmostEqual(
            res_nan.sub_scores["pullback_strategy_score"],
            res_plain.sub_scores["pullback_strategy_score"],
        )
        self.assertAlmostEqual(
            res_nan.sub_scores["breakout_strategy_score"],
            res_plain.sub_scores["breakout_strategy_score"],
        )
        self.assertAlmostEqual(res_nan.sub_scores["penalty_score"], 0.0)

    def test_fundamental_score_includes_f006_shareholder_return_score(self):
        self.assertIn("F006_ShareholderReturnScore", FUNDAMENTAL_FEATURE_IDS)
        self.assertEqual(len(FUNDAMENTAL_FEATURE_IDS), 6)

        base_tech = {
            "M001_MAAlignmentScore": 80.0,
            "T001_TrendStrengthScore": 80.0,
            "P001_PullbackScore": 80.0,
            "P002_BreakoutScore": 60.0,
            "O001_MomentumScore": 70.0,
            "V001_VolumeScore": 70.0,
            "R001_VolatilityScore": 60.0,
        }
        fs_all_f = self._build_feature_set(
            {
                **base_tech,
                "F001_ProfitabilityScore": 60.0,
                "F002_GrowthScore": 60.0,
                "F003_ValuationScore": 60.0,
                "F004_FinancialHealthScore": 60.0,
                "F005_EarningsQualityScore": 60.0,
                "F006_ShareholderReturnScore": 90.0,
            }
        )
        fs_f001_to_f005 = self._build_feature_set(
            {
                **base_tech,
                "F001_ProfitabilityScore": 60.0,
                "F002_GrowthScore": 60.0,
                "F003_ValuationScore": 60.0,
                "F004_FinancialHealthScore": 60.0,
                "F005_EarningsQualityScore": 60.0,
            }
        )
        res_all = self.calculator.calculate([fs_all_f], [])[0]
        res_5 = self.calculator.calculate([fs_f001_to_f005], [])[0]

        self.assertAlmostEqual(res_all.sub_scores["fundamental_score"], 65.0)
        self.assertAlmostEqual(res_5.sub_scores["fundamental_score"], 60.0)
        self.assertGreater(res_all.total_score, res_5.total_score)


if __name__ == "__main__":
    unittest.main()
