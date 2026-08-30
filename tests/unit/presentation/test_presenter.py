import unittest
from datetime import datetime
from unittest.mock import patch
from src.presentation.presenter import Presenter
from src.model.data_models import AnalysisResultModel, FeatureResultModel, PatternResultModel

class TestPresenter(unittest.TestCase):
    @patch("builtins.print")
    def test_display_cli(self, mock_print):
        presenter = Presenter()
        results = [
            AnalysisResultModel(
                symbol="7203.T",
                company_name="Company_7203.T",
                total_score=85.0,
                feature_results=[
                    FeatureResultModel(feature_id="M001_MAAlignmentScore", feature_name="MA Alignment", score=80.0, raw_value=80.0, metadata={})
                ],
                pattern_results=[
                    PatternResultModel(pattern_id="R001_DoubleBottom", pattern_name="Double Bottom", detected=True, confidence=90.0, details={})
                ],
                rank=1,
                summary="テストサマリー"
            )
        ]
        
        presenter.display_results(results, output_type="cli")
        
        # printが呼ばれていることを確認
        self.assertTrue(mock_print.called)

    @patch("builtins.print")
    def test_display_empty(self, mock_print):
        presenter = Presenter()
        presenter.display_results([], output_type="cli")
        mock_print.assert_any_call("表示する分析結果がありません。")

if __name__ == "__main__":
    unittest.main()
