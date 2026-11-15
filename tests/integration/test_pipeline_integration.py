import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import src.feature_engine
import src.pattern_detector
import src.score_engine
from src.config.screening_config import AtlasScreeningConfig
from src.feature_engine.manager import calculate_features
from src.feature_engine.registry import feature_registry
from src.indicator_calculator.calculator import IndicatorCalculator
from src.main import main, parse_args, run_full_pipeline
from src.model.data_models import (
    FeatureResultModel,
    FeatureSetModel,
    FinancialModel,
    OhlcvModel,
    PatternResultModel,
    PatternSetModel,
    StockMasterModel,
)
from src.pattern_detector.manager import detect_patterns
from src.pattern_detector.registry import pattern_registry
from src.presentation.presenter import Presenter
from src.ranking.generator import RankingGenerator
from src.score_engine.manager import calculate_scores
from src.score_engine.registry import score_registry
from src.screener.screener import Screener


def _build_uptrend_breakout_ohlcv(symbol: str, days: int = 90) -> list[OhlcvModel]:
    """上昇トレンドかつ最終日に直近高値を健全に上抜ける OHLCV データを生成する。"""
    start = date(2025, 10, 1)
    bars: list[OhlcvModel] = []
    for i in range(days):
        dt = start + timedelta(days=i)
        if i < days - 1:
            close = 1000.0 + i * 5.0
            high = close + 8.0
            low = close - 8.0
            open_p = close - 2.0
            volume = 200_000
        else:
            # 最終日に直近20日高値より少し上抜けて出来高も増加
            prev_high = 1000.0 + (i - 1) * 5.0 + 8.0
            close = prev_high + 10.0
            high = close + 5.0
            low = prev_high - 2.0
            open_p = prev_high
            volume = 450_000
        bars.append(
            OhlcvModel(
                symbol=symbol,
                date=dt,
                open=open_p,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
    return bars


def _build_sample_financial(symbol: str) -> FinancialModel:
    return FinancialModel(
        symbol=symbol,
        fiscal_date=date(2025, 3, 31),
        eps=150.0,
        bps=1200.0,
        roe=15.0,
        roa=8.0,
        per=10.0,
        pbr=1.2,
        revenue=50_000_000_000.0,
        operating_profit=5_000_000_000.0,
        net_profit=3_500_000_000.0,
        revenue_growth=12.0,
        net_profit_growth=18.0,
        revenue_growth_3y_avg=10.0,
        net_profit_growth_3y_avg=14.0,
        total_assets=100_000_000_000.0,
        equity_ratio=45.0,
    )


class TestPipelineIntegration(unittest.TestCase):
    def test_registry_coverage(self):
        """
        パッケージインポートのみで主要な特徴量・全3パターン・スコア計算機がレジストリに登録されていることを検証する。
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
            "P001_Hammer",
            "R001_DoubleBottom",
            "R002_DoubleTop",
        ]
        for ep in expected_patterns:
            self.assertIn(ep, pattern_ids, f"Pattern {ep} is not registered.")

        scores = score_registry.list_score_calculators()
        score_ids = [s["score_id"] for s in scores]
        self.assertIn("S001_OverallScore", score_ids, "S001_OverallScore is not registered.")
        self.assertIn("S002_StrategyScore", score_ids, "S002_StrategyScore is not registered.")

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
                    FeatureResultModel(feature_id="T001_TrendStrengthScore", feature_name="Trend Strength", score=70.0, raw_value=70.0, metadata={}),
                ],
            )
        ]

        pattern_sets = [
            PatternSetModel(
                symbol="7203.T",
                date=datetime(2026, 1, 1),
                results=[
                    PatternResultModel(pattern_id="R001_DoubleBottom", pattern_name="Double Bottom", detected=True, confidence=90.0, details={})
                ],
            )
        ]

        results = calculator.calculate(feature_sets, pattern_sets)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.symbol, "7203.T")
        self.assertGreater(res.total_score, 0.0)
        self.assertIn("FeatureAverageScore", res.sub_scores)
        self.assertIn("PatternAverageConfidence", res.sub_scores)

    def test_e2e_strategy_scoring_to_report_export(self):
        """
        指標計算 -> 特徴量 -> パターン -> S002_StrategyScore -> Screener -> RankingGenerator -> Presenter
        の E2E 結合フローを一時ディレクトリへの JSON / Markdown 出力まで通して検証する。
        """
        config = AtlasScreeningConfig()
        symbol = "7203.T"
        ohlcv_data = _build_uptrend_breakout_ohlcv(symbol, days=90)
        fin_data = _build_sample_financial(symbol)
        master = StockMasterModel(
            code="7203",
            symbol=symbol,
            name="トヨタ自動車",
            market="プライム",
            sector_33="輸送用機器",
        )

        calculator = IndicatorCalculator()
        indicator_sets = calculator.calculate_indicators(ohlcv_data)
        feature_sets = calculate_features(ohlcv_data, indicator_sets, fin_data)
        pattern_sets = detect_patterns(ohlcv_data, indicator_sets)
        score_results = calculate_scores(
            feature_sets,
            pattern_sets,
            score_ids=["S002_StrategyScore"],
            ohlcv_data=ohlcv_data,
            indicator_sets=indicator_sets,
            score_configs={"S002_StrategyScore": config.strategy_score},
        )

        screener = Screener()
        filtered = screener.apply_screener(score_results, criteria=config.screener)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].symbol, symbol)
        self.assertIn(filtered[0].strategy_type, ("pullback", "breakout"))

        ranking_gen = RankingGenerator()
        strategy_rankings = ranking_gen.generate_strategy_rankings(
            filtered,
            master_map=[master],
            feature_sets=feature_sets,
            pattern_sets=pattern_sets,
            financial_map={symbol: fin_data},
            overall_top_n=config.ranking.top_n,
            strategy_top_n=config.ranking.strategy_top_n,
        )
        overall = strategy_rankings["overall"]
        self.assertEqual(len(overall), 1)
        self.assertEqual(overall[0].company_name, "トヨタ自動車")
        self.assertEqual(overall[0].market, "プライム")
        self.assertEqual(overall[0].financial_summary["roe"], 15.0)
        self.assertIsNotNone(overall[0].key_levels.get("close"))

        presenter = Presenter()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = presenter.export_reports(
                overall,
                output_dir=tmpdir,
                formats=("json", "markdown"),
                strategy_rankings=strategy_rankings,
                metadata={"mode": "integration_test"},
            )
            self.assertTrue(paths["json"].exists())
            self.assertTrue(paths["markdown"].exists())

            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["total_candidates"], 1)
            self.assertEqual(payload["candidates"][0]["symbol"], symbol)
            self.assertEqual(payload["candidates"][0]["company_name"], "トヨタ自動車")

            md_content = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("トヨタ自動車", md_content)
            self.assertIn("## 推奨銘柄詳細", md_content)

    def test_run_full_pipeline_with_mocked_data_explicit_and_prescreened(self):
        """
        main.run_full_pipeline をモックデータで実行し、
        明示シンボル実行と事前スクリーニング自動抽出実行の両方でレポートが生成されることを確認する。
        """
        ohlcv_7203 = _build_uptrend_breakout_ohlcv("7203.T", days=90)
        fin_7203 = _build_sample_financial("7203.T")
        master_7203 = StockMasterModel(
            code="7203",
            symbol="7203.T",
            name="トヨタ自動車",
            market="プライム",
            sector_33="輸送用機器",
        )
        # 事前スクリーニングで除外されるべき銘柄（グロース市場・赤字）
        master_9999 = StockMasterModel(
            code="9999",
            symbol="9999.T",
            name="除外テスト株式会社",
            market="グロース",
            sector_33="情報・通信業",
        )
        fin_9999 = FinancialModel(
            symbol="9999.T",
            fiscal_date=date(2025, 3, 31),
            revenue=1_000_000_000.0,
            operating_profit=-100_000_000.0,
            net_profit=-200_000_000.0,
            roe=-5.0,
            equity_ratio=10.0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "out_explicit"
            with patch("src.main.MasterManager") as mock_master_cls, \
                 patch("src.main.collect_ohlcv_data", return_value=ohlcv_7203), \
                 patch("src.main.collect_financial_data", return_value=fin_7203):
                mock_master_cls.return_value.load_master.return_value = [master_7203]

                result = run_full_pipeline(
                    symbols=["7203.T"],
                    start_date=date(2025, 10, 1),
                    end_date=date(2025, 12, 31),
                    fiscal_year=2025,
                    as_of_date=date(2025, 12, 31),
                    output_dir=out_dir,
                    export_reports=True,
                )

            self.assertEqual(result["processed_symbols"], ["7203.T"])
            self.assertEqual(len(result["analysis_results"]), 1)
            self.assertEqual(result["analysis_results"][0].company_name, "トヨタ自動車")
            self.assertTrue(result["report_paths"]["json"].exists())
            self.assertTrue(result["report_paths"]["markdown"].exists())

            # symbols=None の事前スクリーニング＋流動性フィルタ経由ルート
            out_dir_auto = Path(tmpdir) / "out_auto"
            with patch("src.main.MasterManager") as mock_master_cls, \
                 patch("src.main.data_collector") as mock_dc, \
                 patch("src.main.collect_ohlcv_data", return_value=ohlcv_7203), \
                 patch("src.main.collect_financial_data", return_value=fin_7203):
                mock_master_cls.return_value.load_master.return_value = [master_7203, master_9999]
                mock_dc.load_financial_snapshot.return_value = {
                    "7203": fin_7203,
                    "9999": fin_9999,
                }

                auto_result = run_full_pipeline(
                    symbols=None,
                    start_date=date(2025, 10, 1),
                    end_date=date(2025, 12, 31),
                    fiscal_year=2025,
                    as_of_date=date(2025, 12, 31),
                    output_dir=out_dir_auto,
                    export_reports=True,
                )

            self.assertEqual(auto_result["processed_symbols"], ["7203.T"])
            self.assertEqual(len(auto_result["analysis_results"]), 1)
            self.assertTrue(auto_result["report_paths"]["json"].exists())
            self.assertTrue(auto_result["report_paths"]["markdown"].exists())
            self.assertIsNone(auto_result["evaluation_summary"])

    def test_run_full_pipeline_evaluate_mode_and_cli(self):
        """
        run_full_pipeline(mode='evaluate', as_of_date=...) と CLI main() の結合テスト。
        as_of_date 用のキャッシュ分離およびフォワードリターン検証レポート生成を確認する。
        """
        ohlcv_screen = _build_uptrend_breakout_ohlcv("7203.T", days=92)
        signal_bar = ohlcv_screen[-1]  # 2025-12-31
        as_of = signal_bar.date

        # シグナル翌日以降のフォワードOHLCV（20日分）
        forward_bars = [signal_bar]
        for i in range(1, 21):
            close = signal_bar.close * (1.0 + 0.005 * i)
            forward_bars.append(
                OhlcvModel(
                    symbol="7203.T",
                    date=as_of + timedelta(days=i),
                    open=close - 5.0,
                    high=close + 10.0,
                    low=close - 10.0,
                    close=close,
                    volume=300_000,
                )
            )

        fin_7203 = _build_sample_financial("7203.T")
        master_7203 = StockMasterModel(
            code="7203",
            symbol="7203.T",
            name="トヨタ自動車",
            market="プライム",
            sector_33="輸送用機器",
        )

        # 不正引数の検証
        with self.assertRaises(ValueError):
            run_full_pipeline(symbols=["7203.T"], mode="invalid_mode")
        with self.assertRaises(ValueError):
            run_full_pipeline(symbols=["7203.T"], mode="evaluate", as_of_date=None)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "eval_out"
            with patch("src.main.MasterManager") as mock_master_cls, \
                 patch("src.main.collect_ohlcv_data", return_value=ohlcv_screen), \
                 patch("src.main.collect_financial_data", return_value=fin_7203), \
                 patch("src.evaluator.evaluator.data_collector.collect_ohlcv_data", return_value=forward_bars), \
                 patch("src.main.IndicatorCalculator.calculate_indicators", wraps=IndicatorCalculator().calculate_indicators) as spy_ind, \
                 patch("src.main.calculate_features", wraps=calculate_features) as spy_feat:
                mock_master_cls.return_value.load_master.return_value = [master_7203]

                result = run_full_pipeline(
                    symbols=["7203.T"],
                    start_date=date(2025, 10, 1),
                    end_date=as_of,
                    fiscal_year=2025,
                    as_of_date=as_of,
                    output_dir=out_dir,
                    export_reports=True,
                    mode="evaluate",
                    horizons=[20, 5, 20],
                    use_cache=False,
                )

            # cache_key_suffix と use_cache=False が引き継がれていること
            self.assertEqual(spy_ind.call_args.kwargs["use_cache"], False)
            self.assertEqual(spy_ind.call_args.kwargs["cache_key_suffix"], f"asof_{as_of.isoformat()}")
            self.assertEqual(spy_feat.call_args.kwargs["use_cache"], False)
            self.assertEqual(spy_feat.call_args.kwargs["cache_key_suffix"], f"asof_{as_of.isoformat()}")

            eval_summary = result["evaluation_summary"]
            self.assertIsNotNone(eval_summary)
            self.assertEqual(eval_summary.horizons, [5, 20])
            self.assertEqual(eval_summary.total_candidates, 1)
            self.assertEqual(eval_summary.overall_summary[5].evaluated_count, 1)
            self.assertEqual(eval_summary.overall_summary[20].evaluated_count, 1)
            self.assertAlmostEqual(eval_summary.items[0].horizons[5].return_pct, 2.5, places=4)
            self.assertAlmostEqual(eval_summary.items[0].horizons[20].return_pct, 10.0, places=4)

            json_path = result["report_paths"]["json"]
            md_path = result["report_paths"]["markdown"]
            self.assertEqual(json_path.name, f"evaluation_report_{as_of.isoformat()}.json")
            self.assertEqual(md_path.name, f"evaluation_report_{as_of.isoformat()}.md")

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertIn("evaluation", payload)
            self.assertEqual(payload["metadata"]["mode"], "evaluate")
            md_text = md_path.read_text(encoding="utf-8")
            self.assertIn("## フォワードリターン検証サマリー（全体 / 戦略別）", md_text)

            # CLI parse_args と main() の結合確認
            parsed = parse_args([
                "--mode", "evaluate",
                "--as-of-date", as_of.isoformat(),
                "--symbols", "7203.T",
                "--horizons", "5", "20",
                "--no-cache",
                "--no-export",
            ])
            self.assertEqual(parsed.mode, "evaluate")
            self.assertEqual(parsed.as_of_date, as_of)
            self.assertEqual(parsed.horizons, [5, 20])
            self.assertTrue(parsed.no_cache)
            self.assertTrue(parsed.no_export)

            with patch("src.main.MasterManager") as mock_master_cls, \
                 patch("src.main.collect_ohlcv_data", return_value=ohlcv_screen), \
                 patch("src.main.collect_financial_data", return_value=fin_7203), \
                 patch("src.evaluator.evaluator.data_collector.collect_ohlcv_data", return_value=forward_bars):
                mock_master_cls.return_value.load_master.return_value = [master_7203]
                exit_code = main([
                    "--mode", "evaluate",
                    "--as-of-date", as_of.isoformat(),
                    "--symbols", "7203.T",
                    "--horizons", "5",
                    "--output-dir", str(Path(tmpdir) / "cli_out"),
                    "--no-cache",
                ])
            self.assertEqual(exit_code, 0)
            self.assertTrue(
                (Path(tmpdir) / "cli_out" / f"evaluation_report_{as_of.isoformat()}.json").exists()
            )

            # evaluate モードで --as-of-date 未指定時は終了コード 1
            err_code = main(["--mode", "evaluate", "--symbols", "7203.T"])
            self.assertEqual(err_code, 1)


if __name__ == "__main__":
    unittest.main()
