from pathlib import Path
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

from pydantic import ValidationError

from src.config.screening_config import (
    AtlasScreeningConfig,
    EvaluationConfig,
    OutputConfig,
    RankingConfig,
    load_screening_config,
)
from src.config.settings import Settings
from src.model.data_models import FeatureResultModel, FeatureSetModel
import src.score_engine  # レジストリ登録
from src.score_engine.manager import ScoreManager
from src.score_engine.scores.strategy import StrategyScoreConfig


class TestScreeningConfig(unittest.TestCase):
    def test_load_project_default_yaml(self):
        """プロジェクトルートの config/screening.yaml を読み込み、チューニング済み設定と一致することを確認する"""
        project_yaml = (
            Path(__file__).resolve().parents[3] / "config" / "screening.yaml"
        )
        self.assertTrue(project_yaml.exists())

        config = load_screening_config(project_yaml)
        self.assertIsInstance(config, AtlasScreeningConfig)
        self.assertEqual(config.pre_screening.target_markets, ["プライム", "スタンダード"])
        self.assertEqual(config.pre_screening.min_revenue, 10_000_000_000.0)
        self.assertEqual(config.strategy_score.min_entry_score, 60.0)
        self.assertEqual(config.strategy_score.extreme_volatility_penalty, 20.0)
        self.assertEqual(config.strategy_score.extreme_volatility_ratio_threshold, 2.0)
        self.assertEqual(config.strategy_score.sma75_dev_overheat_threshold, 0.25)
        self.assertEqual(config.strategy_score.sma75_dev_overheat_penalty, 12.0)
        self.assertEqual(config.strategy_score.gap_up_overheat_threshold, 0.07)
        self.assertEqual(config.strategy_score.gap_up_overheat_penalty, 10.0)
        self.assertEqual(config.strategy_score.pullback_rsi_ideal_min, 40.0)
        self.assertEqual(config.strategy_score.pullback_rsi_ideal_max, 60.0)
        self.assertEqual(config.strategy_score.breakout_rsi_ideal_min, 55.0)
        self.assertEqual(config.strategy_score.breakout_rsi_ideal_max, 75.0)
        self.assertEqual(config.strategy_score.rsi_overheat_threshold, 80.0)
        self.assertEqual(config.strategy_score.rsi_overheat_penalty, 8.0)
        self.assertEqual(config.strategy_score.short_rsi_rebound_bonus, 5.0)
        self.assertEqual(config.strategy_score.pullback_weight_p001, 0.32)
        self.assertEqual(config.strategy_score.pullback_weight_trend_env, 0.20)
        self.assertEqual(config.strategy_score.pullback_weight_o001, 0.10)
        self.assertEqual(config.strategy_score.pullback_weight_fundamental, 0.22)
        self.assertEqual(config.strategy_score.pullback_weight_volatility_stability, 0.12)
        self.assertEqual(config.strategy_score.pullback_weight_v001, 0.04)
        self.assertEqual(config.strategy_score.double_bottom_bonus_max, 6.0)
        self.assertEqual(config.strategy_score.pullback_dryup_rebound_bonus, 5.0)
        self.assertEqual(config.strategy_score.double_top_penalty_factor, 0.45)
        self.assertEqual(config.strategy_score.breakout_weight_p002, 0.33)
        self.assertEqual(config.strategy_score.breakout_weight_v001, 0.22)
        self.assertEqual(config.strategy_score.breakout_weight_trend_env, 0.13)
        self.assertEqual(config.strategy_score.breakout_weight_fundamental, 0.22)
        self.assertEqual(config.strategy_score.fundamental_weight_f001, 0.05)
        self.assertEqual(config.strategy_score.fundamental_weight_f002, 0.20)
        self.assertEqual(config.strategy_score.fundamental_weight_f003, 0.50)
        self.assertEqual(config.strategy_score.fundamental_weight_f004, 0.05)
        self.assertEqual(config.strategy_score.fundamental_weight_f005, 0.05)
        self.assertEqual(config.strategy_score.fundamental_weight_f006, 0.15)
        self.assertEqual(config.screener.min_total_score, 65.0)
        self.assertEqual(config.screener.max_double_top_confidence, 60.0)
        self.assertEqual(config.screener.score_id, "S002_StrategyScore")
        self.assertTrue(config.screener.apply_market_regime_adjustment)
        self.assertTrue(config.market_context.enabled)
        self.assertEqual(config.market_context.benchmark_symbol, "1306.T")
        self.assertEqual(config.market_context.min_universe_size, 20)
        self.assertEqual(config.market_context.min_sector_size, 5)
        self.assertEqual(config.market_context.breadth_severe_bearish_threshold, 0.35)
        self.assertEqual(config.market_context.breakout_bearish_threshold_delta, 8.0)
        self.assertEqual(config.market_context.breakout_bearish_score_penalty, 6.0)
        self.assertEqual(config.market_context.pullback_rs_positive_factor, 0.3)
        self.assertEqual(config.market_context.rs_adjustment_max, 4.5)
        self.assertEqual(config.market_context.sector_momentum_adjustment_max, 2.5)
        self.assertEqual(config.market_context.relative_valuation_adjustment_max, 5.5)
        self.assertEqual(config.market_context.total_adjustment_cap, 10.0)
        self.assertEqual(config.ranking.top_n, 20)
        self.assertEqual(config.ranking.strategy_top_n, 10)
        self.assertEqual(config.output.output_dir, "./output")
        self.assertEqual(config.output.formats, ["json", "markdown"])
        self.assertEqual(config.evaluation.horizons, [5, 20, 60])
        self.assertEqual(config.evaluation.entry_price_mode, "signal_close")

    def test_load_default_when_config_file_missing(self):
        """config_path=None で参照先ファイルが存在しない場合はデフォルト AtlasScreeningConfig を返す"""
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = str(Path(tmpdir) / "nonexistent.yaml")
            with patch(
                "src.config.screening_config.Settings",
                return_value=Settings(SCREENING_CONFIG_PATH=missing_path),
            ):
                config = load_screening_config(None)

        self.assertEqual(config, AtlasScreeningConfig())

    def test_explicit_missing_path_raises_file_not_found(self):
        """明示的に存在しない config_path を指定した場合は FileNotFoundError を送出する"""
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "missing_config.yaml"
            with self.assertRaises(FileNotFoundError):
                load_screening_config(missing_path)

    def test_partial_yaml_merges_with_defaults(self):
        """一部セクション・一部キーのみ記載したYAMLがデフォルト値とマージされることを確認する"""
        partial_yaml = """
pre_screening:
  min_roe: 12.5
strategy_score:
  min_entry_score: 72.0
screener:
ranking:
  top_n: 5
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "partial.yaml"
            yaml_path.write_text(partial_yaml, encoding="utf-8")

            config = load_screening_config(yaml_path)

        # 上書きされた値
        self.assertEqual(config.pre_screening.min_roe, 12.5)
        self.assertEqual(config.strategy_score.min_entry_score, 72.0)
        self.assertEqual(config.ranking.top_n, 5)

        # 未指定項目はデフォルト値のまま
        self.assertEqual(config.pre_screening.target_markets, ["プライム", "スタンダード"])
        self.assertEqual(config.pre_screening.liquidity_lookback_days, 20)
        self.assertEqual(config.strategy_score.min_trend_env_score, 50.0)
        self.assertEqual(config.screener.min_total_score, 60.0)
        self.assertEqual(config.ranking.strategy_top_n, 10)
        self.assertEqual(config.output, OutputConfig())
        self.assertIsInstance(config.ranking, RankingConfig)

    def test_score_manager_injects_strategy_score_config(self):
        """ScoreManager / ScoreRegistry へ StrategyScoreConfig が注入されて計算に反映される"""
        manager = ScoreManager()
        fs = FeatureSetModel(
            symbol="7203.T",
            date=date(2025, 3, 1),
            results=[
                FeatureResultModel(feature_id="M001_MAAlignmentScore", feature_name="MA", score=70.0, raw_value=70.0),
                FeatureResultModel(feature_id="T001_TrendStrengthScore", feature_name="Trend", score=70.0, raw_value=70.0),
                FeatureResultModel(feature_id="P001_PullbackScore", feature_name="Pullback", score=75.0, raw_value=75.0),
                FeatureResultModel(feature_id="P002_BreakoutScore", feature_name="Breakout", score=40.0, raw_value=40.0),
                FeatureResultModel(feature_id="O001_MomentumScore", feature_name="Momentum", score=70.0, raw_value=70.0),
            ],
        )

        # デフォルト設定では trend_env=70 >= 50 で通過し pullback になり得る
        default_res = manager.calculate_scores(
            [fs], [], score_ids=["S002_StrategyScore"]
        )[0]
        self.assertEqual(default_res.strategy_type, "pullback")

        # 注入設定で min_trend_env_score=80.0 に引き上げると第1関門未達で watch になる
        strict_cfg = StrategyScoreConfig(min_trend_env_score=80.0)
        strict_res = manager.calculate_scores(
            [fs],
            [],
            score_ids=["S002_StrategyScore"],
            score_configs={"S002_StrategyScore": strict_cfg},
        )[0]
        self.assertEqual(strict_res.strategy_type, "watch")
        self.assertFalse(strict_res.metadata["gate1_passed"])

    def test_evaluation_config_validation_and_normalization(self):
        """EvaluationConfig が horizons の重複排除・昇順化および不正値拒否を行う"""
        cfg = EvaluationConfig(horizons=[60, 5, 20, 5], entry_price_mode="next_open")
        self.assertEqual(cfg.horizons, [5, 20, 60])
        self.assertEqual(cfg.entry_price_mode, "next_open")

        with self.assertRaises(ValidationError):
            EvaluationConfig(horizons=[])
        with self.assertRaises(ValidationError):
            EvaluationConfig(horizons=[5, 0])
        with self.assertRaises(ValidationError):
            EvaluationConfig(horizons=[5, -10])
        with self.assertRaises(ValidationError):
            EvaluationConfig(horizons=[True, 5])
        with self.assertRaises(ValidationError):
            EvaluationConfig(entry_price_mode="invalid_mode")

    def test_ranking_config_strict_date_match_default_and_override(self):
        """RankingConfig.strict_date_match のデフォルト True と YAML 上書きを検証"""
        default_cfg = load_screening_config()
        self.assertTrue(default_cfg.ranking.strict_date_match)

        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "custom.yaml"
            yaml_path.write_text("ranking:\n  strict_date_match: false\n", encoding="utf-8")
            custom_cfg = load_screening_config(yaml_path)
            self.assertFalse(custom_cfg.ranking.strict_date_match)

    def test_load_gemini_preset_yaml(self):
        """config/screening_gemini.yaml が運用プリセット要件どおりにロードできる"""
        gemini_yaml = Path("config/screening_gemini.yaml")
        self.assertTrue(gemini_yaml.exists())
        cfg = load_screening_config(gemini_yaml)
        self.assertEqual(cfg.pre_screening.target_markets, ["プライム"])
        self.assertEqual(cfg.pre_screening.min_avg_trading_value, 3_000_000_000.0)
        self.assertEqual(cfg.pre_screening.max_close, 5000.0)
        self.assertIn("gemini", cfg.output.formats)
        self.assertEqual(cfg.output.gemini_brief_latest_name, "gemini_brief_latest.md")


if __name__ == "__main__":
    unittest.main()
