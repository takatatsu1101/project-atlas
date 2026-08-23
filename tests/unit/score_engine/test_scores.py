
import unittest
from datetime import date
from typing import List
import numpy as np

from src.score_engine.scores.overall import OverallScoreCalculator
from src.model.data_models import FeatureSetModel, PatternSetModel, ScoreResultModel, FeatureResultModel, PatternResultModel

class TestOverallScoreCalculator(unittest.TestCase):

    def setUp(self):
        self.calculator = OverallScoreCalculator()
        self.symbol = "TEST"

        self.feature_sets_data = [
            FeatureSetModel(
                symbol=self.symbol, date=date(2025, 1, 1),
                results=[
                    FeatureResultModel(feature_id="F1", feature_name="Feature1", score=80.0, raw_value=80.0),
                    FeatureResultModel(feature_id="F2", feature_name="Feature2", score=70.0, raw_value=70.0),
                ]
            ),
            FeatureSetModel(
                symbol=self.symbol, date=date(2025, 1, 2),
                results=[
                    FeatureResultModel(feature_id="F1", feature_name="Feature1", score=90.0, raw_value=90.0),
                    FeatureResultModel(feature_id="F2", feature_name="Feature2", score=85.0, raw_value=85.0),
                ]
            ),
        ]

        self.pattern_sets_data = [
            PatternSetModel(
                symbol=self.symbol, date=date(2025, 1, 1),
                results=[
                    PatternResultModel(pattern_id="P1", pattern_name="Pattern1", confidence=90.0),
                ]
            ),
            PatternSetModel(
                symbol=self.symbol, date=date(2025, 1, 2),
                results=[
                    PatternResultModel(pattern_id="P1", pattern_name="Pattern1", confidence=70.0),
                    PatternResultModel(pattern_id="P2", pattern_name="Pattern2", confidence=60.0),
                ]
            ),
        ]

    def test_score_properties(self):
        self.assertEqual(self.calculator.score_id, "S001_OverallScore")
        self.assertEqual(self.calculator.score_name, "総合スコア")
        self.assertEqual(self.calculator.score_category, "Overall")

    def test_calculate_overall_score(self):
        score_results = self.calculator.calculate(self.feature_sets_data, self.pattern_sets_data)

        self.assertEqual(len(score_results), 2)
        self.assertIsInstance(score_results[0], ScoreResultModel)
        self.assertEqual(score_results[0].symbol, self.symbol)
        self.assertEqual(score_results[0].date, date(2025, 1, 1))
        
        # 2025-01-01 の計算: (80 + 70 + 90) / 3 = 80
        self.assertAlmostEqual(score_results[0].total_score, 80.0)
        self.assertAlmostEqual(score_results[0].sub_scores["FeatureAverageScore"], 75.0)
        self.assertAlmostEqual(score_results[0].sub_scores["PatternAverageConfidence"], 90.0)

        # 2025-01-02 の計算: (90 + 85 + 70 + 60) / 4 = 76.25
        self.assertAlmostEqual(score_results[1].total_score, 76.25)
        self.assertAlmostEqual(score_results[1].sub_scores["FeatureAverageScore"], 87.5)
        self.assertAlmostEqual(score_results[1].sub_scores["PatternAverageConfidence"], 65.0)

    def test_calculate_empty_data(self):
        results_no_data = self.calculator.calculate([], [])
        self.assertEqual(len(results_no_data), 0)

        results_only_features = self.calculator.calculate(self.feature_sets_data, [])
        self.assertEqual(len(results_only_features), 2)
        self.assertAlmostEqual(results_only_features[0].total_score, 75.0)

        results_only_patterns = self.calculator.calculate([], self.pattern_sets_data)
        self.assertEqual(len(results_only_patterns), 2)
        self.assertAlmostEqual(results_only_patterns[0].total_score, 90.0)

    def test_normalize_score(self):
        self.assertEqual(self.calculator._normalize_score(50, 0, 100), 50.0)
        self.assertEqual(self.calculator._normalize_score(0, 0, 100), 0.0)
        self.assertEqual(self.calculator._normalize_score(100, 0, 100), 100.0)
        self.assertEqual(self.calculator._normalize_score(10, 0, 50), 20.0)
        self.assertEqual(self.calculator._normalize_score(50, 50, 50), 50.0)
        self.assertEqual(self.calculator._normalize_score(-10, 0, 100), 0.0)
        self.assertEqual(self.calculator._normalize_score(110, 0, 100), 100.0)

if __name__ == '__main__':
    unittest.main()
