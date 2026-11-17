import unittest
from datetime import date
from unittest.mock import patch

from src.model.data_models import (
    FeatureResultModel,
    FeatureSetModel,
    FinancialModel,
    PatternResultModel,
    PatternSetModel,
    ScoreResultModel,
    StockMasterModel,
)
from src.ranking.generator import RankingGenerator


class TestRankingGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = RankingGenerator()
        self.target_date = date(2026, 2, 10)

    def test_full_field_inheritance_and_lookup(self):
        """銘柄マスタ・特徴量・パターン・財務サマリー・価格水準・リスク指標が完全に引き継がれる"""
        score_res = ScoreResultModel(
            symbol="7203.T",
            date=self.target_date,
            score_id="S002_StrategyScore",
            total_score=82.5,
            strategy_type="pullback",
            sub_scores={
                "pullback_strategy_score": 82.5,
                "breakout_strategy_score": 55.0,
                "trend_env_score": 78.0,
                "fundamental_score": 72.0,
            },
            reasons=["第1関門（トレンド環境）を通過しました。", "押し目買い戦略を採用しました。"],
            key_levels={"close": 3050.0, "sma5": 3020.0, "sma25": 2980.0, "sma75": 2850.0},
            risk_metrics={"atr": 45.0, "atr_pct": 1.48, "volume_ratio": 1.35},
            metadata={},
        )

        masters = [
            StockMasterModel(
                code="7203",
                symbol="7203.T",
                name="トヨタ自動車",
                market="プライム",
                sector_33="輸送用機器",
                sector_17="自動車・輸送機",
            )
        ]

        feature_sets = [
            FeatureSetModel(
                symbol="7203.T",
                date=date(2026, 2, 9),
                results=[
                    FeatureResultModel(
                        feature_id="OLD", feature_name="Old", score=10.0, raw_value=10.0
                    )
                ],
            ),
            FeatureSetModel(
                symbol="7203.T",
                date=self.target_date,
                results=[
                    FeatureResultModel(
                        feature_id="M001_MAAlignmentScore",
                        feature_name="MA整列",
                        score=85.0,
                        raw_value=85.0,
                    )
                ],
            ),
        ]

        # pattern_sets は当日一致が無いため symbol の最新結果へフォールバックすることを検証
        pattern_sets = [
            PatternSetModel(
                symbol="7203.T",
                date=date(2026, 2, 8),
                results=[
                    PatternResultModel(
                        pattern_id="P001_Hammer",
                        pattern_name="ハンマー",
                        confidence=75.0,
                    )
                ],
            )
        ]

        # code キーでも検索できることを検証
        financial_map = {
            "7203": FinancialModel(
                symbol="7203.T",
                fiscal_date=date(2025, 3, 31),
                per=11.5,
                pbr=1.1,
                roe=12.4,
                roa=4.2,
                revenue_growth=8.5,
                net_profit_growth=15.0,
                revenue_growth_3y_avg=7.2,
                net_profit_growth_3y_avg=12.1,
                equity_ratio=38.0,
                eps=265.0,
                bps=2770.0,
                revenue=45_000_000_000_000.0,
                operating_profit=5_000_000_000_000.0,
                net_profit=4_200_000_000_000.0,
            )
        }

        ranking = self.generator.generate_ranking(
            [score_res],
            master_map=masters,
            feature_sets=feature_sets,
            pattern_sets=pattern_sets,
            financial_map=financial_map,
        )

        self.assertEqual(len(ranking), 1)
        res = ranking[0]
        self.assertEqual(res.rank, 1)
        self.assertEqual(res.symbol, "7203.T")
        self.assertEqual(res.company_name, "トヨタ自動車")
        self.assertEqual(res.market, "プライム")
        self.assertEqual(res.sector, "輸送用機器")
        self.assertEqual(res.date, self.target_date)
        self.assertEqual(res.strategy_type, "pullback")
        self.assertEqual(res.total_score, 82.5)
        self.assertEqual(res.key_levels["close"], 3050.0)
        self.assertEqual(res.risk_metrics["atr_pct"], 1.48)
        self.assertEqual(len(res.reasons), 2)
        self.assertEqual(res.feature_results[0].feature_id, "M001_MAAlignmentScore")
        self.assertEqual(res.pattern_results[0].pattern_id, "P001_Hammer")
        self.assertEqual(res.financial_summary["per"], 11.5)
        self.assertEqual(res.financial_summary["roe"], 12.4)
        self.assertEqual(res.financial_summary["equity_ratio"], 38.0)
        self.assertIn("トヨタ自動車", res.summary)
        self.assertIn("押し目買い型", res.summary)
        self.assertIn("1位", res.summary)

    def test_deterministic_sorting_tiebreakers(self):
        """同スコア時は trend_env_score 降順 -> symbol 昇順で決定論的に並ぶ"""
        scores = [
            ScoreResultModel(
                symbol="9984.T",
                date=self.target_date,
                total_score=80.0,
                strategy_type="pullback",
                sub_scores={"trend_env_score": 70.0, "pullback_strategy_score": 80.0},
            ),
            ScoreResultModel(
                symbol="6758.T",
                date=self.target_date,
                total_score=80.0,
                strategy_type="pullback",
                sub_scores={"trend_env_score": 70.0, "pullback_strategy_score": 80.0},
            ),
            ScoreResultModel(
                symbol="7203.T",
                date=self.target_date,
                total_score=80.0,
                strategy_type="pullback",
                sub_scores={"trend_env_score": 85.0, "pullback_strategy_score": 80.0},
            ),
        ]

        ranking = self.generator.generate_ranking(scores)
        self.assertEqual([r.symbol for r in ranking], ["7203.T", "6758.T", "9984.T"])
        self.assertEqual([r.rank for r in ranking], [1, 2, 3])

    def test_generate_strategy_rankings_and_top_n(self):
        """総合・押し目買い・ブレイクアウトの各ランキングと top_n 制限が正しく動作する"""
        scores = [
            ScoreResultModel(
                symbol="1001.T",
                date=self.target_date,
                total_score=85.0,
                strategy_type="pullback",
                sub_scores={"pullback_strategy_score": 85.0, "trend_env_score": 75.0},
            ),
            ScoreResultModel(
                symbol="1002.T",
                date=self.target_date,
                total_score=78.0,
                strategy_type="pullback",
                sub_scores={"pullback_strategy_score": 78.0, "trend_env_score": 72.0},
            ),
            ScoreResultModel(
                symbol="2001.T",
                date=self.target_date,
                total_score=90.0,
                strategy_type="breakout",
                sub_scores={"breakout_strategy_score": 90.0, "trend_env_score": 80.0},
            ),
            ScoreResultModel(
                symbol="2002.T",
                date=self.target_date,
                total_score=76.0,
                strategy_type="breakout",
                sub_scores={"breakout_strategy_score": 76.0, "trend_env_score": 70.0},
            ),
        ]

        rankings = self.generator.generate_strategy_rankings(
            scores,
            overall_top_n=3,
            strategy_top_n=1,
        )

        self.assertEqual([r.symbol for r in rankings["overall"]], ["2001.T", "1001.T", "1002.T"])
        self.assertEqual([r.symbol for r in rankings["pullback"]], ["1001.T"])
        self.assertEqual([r.symbol for r in rankings["breakout"]], ["2001.T"])
        self.assertEqual(rankings["pullback"][0].rank, 1)
        self.assertEqual(rankings["breakout"][0].rank, 1)

    def test_feature_and_pattern_code_normalization_fallback(self):
        """feature_sets / pattern_sets の symbol と code の表記揺れを補完し完全一致を優先する"""
        scores = [
            ScoreResultModel(
                symbol="7203.T",
                date=self.target_date,
                total_score=85.0,
                strategy_type="pullback",
                sub_scores={"pullback_strategy_score": 85.0, "trend_env_score": 80.0},
            ),
            ScoreResultModel(
                symbol="6758",
                date=self.target_date,
                total_score=80.0,
                strategy_type="breakout",
                sub_scores={"breakout_strategy_score": 80.0, "trend_env_score": 75.0},
            ),
            ScoreResultModel(
                symbol="9984.T",
                date=self.target_date,
                total_score=75.0,
                strategy_type="pullback",
                sub_scores={"pullback_strategy_score": 75.0, "trend_env_score": 70.0},
            ),
        ]

        feature_sets = [
            # 7203.T に対し code のみの FeatureSet
            FeatureSetModel(
                symbol="7203",
                date=self.target_date,
                results=[
                    FeatureResultModel(
                        feature_id="F_7203_CODE", feature_name="F7203", score=80.0, raw_value=80.0
                    )
                ],
            ),
            # 6758 に対し .T 付き FeatureSet
            FeatureSetModel(
                symbol="6758.T",
                date=self.target_date,
                results=[
                    FeatureResultModel(
                        feature_id="F_6758_TICKER", feature_name="F6758", score=82.0, raw_value=82.0
                    )
                ],
            ),
            # 9984.T に対し code と完全一致の両方がある場合は完全一致を優先
            FeatureSetModel(
                symbol="9984",
                date=self.target_date,
                results=[
                    FeatureResultModel(
                        feature_id="F_9984_CODE", feature_name="F9984Code", score=50.0, raw_value=50.0
                    )
                ],
            ),
            FeatureSetModel(
                symbol="9984.T",
                date=self.target_date,
                results=[
                    FeatureResultModel(
                        feature_id="F_9984_EXACT", feature_name="F9984Exact", score=90.0, raw_value=90.0
                    )
                ],
            ),
        ]

        pattern_sets = [
            PatternSetModel(
                symbol="7203",
                date=self.target_date,
                results=[
                    PatternResultModel(
                        pattern_id="P001_Hammer", pattern_name="ハンマー", confidence=75.0
                    )
                ],
            ),
            PatternSetModel(
                symbol="6758.T",
                date=self.target_date,
                results=[
                    PatternResultModel(
                        pattern_id="R001_DoubleBottom", pattern_name="ダブルボトム", confidence=88.0
                    )
                ],
            ),
        ]

        ranking = self.generator.generate_ranking(
            scores,
            feature_sets=feature_sets,
            pattern_sets=pattern_sets,
        )

        by_symbol = {r.symbol: r for r in ranking}
        self.assertEqual(by_symbol["7203.T"].feature_results[0].feature_id, "F_7203_CODE")
        self.assertEqual(by_symbol["7203.T"].pattern_results[0].pattern_id, "P001_Hammer")
        self.assertEqual(by_symbol["6758"].feature_results[0].feature_id, "F_6758_TICKER")
        self.assertEqual(by_symbol["6758"].pattern_results[0].pattern_id, "R001_DoubleBottom")
        self.assertEqual(by_symbol["9984.T"].feature_results[0].feature_id, "F_9984_EXACT")

    def test_generate_strategy_rankings_builds_lookups_once_and_matches_single_calls(self):
        """generate_strategy_rankings はルックアップ構築を1回のみ行い、個別 generate_ranking と同一結果を返す"""
        scores = [
            ScoreResultModel(
                symbol="7203.T",
                date=self.target_date,
                total_score=85.0,
                strategy_type="pullback",
                sub_scores={"pullback_strategy_score": 85.0, "trend_env_score": 80.0},
            ),
            ScoreResultModel(
                symbol="6758.T",
                date=self.target_date,
                total_score=88.0,
                strategy_type="breakout",
                sub_scores={"breakout_strategy_score": 88.0, "trend_env_score": 82.0},
            ),
        ]
        masters = [
            StockMasterModel(code="7203", symbol="7203.T", name="トヨタ自動車", market="プライム"),
            StockMasterModel(code="6758", symbol="6758.T", name="ソニーグループ", market="プライム"),
        ]
        feature_sets = [
            FeatureSetModel(
                symbol="7203.T",
                date=self.target_date,
                results=[
                    FeatureResultModel(feature_id="F1", feature_name="F1", score=80.0, raw_value=80.0)
                ],
            )
        ]
        pattern_sets = [
            PatternSetModel(
                symbol="6758.T",
                date=self.target_date,
                results=[
                    PatternResultModel(pattern_id="P1", pattern_name="P1", confidence=75.0)
                ],
            )
        ]
        financial_map = {
            "7203.T": FinancialModel(symbol="7203.T", fiscal_date=date(2025, 3, 31), roe=12.0),
            "6758.T": FinancialModel(symbol="6758.T", fiscal_date=date(2025, 3, 31), roe=14.0),
        }

        expected_overall = self.generator.generate_ranking(
            scores,
            master_map=masters,
            feature_sets=feature_sets,
            pattern_sets=pattern_sets,
            financial_map=financial_map,
            strategy_filter=None,
            top_n=2,
        )
        expected_pullback = self.generator.generate_ranking(
            scores,
            master_map=masters,
            feature_sets=feature_sets,
            pattern_sets=pattern_sets,
            financial_map=financial_map,
            strategy_filter="pullback",
            top_n=1,
        )
        expected_breakout = self.generator.generate_ranking(
            scores,
            master_map=masters,
            feature_sets=feature_sets,
            pattern_sets=pattern_sets,
            financial_map=financial_map,
            strategy_filter="breakout",
            top_n=1,
        )

        with patch.object(
            self.generator, "_build_master_lookup", wraps=self.generator._build_master_lookup
        ) as spy_master, patch.object(
            self.generator, "_build_financial_lookup", wraps=self.generator._build_financial_lookup
        ) as spy_fin, patch.object(
            self.generator, "_build_set_lookup", wraps=self.generator._build_set_lookup
        ) as spy_set:
            rankings = self.generator.generate_strategy_rankings(
                scores,
                master_map=masters,
                feature_sets=feature_sets,
                pattern_sets=pattern_sets,
                financial_map=financial_map,
                overall_top_n=2,
                strategy_top_n=1,
            )

        self.assertEqual(spy_master.call_count, 1)
        self.assertEqual(spy_fin.call_count, 1)
        # feature_sets と pattern_sets の2回のみ
        self.assertEqual(spy_set.call_count, 2)

        self.assertEqual(rankings["overall"], expected_overall)
        self.assertEqual(rankings["pullback"], expected_pullback)
        self.assertEqual(rankings["breakout"], expected_breakout)

    def test_generate_strategy_rankings_empty_input_skips_lookups(self):
        """generate_strategy_rankings([]) 空入力時はルックアップ構築が0回で全戦略空リストを返す"""
        with patch.object(
            self.generator, "_build_master_lookup", wraps=self.generator._build_master_lookup
        ) as spy_master, patch.object(
            self.generator, "_build_financial_lookup", wraps=self.generator._build_financial_lookup
        ) as spy_fin, patch.object(
            self.generator, "_build_set_lookup", wraps=self.generator._build_set_lookup
        ) as spy_set:
            rankings = self.generator.generate_strategy_rankings([])

        self.assertEqual(rankings, {"overall": [], "pullback": [], "breakout": []})
        spy_master.assert_not_called()
        spy_fin.assert_not_called()
        spy_set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
