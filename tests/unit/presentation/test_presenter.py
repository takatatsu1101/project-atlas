import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.model.data_models import (
    AnalysisResultModel,
    BatchBacktestSummaryModel,
    EvaluationSummaryModel,
    FeatureQuantileRowModel,
    FeatureResultModel,
    ForwardEvaluationItemModel,
    HorizonMetricsModel,
    HorizonSummaryModel,
    PatternResultModel,
)
from src.presentation.presenter import Presenter, display_results


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

    @staticmethod
    def _sample_evaluation_summary() -> EvaluationSummaryModel:
        return EvaluationSummaryModel(
            as_of_date=date(2026, 2, 15),
            horizons=[5, 20],
            entry_price_mode="signal_close",
            total_candidates=1,
            overall_summary={
                5: HorizonSummaryModel(
                    horizon_days=5,
                    total_candidates=1,
                    evaluated_count=1,
                    win_count=1,
                    win_rate_pct=100.0,
                    avg_return_pct=4.5,
                    median_return_pct=4.5,
                    avg_mfe_pct=6.2,
                    avg_mae_pct=-1.1,
                    best_symbol="7203.T",
                    best_return_pct=4.5,
                    worst_symbol="7203.T",
                    worst_return_pct=4.5,
                ),
                20: HorizonSummaryModel(
                    horizon_days=20,
                    total_candidates=1,
                    evaluated_count=0,
                    win_count=0,
                ),
            },
            strategy_summary={
                "pullback": {
                    5: HorizonSummaryModel(
                        horizon_days=5,
                        total_candidates=1,
                        evaluated_count=1,
                        win_count=1,
                        win_rate_pct=100.0,
                        avg_return_pct=4.5,
                        median_return_pct=4.5,
                        avg_mfe_pct=6.2,
                        avg_mae_pct=-1.1,
                        best_symbol="7203.T",
                        best_return_pct=4.5,
                        worst_symbol="7203.T",
                        worst_return_pct=4.5,
                    ),
                    20: HorizonSummaryModel(
                        horizon_days=20,
                        total_candidates=1,
                        evaluated_count=0,
                        win_count=0,
                    ),
                }
            },
            items=[
                ForwardEvaluationItemModel(
                    symbol="7203.T",
                    company_name="トヨタ自動車",
                    market="プライム",
                    sector="輸送用機器",
                    strategy_type="pullback",
                    rank=1,
                    total_score=85.0,
                    signal_date=date(2026, 2, 15),
                    entry_price=3100.0,
                    horizons={
                        5: HorizonMetricsModel(
                            horizon_days=5,
                            available=True,
                            target_date=date(2026, 2, 20),
                            exit_close=3239.5,
                            return_pct=4.5,
                            mfe_pct=6.2,
                            mae_pct=-1.1,
                            is_win=True,
                        ),
                        20: HorizonMetricsModel(horizon_days=20, available=False),
                    },
                    status="evaluated",
                )
            ],
        )

    @patch("builtins.print")
    def test_display_cli_with_evaluation_summary_even_when_results_empty(self, mock_print):
        """evaluation_summary 指定時は結果あり・空のどちらでもCLIに検証サマリーを出力する"""
        presenter = Presenter()
        eval_summary = self._sample_evaluation_summary()

        # 分析結果空でもフォワードリターン検証サマリーは表示される
        presenter.display_results([], output_type="cli", evaluation_summary=eval_summary)
        printed_text = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("表示する分析結果がありません。", printed_text)
        self.assertIn("フォワードリターン検証サマリー", printed_text)
        self.assertIn("+5営業日", printed_text)
        self.assertIn("100.00%", printed_text)
        self.assertIn("+4.50%", printed_text)
        self.assertIn("7203.T", printed_text)

    def test_export_reports_with_evaluation_summary_and_prefix(self):
        """evaluation_summary 付きで evaluation_report プレフィックスの JSON / Markdown が出力される"""
        presenter = Presenter()
        results = self._sample_results()
        eval_summary = self._sample_evaluation_summary()

        with tempfile.TemporaryDirectory() as tmpdir:
            # evaluation_summary=None のときは evaluation キーを含まない
            plain_json = presenter.export_json(results, output_dir=tmpdir)
            self.assertEqual(plain_json.name, "screening_report_2026-02-15.json")
            plain_payload = json.loads(plain_json.read_text(encoding="utf-8"))
            self.assertNotIn("evaluation", plain_payload)

            # evaluation_summary 指定時は evaluation_report_* になり evaluation キーが含まれる
            paths = display_results(
                results,
                output_type="all",
                output_dir=tmpdir,
                evaluation_summary=eval_summary,
            )
            self.assertEqual(paths["json"].name, "evaluation_report_2026-02-15.json")
            self.assertEqual(paths["markdown"].name, "evaluation_report_2026-02-15.md")

            eval_payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertIn("evaluation", eval_payload)
            self.assertEqual(eval_payload["evaluation"]["total_candidates"], 1)
            self.assertEqual(eval_payload["evaluation"]["overall_summary"]["5"]["win_count"], 1)

            md_text = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("## フォワードリターン検証サマリー（全体 / 戦略別）", md_text)
            self.assertIn("## 銘柄別フォワードリターン詳細", md_text)
            self.assertIn("+4.50%", md_text)

            # report_prefix 明示指定でファイル名プレフィックスを上書きできる
            custom_paths = presenter.export_reports(
                results,
                output_dir=tmpdir,
                formats=("json", "markdown"),
                evaluation_summary=eval_summary,
                report_prefix="custom_eval",
            )
            self.assertEqual(custom_paths["json"].name, "custom_eval_2026-02-15.json")
            self.assertEqual(custom_paths["markdown"].name, "custom_eval_2026-02-15.md")

    def _sample_batch_summary(self) -> BatchBacktestSummaryModel:
        es1 = self._sample_evaluation_summary()
        d2 = date(2026, 3, 15)
        es2 = EvaluationSummaryModel(
            as_of_date=d2,
            horizons=[5, 20],
            entry_price_mode="signal_close",
            total_candidates=1,
            overall_summary={
                5: HorizonSummaryModel(
                    horizon_days=5,
                    total_candidates=1,
                    evaluated_count=1,
                    win_count=0,
                    win_rate_pct=0.0,
                    avg_return_pct=-2.0,
                    median_return_pct=-2.0,
                    avg_mfe_pct=1.0,
                    avg_mae_pct=-3.0,
                    best_symbol="6758.T",
                    best_return_pct=-2.0,
                    worst_symbol="6758.T",
                    worst_return_pct=-2.0,
                ),
                20: HorizonSummaryModel(horizon_days=20, total_candidates=1, evaluated_count=0, win_count=0),
            },
            strategy_summary={},
            items=[],
        )
        return BatchBacktestSummaryModel(
            as_of_dates=[date(2026, 2, 15), d2],
            horizons=[5, 20],
            entry_price_mode="signal_close",
            total_dates=2,
            total_candidates=2,
            aggregated_overall_summary={
                5: HorizonSummaryModel(
                    horizon_days=5,
                    total_candidates=2,
                    evaluated_count=2,
                    win_count=1,
                    win_rate_pct=50.0,
                    avg_return_pct=1.25,
                    median_return_pct=1.25,
                    avg_mfe_pct=3.6,
                    avg_mae_pct=-2.05,
                    best_symbol="7203.T",
                    best_return_pct=4.5,
                    worst_symbol="6758.T",
                    worst_return_pct=-2.0,
                ),
                20: HorizonSummaryModel(horizon_days=20, total_candidates=2, evaluated_count=0, win_count=0),
            },
            aggregated_strategy_summary={
                "pullback": {
                    5: HorizonSummaryModel(
                        horizon_days=5,
                        total_candidates=2,
                        evaluated_count=2,
                        win_count=1,
                        win_rate_pct=50.0,
                        avg_return_pct=1.25,
                        median_return_pct=1.25,
                    ),
                    20: HorizonSummaryModel(horizon_days=20, total_candidates=2, evaluated_count=0, win_count=0),
                }
            },
            per_date_summaries={date(2026, 2, 15): es1, d2: es2},
        )

    @patch("builtins.print")
    def test_display_and_export_batch_backtest_reports(self, mock_print):
        """display_batch_backtest_results と export_batch_backtest_reports が CLI / JSON / Markdown を正しく出力する"""
        presenter = Presenter()
        batch_summary = self._sample_batch_summary()

        presenter.display_batch_backtest_results(batch_summary)
        printed_text = "\n".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        self.assertIn("一括バックテスト横断検証サマリー", printed_text)
        self.assertIn("2026-02-15", printed_text)
        self.assertIn("2026-03-15", printed_text)
        self.assertIn("+1.25%", printed_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = presenter.export_batch_backtest_reports(
                batch_summary,
                output_dir=tmpdir,
                formats=("json", "markdown"),
                metadata={"mode": "backtest", "workers_used": 2},
            )
            self.assertEqual(paths["json"].name, "batch_backtest_report_2026-02-15_2026-03-15.json")
            self.assertEqual(paths["markdown"].name, "batch_backtest_report_2026-02-15_2026-03-15.md")

            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["total_dates"], 2)
            self.assertEqual(payload["total_candidates"], 2)
            self.assertEqual(payload["metadata"]["workers_used"], 2)
            self.assertEqual(payload["aggregated_overall_summary"]["5"]["win_count"], 1)
            self.assertIn("2026-02-15", payload["per_date_summaries"])
            self.assertIn("2026-03-15", payload["per_date_summaries"])

            md_text = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("# Project Atlas 一括バックテスト横断検証レポート (2026-02-15 〜 2026-03-15)", md_text)
            self.assertIn("## 全期間横断検証サマリー（全体 / 戦略別）", md_text)
            self.assertIn("## 基準日別サマリー", md_text)
            self.assertIn("+1.25%", md_text)

    @patch("builtins.print")
    def test_evaluation_cli_json_markdown_with_passed_and_feature_quantile_summary(self, mock_print):
        """全通過銘柄サマリーおよび特徴量別分位評価が CLI / JSON / Markdown に出力される"""
        presenter = Presenter()
        eval_summary = self._sample_evaluation_summary()
        eval_summary.passed_total_candidates = 10
        eval_summary.passed_overall_summary = {
            5: HorizonSummaryModel(
                horizon_days=5,
                total_candidates=10,
                evaluated_count=10,
                win_count=7,
                win_rate_pct=70.0,
                avg_return_pct=2.3,
                median_return_pct=2.0,
                avg_mfe_pct=4.5,
                avg_mae_pct=-1.2,
                best_symbol="7203.T",
                best_return_pct=6.0,
                worst_symbol="9984.T",
                worst_return_pct=-2.0,
            ),
            20: HorizonSummaryModel(
                horizon_days=20,
                total_candidates=10,
                evaluated_count=0,
                win_count=0,
            ),
        }
        eval_summary.feature_quantile_summary = {
            "F001_Trend": {
                5: FeatureQuantileRowModel(
                    feature_id="F001_Trend",
                    feature_name="トレンド強度",
                    horizon_days=5,
                    total_samples=10,
                    unique_score_count=8,
                    top_count=2,
                    top_win_rate_pct=100.0,
                    top_avg_return_pct=5.5,
                    top_avg_mfe_pct=7.0,
                    top_avg_mae_pct=-0.5,
                    bottom_count=2,
                    bottom_win_rate_pct=0.0,
                    bottom_avg_return_pct=-1.5,
                    bottom_avg_mfe_pct=1.0,
                    bottom_avg_mae_pct=-3.0,
                    spread_return_pct=7.0,
                    spread_win_rate_pct=100.0,
                ),
                20: FeatureQuantileRowModel(
                    feature_id="F001_Trend",
                    feature_name="トレンド強度",
                    horizon_days=20,
                    total_samples=3,
                    unique_score_count=3,
                ),
            }
        }

        presenter.display_results([], output_type="cli", evaluation_summary=eval_summary)
        printed_text = "\n".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        self.assertIn("[全通過銘柄サマリー (全 10 件)]", printed_text)
        self.assertIn("[特徴量別分位評価 (上位20% vs 下位20%)]", printed_text)
        self.assertIn("F001_Trend (トレンド強度)", printed_text)
        self.assertIn("n=10 (unique=8)", printed_text)
        self.assertIn("サンプル不足(<5)", printed_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = presenter.export_reports(
                [],
                output_dir=tmpdir,
                formats=("json", "markdown"),
                as_of_date=date(2026, 2, 15),
                evaluation_summary=eval_summary,
            )
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["evaluation"]["passed_total_candidates"], 10)
            self.assertIn("5", payload["evaluation"]["passed_overall_summary"])
            self.assertIn("F001_Trend", payload["evaluation"]["feature_quantile_summary"])

            md_text = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("## 全通過銘柄フォワードリターンサマリー（全 10 件）", md_text)
            self.assertIn("## 特徴量別分位評価（上位20% vs 下位20%）", md_text)
            self.assertIn("| F001_Trend | トレンド強度 | +5営業日 | 10 (8) |", md_text)
            self.assertIn("+7.00%", md_text)

    @patch("builtins.print")
    def test_batch_backtest_cli_json_markdown_with_passed_pool_and_feature_quantiles(self, mock_print):
        """一括バックテストで全期間プールの全通過銘柄サマリーと特徴量別分位評価が CLI / JSON / Markdown に出力される"""
        presenter = Presenter()
        batch_summary = BatchBacktestSummaryModel(
            as_of_dates=[date(2026, 2, 15)],
            horizons=[5],
            entry_price_mode="signal_close",
            total_dates=1,
            total_candidates=1,
            aggregated_overall_summary={
                5: HorizonSummaryModel(
                    horizon_days=5,
                    total_candidates=1,
                    evaluated_count=1,
                    win_count=1,
                    win_rate_pct=100.0,
                    avg_return_pct=4.5,
                    median_return_pct=4.5,
                )
            },
            passed_total_candidates=5,
            aggregated_passed_overall_summary={
                5: HorizonSummaryModel(
                    horizon_days=5,
                    total_candidates=5,
                    evaluated_count=5,
                    win_count=3,
                    win_rate_pct=60.0,
                    avg_return_pct=1.8,
                    median_return_pct=1.5,
                )
            },
            aggregated_feature_quantile_summary={
                "F002_Vol": {
                    5: FeatureQuantileRowModel(
                        feature_id="F002_Vol",
                        feature_name="出来高モメンタム",
                        horizon_days=5,
                        total_samples=5,
                        unique_score_count=5,
                        top_count=1,
                        top_win_rate_pct=100.0,
                        top_avg_return_pct=6.0,
                        top_avg_mfe_pct=8.0,
                        top_avg_mae_pct=-0.5,
                        bottom_count=1,
                        bottom_win_rate_pct=0.0,
                        bottom_avg_return_pct=-2.0,
                        bottom_avg_mfe_pct=0.5,
                        bottom_avg_mae_pct=-3.0,
                        spread_return_pct=8.0,
                        spread_win_rate_pct=100.0,
                    )
                }
            },
        )

        presenter.display_batch_backtest_results(batch_summary)
        printed_text = "\n".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        self.assertIn("[全期間プール 全通過銘柄サマリー (全 5 件)]", printed_text)
        self.assertIn("F002_Vol (出来高モメンタム)", printed_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = presenter.export_batch_backtest_reports(
                batch_summary,
                output_dir=tmpdir,
                formats=("json", "markdown"),
            )
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["passed_total_candidates"], 5)
            self.assertIn("5", payload["aggregated_passed_overall_summary"])
            self.assertIn("F002_Vol", payload["aggregated_feature_quantile_summary"])

            md_text = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("## 全期間プール 全通過銘柄サマリー（全 5 件）", md_text)
            self.assertIn("## 全期間プール 特徴量別分位評価（上位20% vs 下位20%）", md_text)
            self.assertIn("| F002_Vol | 出来高モメンタム | +5営業日 | 5 (5) |", md_text)

    @patch("builtins.print")
    def test_market_regime_summary_cli_and_markdown_output(self, mock_print):
        """market_regime_summary が存在する場合、CLI および Markdown に地合いレジーム・Breadth・BO閾値補正が出力される"""
        presenter = Presenter()
        d1 = date(2026, 3, 2)
        eval_d1 = EvaluationSummaryModel(
            as_of_date=d1,
            horizons=[5],
            total_candidates=1,
            overall_summary={5: HorizonSummaryModel(horizon_days=5, total_candidates=1, evaluated_count=1, win_count=1, win_rate_pct=100.0, avg_return_pct=2.0)},
            market_regime_summary={
                "as_of_date": d1.isoformat(),
                "is_active": True,
                "regime": "bearish",
                "universe_size": 100,
                "breadth_ratio": 0.312,
                "breakout_threshold_delta": 8.0,
            },
        )
        batch_summary = BatchBacktestSummaryModel(
            as_of_dates=[d1],
            horizons=[5],
            total_dates=1,
            total_candidates=1,
            aggregated_overall_summary=eval_d1.overall_summary,
            per_date_summaries={d1: eval_d1},
        )

        presenter.display_batch_backtest_results(batch_summary)
        printed_text = "\n".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        self.assertIn("地合い=bearish (Breadth=31.2%, BO閾値+8)", printed_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = presenter.export_batch_backtest_reports(
                batch_summary, output_dir=tmpdir, formats=("markdown",)
            )
            md_text = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("| 基準日 | 候補数 | 地合い (Breadth) |", md_text)
            self.assertIn("bearish (Breadth=31.2%, BO閾値+8)", md_text)

    def test_export_reports_gemini_multiple_deliveries_and_strict_error(self):
        """export_reports で gemini_brief_deliveries の複数併用と fail_on_brief_delivery_error を検証する"""
        presenter = Presenter()
        results = self._sample_results()
        target_date = date(2026, 2, 15)

        class _DummyDriveDelivery:
            key_suffix = "drive"

            def __init__(self, should_fail: bool = False):
                self.should_fail = should_fail

            def deliver(self, files, as_of_date):
                if self.should_fail:
                    raise RuntimeError("drive upload failed")
                return {k: f"gdrive://id_{k}" for k in files}

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "out_ok"
            copy_dir = Path(tmpdir) / "copy_ok"
            copy_dir.mkdir(parents=True, exist_ok=True)

            exported = presenter.export_reports(
                results,
                output_dir=out_dir,
                formats=("gemini",),
                as_of_date=target_date,
                gemini_brief_copy_dir=copy_dir,
                gemini_brief_deliveries=[_DummyDriveDelivery(should_fail=False)],
                fail_on_brief_delivery_error=True,
            )
            self.assertTrue(exported["gemini"].exists())
            self.assertTrue(exported["gemini_latest"].exists())
            self.assertEqual(exported["gemini_drive"], "gdrive://id_gemini")
            self.assertEqual(exported["gemini_latest_drive"], "gdrive://id_gemini_latest")
            self.assertTrue(Path(exported["gemini_copy"]).exists())
            self.assertTrue(Path(exported["gemini_latest_copy"]).exists())

            out_fail_dir = Path(tmpdir) / "out_fail"
            with self.assertRaises(RuntimeError):
                presenter.export_reports(
                    results,
                    output_dir=out_fail_dir,
                    formats=("gemini", "json", "markdown"),
                    as_of_date=target_date,
                    gemini_brief_deliveries=[_DummyDriveDelivery(should_fail=True)],
                    fail_on_brief_delivery_error=True,
                )
            # strict 失敗時でもローカルファイル（gemini + 後続 json / markdown）は生成・保護されていること
            self.assertTrue((out_fail_dir / "gemini_brief_2026-02-15.md").exists())
            self.assertTrue((out_fail_dir / "gemini_brief_latest.md").exists())
            self.assertTrue((out_fail_dir / "screening_report_2026-02-15.json").exists())
            self.assertTrue((out_fail_dir / "screening_report_2026-02-15.md").exists())


if __name__ == "__main__":
    unittest.main()
