import unittest
from datetime import datetime

from src.feature_engine.registry import feature_registry
from src.pattern_detector.registry import pattern_registry
from src.score_engine.registry import score_registry

# Import modules to ensure registry population
import src.feature_engine.features.moving_average.ma_alignment_score
import src.feature_engine.features.price_action.pullback_score
import src.feature_engine.features.price_action.breakout_score
import src.feature_engine.features.trend
import src.feature_engine.features.volume.volume_score
import src.feature_engine.features.oscillator.momentum_score
import src.feature_engine.features.risc.volatility_score
import src.feature_engine.features.fundamental.profitability_score
import src.feature_engine.features.fundamental.growth_score
import src.feature_engine.features.fundamental.valuation_score
import src.feature_engine.features.fundamental.financial_health_score
import src.feature_engine.features.fundamental.earnings_quality_score

import src.pattern_detector.patterns.reversal.double_bottom
import src.pattern_detector.patterns.reversal.double_top

import src.score_engine.scores.overall
from src.model.data_models import (
    FeatureSetModel,
    PatternSetModel,
    FeatureResultModel,
    PatternResultModel
)

class TestPipelineIntegration(unittest.TestCase):
    def test_registry_coverage(self):
        """
        主要な特徴量とパターンがレジストリに正しく登録されていることを検証する。
        """
        features = feature_registry.list_features()
        feature_ids = [f["feature_id"] for f in features]
        
        expected_features = [
            "M001_MAAlignmentScore",
            "P001_PullbackScore",
            "P002_BreakoutScore",
            "T001_TrendStrengthScore",
            "V001_VolumeScore",
            "O001_MomentumScore",
            "R001_VolatilityScore",
            "F001_ProfitabilityScore",
            "F002_GrowthScore",
            "F003_ValuationScore",
            "F004_FinancialHealthScore",
            "F005_EarningsQualityScore",
        ]
        for ef in expected_features:
            self.assertIn(ef, feature_ids, f"Feature {ef} is not registered.")

        patterns = pattern_registry.list_patterns()
        pattern_ids = [p["pattern_id"] for p in patterns]
        
        expected_patterns = [
            "R001_DoubleBottom",
            "R002_DoubleTop",
        ]
        for ep in expected_patterns:
            self.assertIn(ep, pattern_ids, f"Pattern {ep} is not registered.")

        scores = score_registry.list_score_calculators()
        score_ids = [s["score_id"] for s in scores]
        self.assertIn("S001_OverallScore", score_ids, "S001_OverallScore is not registered.")

    def test_score_engine_integration(self):
        """
        ScoreEngine (OverallScoreCalculator) が FeatureSetModel と PatternSetModel を受け取り、
        正しく総合スコアを計算できるかを検証する。
        """
        calculator = score_registry.get_score_calculator("S001_OverallScore")
        
        feature_sets = [
            FeatureSetModel(
                symbol="7203.T",
                date=datetime(2026, 1, 1),
                results=[
                    FeatureResultModel(feature_id="M001_MAAlignmentScore", feature_name="MA Alignment", score=80.0, raw_value=80.0, metadata={}),
                    FeatureResultModel(feature_id="T001_TrendStrengthScore", feature_name="Trend Strength", score=70.0, raw_value=70.0, metadata={})
                ]
            )
        ]
        
        pattern_sets = [
            PatternSetModel(
                symbol="7203.T",
                date=datetime(2026, 1, 1),
                results=[
                    PatternResultModel(pattern_id="R001_DoubleBottom", pattern_name="Double Bottom", detected=True, confidence=90.0, details={})
                ]
            )
        ]

        results = calculator.calculate(feature_sets, pattern_sets)
        
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.symbol, "7203.T")
        self.assertGreater(res.total_score, 0.0)
        self.assertIn("FeatureAverageScore", res.sub_scores)
        self.assertIn("PatternAverageConfidence", res.sub_scores)

if __name__ == "__main__":
    unittest.main()
