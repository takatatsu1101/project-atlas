import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
import io
from contextlib import redirect_stdout
from pathlib import Path
import time
from unittest.mock import patch

import pandas as pd

import src.feature_engine
import src.pattern_detector
import src.score_engine
from src.common.storage import StorageManager
from src.config.screening_config import AtlasScreeningConfig
from src.data_collector.collector import DataCollector
from src.evaluator.evaluator import ForwardReturnEvaluator
from src.feature_engine.manager import calculate_features
from src.feature_engine.registry import feature_registry
from src.indicator_calculator.calculator import IndicatorCalculator
from src.main import (
    DEFAULT_PARALLEL_MIN_SYMBOLS,
    _resolve_worker_count,
    main,
    parse_args,
    run_batch_backtest,
    run_full_pipeline,
)
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
                 patch("src.main.prefetch_ohlcv_batch"), \
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
                 patch("src.main.prefetch_ohlcv_batch"), \
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
                 patch("src.main.prefetch_ohlcv_batch"), \
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
                "--update-master",
                "--no-irbank-download",
            ])
            self.assertEqual(parsed.mode, "evaluate")
            self.assertEqual(parsed.as_of_date, as_of)
            self.assertEqual(parsed.horizons, [5, 20])
            self.assertTrue(parsed.no_cache)
            self.assertTrue(parsed.no_export)
            self.assertTrue(parsed.update_master)
            self.assertTrue(parsed.no_irbank_download)

            full_cli_ohlcv = ohlcv_screen + forward_bars[1:]
            with patch("src.main.MasterManager") as mock_master_cls, \
                 patch("src.main.prefetch_ohlcv_batch"), \
                 patch("src.main.collect_ohlcv_data", return_value=full_cli_ohlcv), \
                 patch("src.main.collect_financial_data", return_value=fin_7203) as mock_fin_fn, \
                 patch("src.evaluator.evaluator.data_collector.collect_ohlcv_data") as mock_eval_ohlcv:
                mock_master_cls.return_value.load_master.return_value = [master_7203]
                mock_master_cls.return_value.update_from_jpx.return_value = [master_7203]
                exit_code = main([
                    "--mode", "evaluate",
                    "--as-of-date", as_of.isoformat(),
                    "--symbols", "7203.T",
                    "--horizons", "5",
                    "--output-dir", str(Path(tmpdir) / "cli_out"),
                    "--no-cache",
                    "--update-master",
                    "--no-irbank-download",
                ])
                mock_master_cls.return_value.update_from_jpx.assert_called_once()
                mock_fin_fn.assert_called_once()
                self.assertEqual(mock_fin_fn.call_args.kwargs.get("allow_download"), False)
                mock_eval_ohlcv.assert_not_called()
            self.assertEqual(exit_code, 0)
            cli_json_path = Path(tmpdir) / "cli_out" / f"evaluation_report_{as_of.isoformat()}.json"
            self.assertTrue(cli_json_path.exists())
            cli_payload = json.loads(cli_json_path.read_text(encoding="utf-8"))
            self.assertEqual(
                cli_payload["evaluation"]["overall_summary"]["5"]["evaluated_count"],
                1,
            )

            # evaluate モードで --as-of-date 未指定時は終了コード 1
            err_code = main(["--mode", "evaluate", "--symbols", "7203.T"])
            self.assertEqual(err_code, 1)

    def test_feature_cache_disabled_by_default_and_enabled_by_cli_flag(self):
        """use_feature_cache はデフォルト False で、--use-feature-cache 指定時のみ True が渡る"""
        ohlcv_7203 = _build_uptrend_breakout_ohlcv("7203.T", days=90)
        fin_7203 = _build_sample_financial("7203.T")
        master_7203 = StockMasterModel(
            code="7203",
            symbol="7203.T",
            name="トヨタ自動車",
            market="プライム",
            sector_33="輸送用機器",
        )
        # ./data/cache を汚さないよう事前計算結果を返すモックで引数を検証する
        sample_ind = IndicatorCalculator().calculate_indicators(ohlcv_7203, use_cache=False)
        sample_feat = calculate_features(ohlcv_7203, sample_ind, fin_7203, use_cache=False)

        # CLI パースの確認
        parsed_default = parse_args(["--symbols", "7203.T"])
        self.assertFalse(parsed_default.use_feature_cache)
        parsed_enabled = parse_args(["--symbols", "7203.T", "--use-feature-cache"])
        self.assertTrue(parsed_enabled.use_feature_cache)

        with patch("src.main.MasterManager") as mock_master_cls, \
             patch("src.main.prefetch_ohlcv_batch"), \
             patch("src.main.collect_ohlcv_data", return_value=ohlcv_7203), \
             patch("src.main.collect_financial_data", return_value=fin_7203), \
             patch("src.main.IndicatorCalculator.calculate_indicators", return_value=sample_ind) as mock_ind, \
             patch("src.main.calculate_features", return_value=sample_feat) as mock_feat:
            mock_master_cls.return_value.load_master.return_value = [master_7203]

            # 1. デフォルト: 指標キャッシュは True、特徴量キャッシュは False
            exit_default = main(["--symbols", "7203.T", "--no-export"])
            self.assertEqual(exit_default, 0)
            self.assertIs(mock_ind.call_args.kwargs["use_cache"], True)
            self.assertIs(mock_feat.call_args.kwargs["use_cache"], False)

            mock_ind.reset_mock()
            mock_feat.reset_mock()

            # 2. --use-feature-cache 指定時のみ特徴量キャッシュも True
            exit_enabled = main(["--symbols", "7203.T", "--no-export", "--use-feature-cache"])
            self.assertEqual(exit_enabled, 0)
            self.assertIs(mock_ind.call_args.kwargs["use_cache"], True)
            self.assertIs(mock_feat.call_args.kwargs["use_cache"], True)

            mock_ind.reset_mock()
            mock_feat.reset_mock()

            # 3. --no-cache と --use-feature-cache 併用時は両方 False
            exit_nocache = main(
                ["--symbols", "7203.T", "--no-export", "--no-cache", "--use-feature-cache"]
            )
            self.assertEqual(exit_nocache, 0)
            self.assertIs(mock_ind.call_args.kwargs["use_cache"], False)
            self.assertIs(mock_feat.call_args.kwargs["use_cache"], False)

    def test_evaluate_mode_single_ohlcv_fetch_no_lookahead_and_timings_sec(self):
        """
        mode='evaluate' (end_date=None) で OHLCV が1回で一括取得され ForwardReturnEvaluator が再取得しないこと、
        分析側へ as_of_date 以前のバーのみ渡ること、latest_close が財務取得へ渡ること、
        および timings_sec が戻り値・JSONメタデータ(elapsed_sec)・出力サマリーに含まれることを検証する。
        """
        screen_ohlcv = _build_uptrend_breakout_ohlcv("7203.T", days=90)
        asof_bar = screen_ohlcv[-1]
        as_of = asof_bar.date
        expected_asof_close = asof_bar.close
        forward_bars: list[OhlcvModel] = []
        for i in range(1, 26):
            close = expected_asof_close * (1.0 + 0.005 * i)
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
        full_ohlcv = screen_ohlcv + forward_bars
        fin_7203 = _build_sample_financial("7203.T")
        master_7203 = StockMasterModel(
            code="7203",
            symbol="7203.T",
            name="トヨタ自動車",
            market="プライム",
            sector_33="輸送用機器",
        )

        # 分析段階の入力バー日付（先読み防止）を記録する
        ind_calc = IndicatorCalculator()
        real_calculate_indicators = IndicatorCalculator.calculate_indicators
        recorded_ind_dates: list[date] = []
        recorded_feat_dates: list[date] = []
        recorded_pat_dates: list[date] = []
        recorded_score_dates: list[date] = []

        def spy_ind(ohlcv_data, **kwargs):
            recorded_ind_dates.extend(b.date for b in ohlcv_data)
            return real_calculate_indicators(ind_calc, ohlcv_data, use_cache=False)

        def spy_feat(ohlcv_data, indicator_data, financial_data=None, **kwargs):
            recorded_feat_dates.extend(b.date for b in ohlcv_data)
            return calculate_features(
                ohlcv_data, indicator_data, financial_data, use_cache=False
            )

        def spy_pat(ohlcv_data, indicator_data, **kwargs):
            recorded_pat_dates.extend(b.date for b in ohlcv_data)
            return detect_patterns(ohlcv_data, indicator_data, **kwargs)

        def spy_score(feature_sets, pattern_sets, **kwargs):
            ohlcv_arg = kwargs.get("ohlcv_data") or []
            recorded_score_dates.extend(b.date for b in ohlcv_arg)
            return calculate_scores(feature_sets, pattern_sets, **kwargs)

        expected_eval_fetch_end = ForwardReturnEvaluator.compute_default_fetch_end(as_of, [5, 20])

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "eval_single_fetch"
            stdout_buf = io.StringIO()
            with patch("src.main.MasterManager") as mock_master_cls, \
                 patch("src.main.prefetch_ohlcv_batch"), \
                 patch("src.main.collect_ohlcv_data", return_value=full_ohlcv) as mock_main_ohlcv, \
                 patch("src.main.collect_financial_data", return_value=fin_7203) as mock_main_fin, \
                 patch("src.evaluator.evaluator.data_collector.collect_ohlcv_data") as mock_eval_ohlcv, \
                 patch("src.main.IndicatorCalculator.calculate_indicators", side_effect=spy_ind), \
                 patch("src.main.calculate_features", side_effect=spy_feat), \
                 patch("src.main.detect_patterns", side_effect=spy_pat), \
                 patch("src.main.calculate_scores", side_effect=spy_score), \
                 redirect_stdout(stdout_buf):
                mock_master_cls.return_value.load_master.return_value = [master_7203]

                result = run_full_pipeline(
                    symbols=["7203.T"],
                    start_date=full_ohlcv[0].date,
                    end_date=None,
                    fiscal_year=2025,
                    as_of_date=as_of,
                    output_dir=out_dir,
                    export_reports=True,
                    mode="evaluate",
                    horizons=[5, 20],
                    use_cache=False,
                )

            # 1. OHLCV は eval_fetch_end まで一括取得され、Evaluator 側では再取得されない
            mock_main_ohlcv.assert_called_once_with(
                "7203.T",
                full_ohlcv[0].date,
                expected_eval_fetch_end,
                as_of_date=expected_eval_fetch_end,
            )
            mock_eval_ohlcv.assert_not_called()

            # 2. 財務取得へ as_of_date 時点の終値が渡されていること（未来日の終値ではない）
            mock_main_fin.assert_called_once()
            self.assertEqual(mock_main_fin.call_args.kwargs.get("latest_close"), expected_asof_close)

            # 3. 分析側の全工程で as_of_date より後のバーが渡されていないこと（先読みバイアスなし）
            for label, dates_list in (
                ("indicators", recorded_ind_dates),
                ("features", recorded_feat_dates),
                ("patterns", recorded_pat_dates),
                ("scores", recorded_score_dates),
            ):
                self.assertTrue(dates_list, f"{label} に渡された日付が空です")
                self.assertLessEqual(max(dates_list), as_of, f"{label} に未来日付が混入しています")

            # 4. フォワードリターン検証が共有 ohlcv_map を使って完了していること
            eval_summary = result["evaluation_summary"]
            self.assertIsNotNone(eval_summary)
            self.assertEqual(eval_summary.overall_summary[5].evaluated_count, 1)
            self.assertEqual(eval_summary.overall_summary[20].evaluated_count, 1)

            # 5. timings_sec が戻り値・標準出力サマリーに含まれ、JSONメタデータに elapsed_sec が記録されること
            expected_timing_keys = {
                "setup_and_prescreen",
                "ohlcv_collection",
                "liquidity_filter",
                "financial_collection",
                "indicator_calculation",
                "feature_calculation",
                "pattern_detection",
                "score_calculation",
                "screening_and_ranking",
                "forward_evaluation",
                "total",
            }
            timings = result["timings_sec"]
            self.assertEqual(set(timings.keys()), expected_timing_keys)
            for key, val in timings.items():
                self.assertIsInstance(val, float, f"{key} の型が float ではありません")
                self.assertGreaterEqual(val, 0.0, f"{key} が負数です")
            self.assertGreater(timings["total"], 0.0)

            payload = json.loads(result["report_paths"]["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["metadata"]["elapsed_sec"], timings["total"])
            self.assertNotIn("timings_sec", payload["metadata"])
            self.assertIn("フェーズ別所要時間:", stdout_buf.getvalue())

    def test_evaluate_mode_with_future_end_date_fetches_once_and_passes_eval_end_date(self):
        """
        mode='evaluate' で end_date > as_of_date を指定した場合、end_date まで1回で取得し
        eval_end_date=end_date で評価され、Evaluator 側で再取得しないことを検証する。
        """
        screen_ohlcv = _build_uptrend_breakout_ohlcv("7203.T", days=90)
        asof_bar = screen_ohlcv[-1]
        as_of = asof_bar.date
        eval_end = as_of + timedelta(days=10)

        forward_bars: list[OhlcvModel] = []
        for i in range(1, 11):
            close = asof_bar.close * (1.0 + 0.005 * i)
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
        full_ohlcv = screen_ohlcv + forward_bars
        fin_7203 = _build_sample_financial("7203.T")
        master_7203 = StockMasterModel(
            code="7203",
            symbol="7203.T",
            name="トヨタ自動車",
            market="プライム",
            sector_33="輸送用機器",
        )

        real_evaluate = ForwardReturnEvaluator.evaluate
        with patch("src.main.MasterManager") as mock_master_cls, \
             patch("src.main.prefetch_ohlcv_batch"), \
             patch("src.main.collect_ohlcv_data", return_value=full_ohlcv) as mock_main_ohlcv, \
             patch("src.main.collect_financial_data", return_value=fin_7203), \
             patch("src.evaluator.evaluator.data_collector.collect_ohlcv_data") as mock_eval_ohlcv, \
             patch.object(
                 ForwardReturnEvaluator,
                 "evaluate",
                 autospec=True,
                 side_effect=real_evaluate,
             ) as spy_evaluate:
            mock_master_cls.return_value.load_master.return_value = [master_7203]

            result = run_full_pipeline(
                symbols=["7203.T"],
                start_date=full_ohlcv[0].date,
                end_date=eval_end,
                fiscal_year=2025,
                as_of_date=as_of,
                export_reports=False,
                mode="evaluate",
                horizons=[5],
                use_cache=False,
            )

        mock_main_ohlcv.assert_called_once_with(
            "7203.T",
            full_ohlcv[0].date,
            eval_end,
            as_of_date=eval_end,
        )
        mock_eval_ohlcv.assert_not_called()
        spy_evaluate.assert_called_once()
        self.assertEqual(spy_evaluate.call_args.kwargs["eval_end_date"], eval_end)
        self.assertIn("7203.T", spy_evaluate.call_args.kwargs["ohlcv_map"])
        self.assertEqual(result["evaluation_summary"].overall_summary[5].evaluated_count, 1)

    def test_evaluate_mode_zero_forward_bars_does_not_refetch_and_returns_no_forward_data(self):
        """
        mode='evaluate' で一括取得時に未来バーが0件だった場合でも、
        Evaluator 側が再取得せず status == 'no_forward_data' になることを検証する。
        """
        screen_ohlcv = _build_uptrend_breakout_ohlcv("7203.T", days=90)
        as_of = screen_ohlcv[-1].date
        fin_7203 = _build_sample_financial("7203.T")
        master_7203 = StockMasterModel(
            code="7203",
            symbol="7203.T",
            name="トヨタ自動車",
            market="プライム",
            sector_33="輸送用機器",
        )

        with patch("src.main.MasterManager") as mock_master_cls, \
             patch("src.main.prefetch_ohlcv_batch"), \
             patch("src.main.collect_ohlcv_data", return_value=screen_ohlcv) as mock_main_ohlcv, \
             patch("src.main.collect_financial_data", return_value=fin_7203), \
             patch("src.evaluator.evaluator.data_collector.collect_ohlcv_data") as mock_eval_ohlcv:
            mock_master_cls.return_value.load_master.return_value = [master_7203]

            result = run_full_pipeline(
                symbols=["7203.T"],
                start_date=screen_ohlcv[0].date,
                end_date=None,
                fiscal_year=2025,
                as_of_date=as_of,
                export_reports=False,
                mode="evaluate",
                horizons=[5],
                use_cache=False,
            )

        mock_main_ohlcv.assert_called_once()
        mock_eval_ohlcv.assert_not_called()
        eval_summary = result["evaluation_summary"]
        self.assertIsNotNone(eval_summary)
        self.assertEqual(len(eval_summary.items), 1)
        self.assertEqual(eval_summary.items[0].status, "no_forward_data")
        self.assertEqual(eval_summary.overall_summary[5].evaluated_count, 0)

    def test_run_full_pipeline_calls_prefetch_ohlcv_batch_and_records_timing(self):
        """run_full_pipeline が prefetch_ohlcv_batch を期待引数で呼び、ohlcv_collection へ計上する"""
        ohlcv_7203 = _build_uptrend_breakout_ohlcv("7203.T", days=90)
        ohlcv_9984 = _build_uptrend_breakout_ohlcv("9984.T", days=90)
        fin_7203 = _build_sample_financial("7203.T")
        fin_9984 = _build_sample_financial("9984.T")
        masters = [
            StockMasterModel(code="7203", symbol="7203.T", name="トヨタ", market="プライム", sector_33="輸送用機器"),
            StockMasterModel(code="9984", symbol="9984.T", name="ソフトバンクG", market="プライム", sector_33="情報・通信業"),
        ]

        def slow_prefetch(*args, **kwargs):
            time.sleep(0.02)
            return {"total": 2, "skipped": 0, "batch_updated": 2, "retried_updated": 0, "failed": 0}

        with patch("src.main.MasterManager") as mock_master_cls, \
             patch("src.main.prefetch_ohlcv_batch", side_effect=slow_prefetch) as mock_prefetch, \
             patch("src.main.collect_ohlcv_data", side_effect=[ohlcv_7203, ohlcv_9984]), \
             patch("src.main.collect_financial_data", side_effect=[fin_7203, fin_9984]):
            mock_master_cls.return_value.load_master.return_value = masters

            result = run_full_pipeline(
                symbols=["7203.T", "9984.T"],
                start_date=date(2025, 10, 1),
                end_date=date(2025, 12, 31),
                fiscal_year=2025,
                as_of_date=date(2025, 12, 31),
                export_reports=False,
                use_cache=False,
            )

        mock_prefetch.assert_called_once_with(
            ["7203.T", "9984.T"],
            date(2025, 10, 1),
            date(2025, 12, 31),
            as_of_date=date(2025, 12, 31),
        )
        self.assertGreaterEqual(result["timings_sec"]["ohlcv_collection"], 0.015)

    def test_run_full_pipeline_real_collector_second_run_zero_network_calls(self):
        """実 DataCollector + モック yf.download で2回目パイプライン実行時に再通信ゼロとなることを検証"""
        # 2025-10-01 〜 2025-12-30（12/31は東証休場のため最終完了営業日は 12/30）
        bars_7203 = _build_uptrend_breakout_ohlcv("7203.T", days=91)
        bars_9984 = _build_uptrend_breakout_ohlcv("9984.T", days=91)

        def to_yf_frame(bars):
            df = pd.DataFrame([
                {
                    "Date": pd.Timestamp(b.date),
                    "Open": b.open,
                    "High": b.high,
                    "Low": b.low,
                    "Close": b.close,
                    "Volume": b.volume,
                }
                for b in bars
            ]).set_index("Date")
            return df

        multi_df = pd.concat(
            {
                "7203.T": to_yf_frame(bars_7203),
                "9984.T": to_yf_frame(bars_9984),
            },
            axis=1,
        )
        masters = [
            StockMasterModel(code="7203", symbol="7203.T", name="トヨタ", market="プライム", sector_33="輸送用機器"),
            StockMasterModel(code="9984", symbol="9984.T", name="ソフトバンクG", market="プライム", sector_33="情報・通信業"),
        ]
        fin_map = {
            "7203.T": _build_sample_financial("7203.T"),
            "9984.T": _build_sample_financial("9984.T"),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            real_collector = DataCollector()
            real_collector.storage = StorageManager(base_dir=Path(tmpdir))

            with patch("src.data_collector.collector.data_collector", real_collector), \
                 patch("src.main.data_collector", real_collector), \
                 patch("src.main.MasterManager") as mock_master_cls, \
                 patch("src.main.collect_financial_data", side_effect=lambda sym, *args, **kwargs: fin_map[sym]), \
                 patch("yfinance.download", return_value=multi_df) as mock_download, \
                 patch("yfinance.Ticker") as mock_ticker:
                mock_master_cls.return_value.load_master.return_value = masters

                # 1回目実行: yf.download が1回呼ばれ、個別 Ticker 取得は不要
                res1 = run_full_pipeline(
                    symbols=["7203.T", "9984.T"],
                    start_date=date(2025, 10, 1),
                    end_date=date(2025, 12, 31),
                    fiscal_year=2025,
                    as_of_date=date(2025, 12, 31),
                    export_reports=False,
                    use_cache=False,
                )
                self.assertEqual(res1["processed_symbols"], ["7203.T", "9984.T"])
                self.assertEqual(mock_download.call_count, 1)
                mock_ticker.assert_not_called()

                mock_download.reset_mock()
                mock_ticker.reset_mock()

                # 2回目実行: Parquet キャッシュが 2025-10-01〜2025-12-30（12/31休場マージン込）で十分なため再通信ゼロ
                res2 = run_full_pipeline(
                    symbols=["7203.T", "9984.T"],
                    start_date=date(2025, 10, 1),
                    end_date=date(2025, 12, 31),
                    fiscal_year=2025,
                    as_of_date=date(2025, 12, 31),
                    export_reports=False,
                    use_cache=False,
                )
                self.assertEqual(res2["processed_symbols"], ["7203.T", "9984.T"])
                mock_download.assert_not_called()
                mock_ticker.assert_not_called()

    def test_latest_only_per_symbol_propagates_and_matches_full_evaluation(self):
        """
        latest_only_per_symbol=True 時の最適化パス（latest_only=True 伝播）と
        全日付計算後 Screener 抽出（従来パス）、および latest_only_per_symbol=False の伝播を検証し、
        最終ランキングとフォワード評価結果が一致することを確認する。
        """
        screen_7203 = _build_uptrend_breakout_ohlcv("7203.T", days=90)
        screen_9984 = _build_uptrend_breakout_ohlcv("9984.T", days=90)
        as_of = screen_7203[-1].date

        # evaluate モード検証用のフォワードバーを追加
        def append_forward(bars):
            last = bars[-1]
            fwd = []
            for i in range(1, 7):
                c = last.close * (1.0 + 0.01 * i)
                fwd.append(
                    OhlcvModel(
                        symbol=last.symbol,
                        date=last.date + timedelta(days=i),
                        open=c - 2.0,
                        high=c + 5.0,
                        low=c - 5.0,
                        close=c,
                        volume=250_000,
                    )
                )
            return bars + fwd

        full_7203 = append_forward(screen_7203)
        full_9984 = append_forward(screen_9984)
        fin_map = {
            "7203.T": _build_sample_financial("7203.T"),
            "9984.T": _build_sample_financial("9984.T"),
        }
        masters = [
            StockMasterModel(code="7203", symbol="7203.T", name="トヨタ自動車", market="プライム", sector_33="輸送用機器"),
            StockMasterModel(code="9984", symbol="9984.T", name="ソフトバンクG", market="プライム", sector_33="情報・通信業"),
        ]
        ohlcv_by_sym = {"7203.T": full_7203, "9984.T": full_9984}

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            cfg_true_path = tmp_path / "cfg_true.yaml"
            cfg_false_path = tmp_path / "cfg_false.yaml"
            cfg_true_path.write_text(
                "screener:\n  latest_only_per_symbol: true\n", encoding="utf-8"
            )
            cfg_false_path.write_text(
                "screener:\n  latest_only_per_symbol: false\n", encoding="utf-8"
            )

            # 1. latest_only_per_symbol=True（最適化パス: latest_only=True が伝播）
            with patch("src.main.MasterManager") as mock_master_cls, \
                 patch("src.main.prefetch_ohlcv_batch"), \
                 patch("src.main.collect_ohlcv_data", side_effect=lambda sym, *a, **kw: ohlcv_by_sym[sym]), \
                 patch("src.main.collect_financial_data", side_effect=lambda sym, *a, **kw: fin_map[sym]), \
                 patch("src.main.calculate_features", wraps=calculate_features) as spy_feat_opt, \
                 patch("src.main.detect_patterns", wraps=detect_patterns) as spy_pat_opt:
                mock_master_cls.return_value.load_master.return_value = masters
                res_opt = run_full_pipeline(
                    symbols=["7203.T", "9984.T"],
                    start_date=screen_7203[0].date,
                    end_date=None,
                    fiscal_year=2025,
                    as_of_date=as_of,
                    config_path=cfg_true_path,
                    export_reports=False,
                    mode="evaluate",
                    horizons=[5],
                    use_cache=False,
                )
                self.assertEqual(spy_feat_opt.call_count, 2)
                self.assertEqual(spy_pat_opt.call_count, 2)
                for c in spy_feat_opt.call_args_list:
                    self.assertIs(c.kwargs.get("latest_only"), True)
                for c in spy_pat_opt.call_args_list:
                    self.assertIs(c.kwargs.get("latest_only"), True)

            # 2. 従来動作相当（全日付計算してから Screener(latest_only_per_symbol=True) で最新日抽出）
            def full_calc_feat(ohlcv_data, indicator_data, financial_data=None, **kwargs):
                kwargs["latest_only"] = False
                return calculate_features(ohlcv_data, indicator_data, financial_data, **kwargs)

            def full_det_pat(ohlcv_data, indicator_data, **kwargs):
                kwargs["latest_only"] = False
                return detect_patterns(ohlcv_data, indicator_data, **kwargs)

            with patch("src.main.MasterManager") as mock_master_cls, \
                 patch("src.main.prefetch_ohlcv_batch"), \
                 patch("src.main.collect_ohlcv_data", side_effect=lambda sym, *a, **kw: ohlcv_by_sym[sym]), \
                 patch("src.main.collect_financial_data", side_effect=lambda sym, *a, **kw: fin_map[sym]), \
                 patch("src.main.calculate_features", side_effect=full_calc_feat), \
                 patch("src.main.detect_patterns", side_effect=full_det_pat):
                mock_master_cls.return_value.load_master.return_value = masters
                res_full_legacy = run_full_pipeline(
                    symbols=["7203.T", "9984.T"],
                    start_date=screen_7203[0].date,
                    end_date=None,
                    fiscal_year=2025,
                    as_of_date=as_of,
                    config_path=cfg_true_path,
                    export_reports=False,
                    mode="evaluate",
                    horizons=[5],
                    use_cache=False,
                )

            # 最終ランキングと評価結果が完全一致すること
            self.assertEqual(len(res_opt["score_results"]), 2)
            self.assertGreater(len(res_full_legacy["score_results"]), 2)
            self.assertEqual(
                [r.model_dump() for r in res_opt["analysis_results"]],
                [r.model_dump() for r in res_full_legacy["analysis_results"]],
            )
            self.assertEqual(
                res_opt["evaluation_summary"].model_dump(),
                res_full_legacy["evaluation_summary"].model_dump(),
            )

            # 3. latest_only_per_symbol=False の場合は latest_only=False が伝播する
            with patch("src.main.MasterManager") as mock_master_cls, \
                 patch("src.main.prefetch_ohlcv_batch"), \
                 patch("src.main.collect_ohlcv_data", side_effect=lambda sym, *a, **kw: ohlcv_by_sym[sym]), \
                 patch("src.main.collect_financial_data", side_effect=lambda sym, *a, **kw: fin_map[sym]), \
                 patch("src.main.calculate_features", wraps=calculate_features) as spy_feat_false, \
                 patch("src.main.detect_patterns", wraps=detect_patterns) as spy_pat_false:
                mock_master_cls.return_value.load_master.return_value = masters
                res_false = run_full_pipeline(
                    symbols=["7203.T"],
                    start_date=screen_7203[0].date,
                    end_date=as_of,
                    fiscal_year=2025,
                    as_of_date=as_of,
                    config_path=cfg_false_path,
                    export_reports=False,
                    use_cache=False,
                )
                self.assertIs(spy_feat_false.call_args.kwargs.get("latest_only"), False)
                self.assertIs(spy_pat_false.call_args.kwargs.get("latest_only"), False)
                self.assertGreater(len(res_false["score_results"]), 1)

    def test_resolve_worker_count_and_cli_args(self):
        """_resolve_worker_count の実環境変数参照・異常値エラー・閾値制御、CLI競合チェックおよび run_batch_backtest バリデーションを検証する"""
        orig_env = os.environ.get("FEATURE_ENGINE_PARALLEL_PROCESSES")
        try:
            os.environ["FEATURE_ENGINE_PARALLEL_PROCESSES"] = "3"
            self.assertEqual(_resolve_worker_count(None, 25), 3)
            self.assertEqual(_resolve_worker_count(None, 19), 1)
            self.assertEqual(_resolve_worker_count(None, 5, parallel_min_symbols=2), 3)
        finally:
            if orig_env is None:
                os.environ.pop("FEATURE_ENGINE_PARALLEL_PROCESSES", None)
            else:
                os.environ["FEATURE_ENGINE_PARALLEL_PROCESSES"] = orig_env

        self.assertEqual(_resolve_worker_count(1, 100, parallel_min_symbols=2), 1)
        self.assertEqual(_resolve_worker_count(8, 5, parallel_min_symbols=2), 5)
        self.assertEqual(DEFAULT_PARALLEL_MIN_SYMBOLS, 20)

        for invalid in (0, -1, True, False):
            with self.assertRaises(ValueError):
                _resolve_worker_count(invalid, 10)

        with self.assertRaises(ValueError):
            run_batch_backtest(
                as_of_dates=[date(2025, 5, 15), date(2025, 6, 5)],
                end_date=date(2025, 6, 1),
            )
        for bad_lb in (0, -5, True, False):
            with self.assertRaises(ValueError):
                run_batch_backtest(
                    as_of_dates=[date(2025, 5, 15)],
                    lookback_days=bad_lb,
                )

        # --mode evaluate と --as-of-dates の併用は終了コード 1
        self.assertEqual(
            main(["--mode", "evaluate", "--as-of-dates", "2025-05-15"]),
            1,
        )

        ns = parse_args(
            [
                "--mode",
                "backtest",
                "--as-of-dates",
                "2025-05-15",
                "2025-06-05",
                "--workers",
                "3",
            ]
        )
        self.assertEqual(ns.mode, "backtest")
        self.assertEqual(ns.as_of_dates, [date(2025, 5, 15), date(2025, 6, 5)])
        self.assertEqual(ns.workers, 3)

    @staticmethod
    def _write_temp_env(
        tmpdir: str,
        bars_by_symbol: dict[str, list[OhlcvModel]],
        bs_by_year: dict[int, dict],
        pl_by_year: dict[int, dict],
    ) -> DataCollector:
        tmp_path = Path(tmpdir)
        storage = StorageManager(base_dir=tmp_path)
        for sym, bars in bars_by_symbol.items():
            df = pd.DataFrame(
                [
                    {
                        "date": b.date,
                        "open": b.open,
                        "high": b.high,
                        "low": b.low,
                        "close": b.close,
                        "volume": b.volume,
                    }
                    for b in bars
                ]
            )
            storage.save_parquet(df, f"price/{sym}.parquet")

        for yr, bs in bs_by_year.items():
            suffix = f"00{str(yr)[-2:]}"
            storage.save_json(bs, f"financial/{suffix}-fy-balance-sheet.json")
        for yr, pl in pl_by_year.items():
            suffix = f"00{str(yr)[-2:]}"
            storage.save_json(pl, f"financial/{suffix}-fy-profit-and-loss.json")

        collector = DataCollector()
        collector.storage = storage
        collector.cache_dir = str(tmp_path / "cache")
        collector.local_irbank_dir = str(tmp_path / "irbank_local")
        collector.user_irbank_dir = str(tmp_path / "irbank_user")
        Path(collector.local_irbank_dir).mkdir(parents=True, exist_ok=True)
        Path(collector.user_irbank_dir).mkdir(parents=True, exist_ok=True)
        return collector

    @staticmethod
    def _snapshot_tree(root: Path) -> dict[str, tuple[int, int]]:
        snap: dict[str, tuple[int, int]] = {}
        for p in sorted(root.rglob("*")):
            if p.is_file():
                st = p.stat()
                snap[str(p.relative_to(root))] = (st.st_mtime_ns, st.st_size)
        return snap

    def test_run_full_pipeline_multiprocess_matches_sequential_and_enforces_read_only(self):
        """ProcessPoolExecutor(workers=2) の結果が workers=1 と一致し、ワーカーが読取専用かつ1銘柄失敗を隔離する"""
        bars_7203 = _build_uptrend_breakout_ohlcv("7203.T", days=90)
        bars_6758 = _build_uptrend_breakout_ohlcv("6758.T", days=90)
        bars_9984 = _build_uptrend_breakout_ohlcv("9984.T", days=90)
        as_of = bars_7203[-1].date

        bs_2025 = {
            "item": {
                "7203": ["2025/03", "100000", "0", "0", "0", "0", "0", "1200.0", "45.0"],
                "6758": ["2025/03", "80000", "0", "0", "0", "0", "0", "1100.0", "42.0"],
                "9984": ["2025/03", "90000", "0", "0", "0", "0", "0", "1300.0", "40.0"],
            }
        }
        pl_2025 = {
            "item": {
                "7203": ["2025/03", "50000000000", "5000000000", "5200000000", "3500000000", "150.0", "15.0", "8.0"],
                "6758": ["2025/03", "40000000000", "4000000000", "4100000000", "2800000000", "140.0", "14.0", "7.5"],
                "9984": ["2025/03", "45000000000", "4500000000", "4700000000", "3100000000", "160.0", "16.0", "8.5"],
            }
        }
        masters = [
            StockMasterModel(code="7203", symbol="7203.T", name="トヨタ自動車", market="プライム", sector_33="輸送用機器"),
            StockMasterModel(code="6758", symbol="6758.T", name="ソニーG", market="プライム", sector_33="電気機器"),
            StockMasterModel(code="9984", symbol="9984.T", name="ソフトバンクG", market="プライム", sector_33="情報・通信業"),
            StockMasterModel(code="8888", symbol="8888.T", name="破損銘柄", market="プライム", sector_33="その他"),
            StockMasterModel(code="9999", symbol="9999.T", name="欠損銘柄", market="プライム", sector_33="その他"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            real_collector = self._write_temp_env(
                tmpdir,
                {"7203.T": bars_7203, "6758.T": bars_6758, "9984.T": bars_9984},
                bs_by_year={2025: bs_2025},
                pl_by_year={2025: pl_2025},
            )
            # 8888.T に不正バイト列の破損 Parquet を配置し、子プロセス内で実際に例外送出させてエラー隔離を検証する
            (Path(tmpdir) / "price" / "8888.T.parquet").write_bytes(b"not-a-valid-parquet-file")
            # 破損銘柄 8888.T（例外）と欠損銘柄 9999.T（空）を混ぜてもワーカー・親プロセスが落ちずに残り3銘柄を処理できる
            target_syms = ["7203.T", "8888.T", "9999.T", "6758.T", "9984.T"]
            before_snapshot = self._snapshot_tree(Path(tmpdir))

            with patch("src.data_collector.collector.data_collector", real_collector), \
                 patch("src.main.data_collector", real_collector), \
                 patch("src.main.prefetch_ohlcv_batch"), \
                 patch("src.main.MasterManager") as mock_master_cls:
                mock_master_cls.return_value.load_master.return_value = masters

                # 1. 先に workers=2 (use_cache=True, use_feature_cache=True) を実行し、読取専用制約で書込ゼロを検証
                res_par = run_full_pipeline(
                    symbols=target_syms,
                    start_date=bars_7203[0].date,
                    end_date=as_of,
                    fiscal_year=2025,
                    as_of_date=as_of,
                    export_reports=False,
                    use_cache=True,
                    use_feature_cache=True,
                    allow_irbank_download=False,
                    workers=2,
                    parallel_min_symbols=2,
                )
                after_par_snapshot = self._snapshot_tree(Path(tmpdir))
                self.assertEqual(before_snapshot, after_par_snapshot)

                # 2. 同一条件 (use_cache=True, use_feature_cache=True) の workers=1 と結果が完全一致し、
                # 逐次側でも同一StorageManager(tmpdir)へ対称的にキャッシュ保存されることを検証
                res_seq = run_full_pipeline(
                    symbols=target_syms,
                    start_date=bars_7203[0].date,
                    end_date=as_of,
                    fiscal_year=2025,
                    as_of_date=as_of,
                    export_reports=False,
                    use_cache=True,
                    use_feature_cache=True,
                    allow_irbank_download=False,
                    workers=1,
                    parallel_min_symbols=2,
                )
                self.assertTrue((Path(tmpdir) / "cache" / f"indicators_7203.T_asof_{as_of.isoformat()}.json").exists())

            self.assertEqual(res_seq["processed_symbols"], ["7203.T", "6758.T", "9984.T"])
            self.assertEqual(res_par["processed_symbols"], res_seq["processed_symbols"])
            self.assertEqual(
                [r.model_dump() for r in res_par["score_results"]],
                [r.model_dump() for r in res_seq["score_results"]],
            )
            self.assertEqual(
                [r.model_dump() for r in res_par["analysis_results"]],
                [r.model_dump() for r in res_seq["analysis_results"]],
            )

    def test_run_batch_backtest_single_fetch_zero_lookahead_and_disclosure_lag(self):
        """
        run_batch_backtest において:
        1) collect_ohlcv_data と calculate_indicators が銘柄あたり1回しか呼ばれない
        2) 未来日の株価を極端値へ改ざんしても過去基準日のスコア・ランキングが1ビットも変化しない
        3) 基準日間の開示ラグによる財務データ切り替えが正しく反映される
        """
        # 2025-02-01 〜 2025-07-10 まで約160日分の日次バーを生成
        start_dt = date(2025, 2, 1)
        d1 = date(2025, 5, 15)  # 2025/03期 + 60日(=2025-05-30) 未到達 -> 2024/03期を採用
        d2 = date(2025, 6, 5)   # 2025/03期 開示済み -> 2025/03期を採用

        def build_series(symbol: str, spike_after_d1: bool = False) -> list[OhlcvModel]:
            bars: list[OhlcvModel] = []
            for i in range(160):
                dt = start_dt + timedelta(days=i)
                base_close = 1000.0 + i * 3.0
                if spike_after_d1 and dt > d1:
                    # d1 より後の未来バーを極端な異常値へ改ざん
                    base_close = 999_999.0 if i % 2 == 0 else 1.0
                bars.append(
                    OhlcvModel(
                        symbol=symbol,
                        date=dt,
                        open=base_close - 2.0,
                        high=base_close + 8.0,
                        low=base_close - 8.0,
                        close=base_close,
                        volume=300_000,
                    )
                )
            return bars

        bs_2024 = {
            "item": {
                "7203": ["2024/03", "80000", "0", "0", "0", "0", "0", "1000.0", "40.0"],
                "6758": ["2024/03", "70000", "0", "0", "0", "0", "0", "900.0", "38.0"],
            }
        }
        pl_2024 = {
            "item": {
                "7203": ["2024/03", "40000000000", "3000000000", "3100000000", "2000000000", "100.0", "10.0", "5.0"],
                "6758": ["2024/03", "35000000000", "2500000000", "2600000000", "1800000000", "90.0", "9.0", "4.5"],
            }
        }
        bs_2025 = {
            "item": {
                "7203": ["2025/03", "100000", "0", "0", "0", "0", "0", "1200.0", "48.0"],
                "6758": ["2025/03", "90000", "0", "0", "0", "0", "0", "1100.0", "46.0"],
            }
        }
        pl_2025 = {
            "item": {
                "7203": ["2025/03", "60000000000", "7000000000", "7200000000", "5000000000", "250.0", "20.0", "10.0"],
                "6758": ["2025/03", "50000000000", "6000000000", "6200000000", "4000000000", "200.0", "18.0", "9.0"],
            }
        }
        masters = [
            StockMasterModel(code="7203", symbol="7203.T", name="トヨタ自動車", market="プライム", sector_33="輸送用機器"),
            StockMasterModel(code="6758", symbol="6758.T", name="ソニーG", market="プライム", sector_33="電気機器"),
        ]

        orig_bars = {"7203.T": build_series("7203.T", False), "6758.T": build_series("6758.T", False)}
        tampered_bars = {"7203.T": build_series("7203.T", True), "6758.T": build_series("6758.T", True)}

        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            col_orig = self._write_temp_env(
                tmp1, orig_bars, {2024: bs_2024, 2025: bs_2025}, {2024: pl_2024, 2025: pl_2025}
            )
            with patch("src.data_collector.collector.data_collector", col_orig), \
                 patch("src.main.data_collector", col_orig), \
                 patch("src.main.prefetch_ohlcv_batch"), \
                 patch("src.main.collect_ohlcv_data", wraps=col_orig.collect_ohlcv_data) as spy_ohlcv, \
                 patch.object(IndicatorCalculator, "calculate_indicators", autospec=True, wraps=IndicatorCalculator.calculate_indicators) as spy_ind, \
                 patch("src.main.MasterManager") as mock_master_cls:
                mock_master_cls.return_value.load_master.return_value = masters

                res_orig = run_batch_backtest(
                    as_of_dates=[d2, d1, d1],  # 重複＆降順で渡す
                    symbols=["7203.T", "6758.T"],
                    start_date=start_dt,
                    end_date=date(2025, 7, 5),
                    horizons=[5],
                    export_reports=False,
                    use_cache=False,
                    allow_irbank_download=False,
                    workers=1,
                )

            # 1) 2基準日×2銘柄でも OHLCV 読込と指標算出は各銘柄1回ずつ（計2回）
            self.assertEqual(spy_ohlcv.call_count, 2)
            self.assertEqual(spy_ind.call_count, 2)
            self.assertEqual(res_orig["as_of_dates"], [d1, d2])

            # 3) 開示ラグによる財務データ切り替え検証 (d1=2025-05-15 -> ROE 10.0%, d2=2025-06-05 -> ROE 20.0%)
            d1_7203 = next(r for r in res_orig["per_date_results"][d1]["analysis_results"] if r.symbol == "7203.T")
            d2_7203 = next(r for r in res_orig["per_date_results"][d2]["analysis_results"] if r.symbol == "7203.T")
            self.assertEqual(d1_7203.financial_summary["roe"], 10.0)
            self.assertEqual(d2_7203.financial_summary["roe"], 20.0)

            # 2) d1 より後の未来バーを極端値へ改ざんして再実行しても d1 のスコア・ランキングは1ビットも変化しない
            col_tampered = self._write_temp_env(
                tmp2, tampered_bars, {2024: bs_2024, 2025: bs_2025}, {2024: pl_2024, 2025: pl_2025}
            )
            with patch("src.data_collector.collector.data_collector", col_tampered), \
                 patch("src.main.data_collector", col_tampered), \
                 patch("src.main.prefetch_ohlcv_batch"), \
                 patch("src.main.collect_ohlcv_data", wraps=col_tampered.collect_ohlcv_data), \
                 patch("src.main.MasterManager") as mock_master_cls:
                mock_master_cls.return_value.load_master.return_value = masters

                res_tampered = run_batch_backtest(
                    as_of_dates=[d1, d2],
                    symbols=["7203.T", "6758.T"],
                    start_date=start_dt,
                    end_date=date(2025, 7, 5),
                    horizons=[5],
                    export_reports=False,
                    use_cache=False,
                    allow_irbank_download=False,
                    workers=1,
                )

            self.assertEqual(
                [s.model_dump() for s in res_orig["per_date_results"][d1]["score_results"]],
                [s.model_dump() for s in res_tampered["per_date_results"][d1]["score_results"]],
            )
            self.assertEqual(
                [r.model_dump() for r in res_orig["per_date_results"][d1]["analysis_results"]],
                [r.model_dump() for r in res_tampered["per_date_results"][d1]["analysis_results"]],
            )

    def test_run_batch_backtest_multiprocess_and_cli_dispatch(self):
        """run_batch_backtest の workers=2 並列一致、および CLI --mode backtest / --as-of-dates を検証"""
        # --mode backtest で日付未指定時は終了コード 1
        self.assertEqual(main(["--mode", "backtest"]), 1)

        start_dt = date(2025, 2, 1)
        d1 = date(2025, 5, 15)
        d2 = date(2025, 6, 5)

        def make_bars(sym: str) -> list[OhlcvModel]:
            out = []
            for i in range(150):
                c = 1000.0 + i * 3.0
                out.append(
                    OhlcvModel(
                        symbol=sym,
                        date=start_dt + timedelta(days=i),
                        open=c - 2.0,
                        high=c + 8.0,
                        low=c - 8.0,
                        close=c,
                        volume=300_000,
                    )
                )
            return out

        bs_2024 = {"item": {"7203": ["2024/03", "80000", "0", "0", "0", "0", "0", "1000.0", "40.0"], "6758": ["2024/03", "70000", "0", "0", "0", "0", "0", "900.0", "38.0"]}}
        pl_2024 = {"item": {"7203": ["2024/03", "40000000000", "3000000000", "3100000000", "2000000000", "100.0", "10.0", "5.0"], "6758": ["2024/03", "35000000000", "2500000000", "2600000000", "1800000000", "90.0", "9.0", "4.5"]}}
        bs_2025 = {"item": {"7203": ["2025/03", "100000", "0", "0", "0", "0", "0", "1200.0", "48.0"], "6758": ["2025/03", "90000", "0", "0", "0", "0", "0", "1100.0", "46.0"]}}
        pl_2025 = {"item": {"7203": ["2025/03", "60000000000", "7000000000", "7200000000", "5000000000", "250.0", "20.0", "10.0"], "6758": ["2025/03", "50000000000", "6000000000", "6200000000", "4000000000", "200.0", "18.0", "9.0"]}}
        masters = [
            StockMasterModel(code="7203", symbol="7203.T", name="トヨタ自動車", market="プライム", sector_33="輸送用機器"),
            StockMasterModel(code="6758", symbol="6758.T", name="ソニーG", market="プライム", sector_33="電気機器"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            real_collector = self._write_temp_env(
                tmpdir,
                {"7203.T": make_bars("7203.T"), "6758.T": make_bars("6758.T")},
                {2024: bs_2024, 2025: bs_2025},
                {2024: pl_2024, 2025: pl_2025},
            )
            out_dir = Path(tmpdir) / "reports"
            before_snapshot = self._snapshot_tree(Path(tmpdir))

            with patch("src.data_collector.collector.data_collector", real_collector), \
                 patch("src.main.data_collector", real_collector), \
                 patch("src.main.prefetch_ohlcv_batch"), \
                 patch("src.main.MasterManager") as mock_master_cls:
                mock_master_cls.return_value.load_master.return_value = masters

                # 1. 先に workers=2 (use_cache=True, use_feature_cache=True, export_reports=False) を実行し、
                # 並列ワーカー実行で cache/*.json や price/*.parquet が一切作成・更新されないことを検証
                res_par_ro = run_batch_backtest(
                    as_of_dates=[d1, d2],
                    symbols=["7203.T", "6758.T"],
                    start_date=start_dt,
                    end_date=date(2025, 6, 30),
                    horizons=[5],
                    export_reports=False,
                    use_cache=True,
                    use_feature_cache=True,
                    allow_irbank_download=False,
                    workers=2,
                    parallel_min_symbols=2,
                )
                after_par_snapshot = self._snapshot_tree(Path(tmpdir))
                self.assertEqual(before_snapshot, after_par_snapshot)

                # 2. 同一条件 (use_cache=True, use_feature_cache=True) の workers=1 と結果完全一致を検証
                res_seq = run_batch_backtest(
                    as_of_dates=[d1, d2],
                    symbols=["7203.T", "6758.T"],
                    start_date=start_dt,
                    end_date=date(2025, 6, 30),
                    horizons=[5],
                    export_reports=False,
                    use_cache=True,
                    use_feature_cache=True,
                    allow_irbank_download=False,
                    workers=1,
                    parallel_min_symbols=2,
                )

                # 3. レポート出力付き並列実行
                res_par = run_batch_backtest(
                    as_of_dates=[d1, d2],
                    symbols=["7203.T", "6758.T"],
                    start_date=start_dt,
                    end_date=date(2025, 6, 30),
                    horizons=[5],
                    output_dir=out_dir,
                    export_reports=True,
                    use_cache=True,
                    use_feature_cache=True,
                    allow_irbank_download=False,
                    workers=2,
                    parallel_min_symbols=2,
                )

                self.assertEqual(res_seq["workers_used"], 1)
                self.assertEqual(res_par_ro["workers_used"], 2)
                self.assertEqual(res_par["workers_used"], 2)
                self.assertEqual(
                    set(res_par["timings_sec"].keys()),
                    {
                        "setup_and_prescreen",
                        "ohlcv_collection",
                        "symbol_evaluation",
                        "screening_and_ranking",
                        "forward_evaluation",
                        "total",
                    },
                )
                self.assertEqual(
                    res_par_ro["batch_summary"].model_dump(),
                    res_seq["batch_summary"].model_dump(),
                )
                self.assertEqual(
                    res_par["batch_summary"].model_dump(),
                    res_seq["batch_summary"].model_dump(),
                )
                for d in (d1, d2):
                    self.assertEqual(
                        [r.model_dump() for r in res_par_ro["per_date_results"][d]["analysis_results"]],
                        [r.model_dump() for r in res_seq["per_date_results"][d]["analysis_results"]],
                    )
                self.assertTrue(res_par["report_paths"]["json"].exists())
                self.assertTrue(res_par["report_paths"]["markdown"].exists())

                # CLI --as-of-dates（--mode 省略時でも run_batch_backtest が呼ばれる）
                exit_code = main(
                    [
                        "--as-of-dates",
                        d1.isoformat(),
                        d2.isoformat(),
                        "--symbols",
                        "7203.T",
                        "6758.T",
                        "--start-date",
                        start_dt.isoformat(),
                        "--end-date",
                        "2025-06-30",
                        "--horizons",
                        "5",
                        "--output-dir",
                        str(out_dir),
                        "--no-cache",
                        "--no-irbank-download",
                        "--workers",
                        "1",
                    ]
                )
                self.assertEqual(exit_code, 0)

    def test_run_batch_backtest_prescreening_warmup_and_dynamic_liquidity(self):
        """
        run_batch_backtest で symbols=None 事前スクリーニング＋流動性フィルタを有効にした際:
        1) _resolve_target_symbols 前に warmup_irbank_cache が実行され初回でも 0銘柄化しないこと
        2) 基準日ごとに開示済み財務・流動性通過銘柄が動的に切り替わること
        """
        start_dt = date(2025, 2, 1)
        d1 = date(2025, 5, 15)  # 7203 のみ流動性通過・開示済み
        d2 = date(2025, 6, 15)  # 6758 も流動性通過・2025/03期開示済み

        bars_7203: list[OhlcvModel] = []
        bars_6758: list[OhlcvModel] = []
        for i in range(150):
            dt = start_dt + timedelta(days=i)
            c = 1000.0 + i * 3.0
            bars_7203.append(
                OhlcvModel(
                    symbol="7203.T",
                    date=dt,
                    open=c - 2.0,
                    high=c + 8.0,
                    low=c - 8.0,
                    close=c,
                    volume=300_000,  # 常に売買代金 > 3億円（1億円基準クリア）
                )
            )
            # 6758 は 5/20 以降から出来高増加（d1 時点では売買代金不足、d2 時点では流動性クリア）
            vol_6758 = 10_000 if dt <= d1 else 300_000
            bars_6758.append(
                OhlcvModel(
                    symbol="6758.T",
                    date=dt,
                    open=c - 2.0,
                    high=c + 8.0,
                    low=c - 8.0,
                    close=c,
                    volume=vol_6758,
                )
            )

        irbank_payloads = {
            ("0024", "fy-balance-sheet.json"): {
                "item": {
                    "7203": ["2024/03", "80000", "0", "0", "0", "0", "0", "1000.0", "40.0"],
                    "6758": ["2024/03", "70000", "0", "0", "0", "0", "0", "900.0", "38.0"],
                }
            },
            ("0024", "fy-profit-and-loss.json"): {
                "item": {
                    "7203": ["2024/03", "40000000000", "3000000000", "3100000000", "2000000000", "100.0", "10.0", "5.0"],
                    "6758": ["2024/03", "35000000000", "2500000000", "2600000000", "1800000000", "90.0", "9.0", "4.5"],
                }
            },
            ("0025", "fy-balance-sheet.json"): {
                "item": {
                    "7203": ["2025/03", "100000", "0", "0", "0", "0", "0", "1200.0", "48.0"],
                    "6758": ["2025/03", "90000", "0", "0", "0", "0", "0", "1100.0", "46.0"],
                }
            },
            ("0025", "fy-profit-and-loss.json"): {
                "item": {
                    "7203": ["2025/03", "60000000000", "7000000000", "7200000000", "5000000000", "250.0", "20.0", "10.0"],
                    "6758": ["2025/03", "50000000000", "6000000000", "6200000000", "4000000000", "200.0", "18.0", "9.0"],
                }
            },
        }
        masters = [
            StockMasterModel(code="7203", symbol="7203.T", name="トヨタ自動車", market="プライム", sector_33="輸送用機器"),
            StockMasterModel(code="6758", symbol="6758.T", name="ソニーG", market="プライム", sector_33="電気機器"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            # 初期状態では IR BANK JSON を一切置かない（初回実行シミュレーション）
            real_collector = self._write_temp_env(
                tmpdir,
                {"7203.T": bars_7203, "6758.T": bars_6758},
                bs_by_year={},
                pl_by_year={},
            )

            def fake_download_irbank(year_suffix: str, fy_type: str, save_path: str, timeout: int = 15):
                payload = irbank_payloads.get((year_suffix, fy_type))
                if payload is None:
                    raise RuntimeError(f"missing mock payload: {year_suffix}-{fy_type}")
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                Path(save_path).write_text(json.dumps(payload), encoding="utf-8")

            with patch("src.data_collector.collector.data_collector", real_collector), \
                 patch("src.main.data_collector", real_collector), \
                 patch.object(real_collector, "_download_irbank_file", side_effect=fake_download_irbank) as mock_dl, \
                 patch("src.main.prefetch_ohlcv_batch"), \
                 patch("src.main.MasterManager") as mock_master_cls:
                mock_master_cls.return_value.load_master.return_value = masters

                res = run_batch_backtest(
                    as_of_dates=[d1, d2],
                    symbols=None,
                    start_date=start_dt,
                    end_date=date(2025, 6, 30),
                    horizons=[5],
                    apply_liquidity_filter=True,
                    export_reports=False,
                    use_cache=True,
                    allow_irbank_download=True,
                    workers=2,
                    parallel_min_symbols=2,
                )

            self.assertGreaterEqual(mock_dl.call_count, 4)
            # d1 時点では 7203.T のみ流動性通過、d2 時点では両銘柄通過
            self.assertEqual(res["per_date_results"][d1]["processed_symbols"], ["7203.T"])
            self.assertEqual(res["per_date_results"][d2]["processed_symbols"], ["7203.T", "6758.T"])


if __name__ == "__main__":
    unittest.main()
