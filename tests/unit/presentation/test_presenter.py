import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.model.data_models import AnalysisResultModel, FeatureResultModel, PatternResultModel
from src.presentation.presenter import Presenter


class TestPresenter(unittest.TestCase):
    def _sample_results(self):
        return [
            AnalysisResultModel(
                symbol="7203.T",
                company_name="トヨタ自動車",
                date=date(2026, 2, 15),
                market="プライム",
                sector="輸送用機器",
                strategy_type="pullback",
                total_score=85.0,
                sub_scores={
                    "pullback_strategy_score": 85.0,
                    "breakout_strategy_score": 60.0,
                    "trend_env_score": 80.0,
                    "fundamental_score": 72.0,
                },
                key_levels={
                    "close": 3100.0,
                    "sma5": 3080.0,
                    "sma25": 3000.0,
                    "sma75": 2850.0,
                    "highest_high": 3200.0,
                    "lowest_low": 2900.0,
                    "sma5_deviation_pct": 0.65,
                    "sma25_deviation_pct": 3.33,
                    "sma75_deviation_pct": 8.77,
                },
                risk_metrics={
                    "atr": 52.0,
                    "atr_pct": 1.68,
                    "volatility_ratio": 1.05,
                    "volume_ratio": 1.42,
                },
                financial_summary={
                    "per": 11.2,
                    "pbr": 1.08,
                    "roe": 12.5,
                    "roa": 4.1,
                    "revenue_growth": 8.2,
                    "net_profit_growth": 14.3,
                    "revenue_growth_3y_avg": 7.5,
                    "net_profit_growth_3y_avg": 11.8,
                    "equity_ratio": 38.5,
                    "eps": 276.0,
                    "bps": 2870.0,
                    "revenue": 45_000_000_000_000.0,
                    "operating_profit": 5_100_000_000_000.0,
                    "net_profit": 4_200_000_000_000.0,
                },
                reasons=[
                    "第1関門（トレンド環境）を通過しました。",
                    "押し目買い戦略を採用しました。",
                ],
                feature_results=[
                    FeatureResultModel(
                        feature_id="M001_MAAlignmentScore",
                        feature_name="MA Alignment",
                        score=80.0,
                        raw_value=80.0,
                        metadata={},
                    )
                ],
                pattern_results=[
                    PatternResultModel(
                        pattern_id="R001_DoubleBottom",
                        pattern_name="Double Bottom",
                        confidence=90.0,
                        metadata={},
                    )
                ],
                rank=1,
                summary="1位: トヨタ自動車（7203.T）[押し目買い型] 総合スコア 85.0点。",
            )
        ]

    @patch("builtins.print")
    def test_display_cli(self, mock_print):
        presenter = Presenter()
        results = self._sample_results()

        presenter.display_results(results, output_type="cli")

        self.assertTrue(mock_print.called)
        printed_text = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("7203.T", printed_text)
        self.assertIn("トヨタ自動車", printed_text)
        self.assertIn("押し目買い型", printed_text)
        self.assertIn("PER=", printed_text)
        self.assertIn("ATR=", printed_text)

    @patch("builtins.print")
    def test_display_empty(self, mock_print):
        presenter = Presenter()
        presenter.display_results([], output_type="cli")
        mock_print.assert_any_call("表示する分析結果がありません。")

    def test_export_json_structure_and_parse(self):
        """export_json で後段AI連携用のJSONが出力・パースできる"""
        presenter = Presenter()
        results = self._sample_results()

        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = Path(tmpdir) / "reports"
            json_path = presenter.export_json(
                results,
                output_dir=nested_dir,
                metadata={"fiscal_year": 2025},
            )

            self.assertTrue(json_path.exists())
            self.assertEqual(json_path.name, "screening_report_2026-02-15.json")

            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertIn("generated_at", data)
            self.assertEqual(data["as_of_date"], "2026-02-15")
            self.assertEqual(data["summary"]["total_candidates"], 1)
            self.assertEqual(data["summary"]["strategy_counts"]["pullback"], 1)
            self.assertEqual(data["metadata"]["fiscal_year"], 2025)
            self.assertEqual(len(data["candidates"]), 1)
            cand = data["candidates"][0]
            self.assertEqual(cand["symbol"], "7203.T")
            self.assertEqual(cand["strategy_label"], "押し目買い型")
            self.assertEqual(cand["key_levels"]["close"], 3100.0)
            self.assertEqual(cand["financial_summary"]["roe"], 12.5)
            self.assertIn("pullback", data["strategy_rankings"])
            self.assertEqual(len(data["strategy_rankings"]["pullback"]), 1)

    def test_export_markdown_required_sections(self):
        """export_markdown に必須セクションが含まれている"""
        presenter = Presenter()
        results = self._sample_results()

        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = presenter.export_markdown(results, output_dir=tmpdir)
            self.assertTrue(md_path.exists())
            self.assertEqual(md_path.name, "screening_report_2026-02-15.md")

            content = md_path.read_text(encoding="utf-8")
            self.assertIn("## 全体サマリー", content)
            self.assertIn("## 戦略別ランキング", content)
            self.assertIn("### 押し目買い型ランキング", content)
            self.assertIn("### ブレイクアウト型ランキング", content)
            self.assertIn("## 推奨銘柄詳細", content)
            self.assertIn("#### 価格水準・サポート/レジスタンス", content)
            self.assertIn("#### リスク指標", content)
            self.assertIn("#### 主要財務指標", content)
            self.assertIn("#### 判定根拠", content)
            self.assertIn("#### 検出パターン・主要特徴量", content)
            self.assertIn("トヨタ自動車", content)
            self.assertIn("R001_DoubleBottom", content)

    def test_export_empty_results_produces_valid_reports(self):
        """0件の場合でも有効な JSON / Markdown ファイルを出力する"""
        presenter = Presenter()
        target_date = date(2026, 2, 20)

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = presenter.display_results(
                [],
                output_type="all",
                output_dir=tmpdir,
                as_of_date=target_date,
            )
            self.assertIsNotNone(paths)
            self.assertTrue(paths["json"].exists())
            self.assertTrue(paths["markdown"].exists())

            data = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(data["as_of_date"], "2026-02-20")
            self.assertEqual(data["summary"]["total_candidates"], 0)
            self.assertEqual(data["candidates"], [])

            md_text = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("条件に合致する推奨銘柄はありませんでした", md_text)

    def test_fallback_strategy_rankings_reorders_and_assigns_strategy_ranks(self):
        """strategy_rankings 未指定時は各戦略内で再ソート・連番順位付けし元モデルを破壊しない"""
        presenter = Presenter()
        results = [
            AnalysisResultModel(
                symbol="9984.T",
                company_name="ソフトバンクG",
                date=date(2026, 2, 15),
                strategy_type="breakout",
                total_score=90.0,
                sub_scores={"breakout_strategy_score": 90.0, "trend_env_score": 80.0},
                rank=1,
            ),
            AnalysisResultModel(
                symbol="7203.T",
                company_name="トヨタ自動車",
                date=date(2026, 2, 15),
                strategy_type="pullback",
                total_score=82.0,
                sub_scores={"pullback_strategy_score": 78.0, "trend_env_score": 75.0},
                rank=2,
            ),
            AnalysisResultModel(
                symbol="6758.T",
                company_name="ソニーG",
                date=date(2026, 2, 15),
                strategy_type="pullback",
                total_score=81.0,
                sub_scores={"pullback_strategy_score": 86.0, "trend_env_score": 70.0},
                rank=3,
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = presenter.export_reports(
                results,
                output_dir=tmpdir,
                formats=("json", "markdown"),
                strategy_rankings=None,
            )

            data = json.loads(paths["json"].read_text(encoding="utf-8"))
            pb_rankings = data["strategy_rankings"]["pullback"]
            self.assertEqual([item["symbol"] for item in pb_rankings], ["6758.T", "7203.T"])
            self.assertEqual([item["rank"] for item in pb_rankings], [1, 2])
            self.assertEqual(data["strategy_rankings"]["breakout"][0]["rank"], 1)

            md_text = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("| 1 | 6758.T | ソニーG | 86.00 |", md_text)
            self.assertIn("| 2 | 7203.T | トヨタ自動車 | 78.00 |", md_text)

        # 元の AnalysisResultModel の総合順位は変更されていないこと
        self.assertEqual([r.rank for r in results], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
