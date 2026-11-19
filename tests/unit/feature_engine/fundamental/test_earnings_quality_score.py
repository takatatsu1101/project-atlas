import unittest
from datetime import date, timedelta

from src.feature_engine.features.fundamental.earnings_quality_score import EarningsQualityScore
from src.model.data_models import FinancialModel, IndicatorSetModel, OhlcvModel


class TestEarningsQualityScore(unittest.TestCase):
    def setUp(self):
        self.feature = EarningsQualityScore()
        self.symbol = "TEST"
        self.ohlcv_data = [
            OhlcvModel(
                symbol=self.symbol,
                date=date(2025, 1, 1) + timedelta(days=i),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=100,
            )
            for i in range(4)
        ]
        self.indicator_data = [
            IndicatorSetModel(symbol=self.symbol, date=bar.date, indicators={})
            for bar in self.ohlcv_data
        ]

    def test_feature_properties(self):
        self.assertEqual(self.feature.feature_id, "F005_EarningsQualityScore")
        self.assertEqual(self.feature.feature_name, "利益の質スコア")
        self.assertEqual(self.feature.feature_category, "Fundamental")

    def test_high_quality_cf_and_profits_scores_100(self):
        # 全5軸が満点水準 -> 100.0
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            revenue=1000.0,
            total_assets=1000.0,
            operating_profit=200.0,
            net_profit=140.0,  # 0.70（実効税率基準 0.60〜0.80 帯）
            roe=14.0,
            roa=8.0,  # leverage = 1.75（1.0〜2.5 帯）
            operating_cf=220.0,  # 営業CF/純利益 = 1.57 >= 1.2, 営業CFマージン = 22% >= 20%
            free_cash_flow=120.0,  # FCF/総資産 = 0.12 >= 0.10
        )
        res = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)[0]
        self.assertAlmostEqual(res.score, 100.0)
        self.assertAlmostEqual(res.metadata["available_weight"], 100.0)
        self.assertAlmostEqual(res.metadata["net_profit_to_operating_profit_ratio"], 0.70)
        self.assertAlmostEqual(res.metadata["roe_to_roa_ratio"], 1.75)

    def test_accounting_profit_with_negative_operating_cf_low_score(self):
        # 会計上は黒字だが営業CF・FCFとも赤字（黒字倒産リスク）
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            revenue=1000.0,
            total_assets=1000.0,
            operating_profit=100.0,
            net_profit=70.0,
            roe=35.0,
            roa=5.0,  # leverage = 7.0（高レバレッジ）
            operating_cf=-150.0,
            free_cash_flow=-200.0,
        )
        res = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)[0]
        # 軸1(35):0 + 軸2(25):0 + 軸3(15):0 + 軸4(15):15 + 軸5(10):0.67 -> 約 15.67点
        self.assertLess(res.score, 20.0)

    def test_net_profit_to_operating_profit_ideal_band_and_boundaries(self):
        # 本業整合性のみに限定して理想帯 (0.60〜0.80) を検証
        def _score_for_ratio(ratio: float) -> float:
            fin = FinancialModel(
                symbol=self.symbol,
                fiscal_date=date(2025, 3, 31),
                operating_profit=100.0,
                net_profit=100.0 * ratio,
            )
            return self.feature.calculate(self.ohlcv_data, self.indicator_data, fin)[0].score

        score_070 = _score_for_ratio(0.70)
        score_060 = _score_for_ratio(0.60)
        score_080 = _score_for_ratio(0.80)
        score_085 = _score_for_ratio(0.85)
        score_040 = _score_for_ratio(0.40)
        score_120 = _score_for_ratio(1.20)
        score_neg = _score_for_ratio(-0.10)

        self.assertAlmostEqual(score_070, 100.0)
        self.assertAlmostEqual(score_060, 100.0)
        self.assertAlmostEqual(score_080, 100.0)
        self.assertGreater(score_070, score_085)
        self.assertGreater(score_070, score_040)
        self.assertGreater(score_085, score_120)
        self.assertAlmostEqual(score_neg, 0.0)

    def test_ordinary_profit_fallback_for_financial_sector_or_missing_op(self):
        # 営業利益が None または <= 0 のとき経常利益(>0)で代替される
        fin_none_op = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            operating_profit=None,
            ordinary_profit=100.0,
            net_profit=70.0,
        )
        res_none = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_none_op)[0]
        self.assertAlmostEqual(res_none.metadata["net_profit_to_operating_profit_ratio"], 0.70)
        self.assertAlmostEqual(res_none.score, 100.0)

        fin_zero_op = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            operating_profit=0.0,
            ordinary_profit=100.0,
            net_profit=70.0,
        )
        res_zero = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_zero_op)[0]
        self.assertAlmostEqual(res_zero.metadata["net_profit_to_operating_profit_ratio"], 0.70)
        self.assertAlmostEqual(res_zero.score, 100.0)

        # 営業利益が正のときは経常利益より営業利益を優先する
        fin_pos_op = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            operating_profit=100.0,
            ordinary_profit=200.0,
            net_profit=70.0,
        )
        res_pos = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_pos_op)[0]
        self.assertAlmostEqual(res_pos.metadata["net_profit_to_operating_profit_ratio"], 0.70)

    def test_missing_cf_rebalances_weight_to_profit_and_leverage(self):
        # CF 全欠損でも整合性(15)＋レバレッジ(10) = available_weight 25 で再配分される
        fin_no_cf = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            operating_profit=100.0,
            net_profit=70.0,
            roe=15.0,
            roa=10.0,
        )
        res = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_no_cf)[0]
        self.assertAlmostEqual(res.metadata["available_weight"], 25.0)
        self.assertIsNone(res.metadata["operating_cf"])
        self.assertIsNone(res.metadata["free_cash_flow"])
        self.assertAlmostEqual(res.score, 100.0)

    def test_capex_sign_invariant_fcf_and_ocf_margin_fallback(self):
        # capex が負値でも正値でも operating_cf - abs(capex) で同一 FCF が算出される
        fin_neg_capex = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            revenue=1000.0,
            total_assets=1000.0,
            operating_cf=180.0,
            capex=-80.0,
            free_cash_flow=None,
            operating_cf_margin=None,
        )
        fin_pos_capex = fin_neg_capex.model_copy(update={"capex": 80.0})
        res_neg = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_neg_capex)[0]
        res_pos = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_pos_capex)[0]
        self.assertAlmostEqual(res_neg.metadata["free_cash_flow"], 100.0)
        self.assertAlmostEqual(res_neg.metadata["operating_cf_margin"], 18.0)
        self.assertAlmostEqual(res_neg.score, res_pos.score)
        self.assertAlmostEqual(res_neg.metadata["available_weight"], 40.0)

        # total_assets 欠損時は revenue ベース、さらに revenue も無ければ定数判定へフォールバック
        fin_rev_only = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            revenue=1000.0,
            free_cash_flow=150.0,  # fcf_margin = 0.15 -> 25.0/25.0 = 100.0
        )
        res_rev = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_rev_only)[0]
        self.assertIsNone(res_rev.metadata["fcf_to_assets"])
        self.assertAlmostEqual(res_rev.score, 100.0)

        fin_fcf_only = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            free_cash_flow=10.0,  # 20.0 / 25.0 = 80.0
        )
        res_fcf_only = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_fcf_only)[0]
        self.assertAlmostEqual(res_fcf_only.score, 80.0)

    def test_net_profit_non_positive_with_operating_cf(self):
        fin_pos_ocf = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            net_profit=-10.0,
            operating_cf=50.0,
        )
        res_pos = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_pos_ocf)[0]
        # 15.0 / 35.0 * 100
        self.assertAlmostEqual(res_pos.score, (15.0 / 35.0) * 100.0)
        self.assertIsNone(res_pos.metadata["cf_to_net_profit"])

        fin_neg_ocf = fin_pos_ocf.model_copy(update={"operating_cf": -20.0})
        res_neg = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_neg_ocf)[0]
        self.assertAlmostEqual(res_neg.score, 0.0)

    def test_missing_and_empty_data(self):
        self.assertEqual(self.feature.calculate(self.ohlcv_data, [], None), [])
        res_none = self.feature.calculate(self.ohlcv_data, self.indicator_data, None)[0]
        self.assertAlmostEqual(res_none.score, 50.0)

        fin_empty = FinancialModel(symbol=self.symbol, fiscal_date=date(2025, 3, 31))
        res_empty = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_empty)[0]
        self.assertAlmostEqual(res_empty.score, 50.0)
        self.assertAlmostEqual(res_empty.metadata["available_weight"], 0.0)

    def test_nan_and_inf_guards(self):
        fin_nan = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            operating_cf=float("nan"),
            free_cash_flow=float("inf"),
            capex=float("-inf"),
            operating_cf_margin=float("nan"),
            operating_profit=float("inf"),
            net_profit=float("nan"),
            roe=float("nan"),
            roa=float("inf"),
        )
        res = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_nan)[0]
        self.assertAlmostEqual(res.score, 50.0)
        self.assertAlmostEqual(res.metadata["available_weight"], 0.0)

    def test_target_indices_matches_full_calculation(self):
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            revenue=1000.0,
            total_assets=1000.0,
            operating_profit=120.0,
            net_profit=84.0,
            roe=14.0,
            roa=7.0,
            operating_cf=130.0,
            capex=-40.0,
        )
        full_results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        partial_results = self.feature.calculate(
            self.ohlcv_data, self.indicator_data, financial_data, target_indices=[0, -1]
        )
        self.assertEqual([r.date for r in partial_results], [full_results[0].date, full_results[-1].date])
        self.assertAlmostEqual(partial_results[0].score, full_results[0].score)
        self.assertAlmostEqual(partial_results[1].score, full_results[-1].score)
        self.assertEqual(partial_results[1].metadata, full_results[-1].metadata)


if __name__ == "__main__":
    unittest.main()
