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
        """プロジェクトルートの config/screening.yaml を読み込み、既定値と一致することを確認する"""
        project_yaml = (
            Path(__file__).resolve().parents[3] / "config" / "screening.yaml"
        )
        self.assertTrue(project_yaml.exists())

        config = load_screening_config(project_yaml)
        self.assertIsInstance(config, AtlasScreeningConfig)
        self.assertEqual(config.pre_screening.target_markets, ["プライム", "スタンダード"])
        self.assertEqual(config.pre_screening.min_revenue, 10_000_000_000.0)
        self.assertEqual(config.strategy_score.min_entry_score, 60.0)
        self.assertEqual(config.screener.min_total_score, 60.0)
        self.assertEqual(config.screener.score_id, "S002_StrategyScore")
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


if __name__ == "__main__":
    unittest.main()
