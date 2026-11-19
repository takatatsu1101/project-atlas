import unittest
from datetime import date, timedelta

from src.feature_engine.features.fundamental.financial_health_score import FinancialHealthScore
from src.model.data_models import FinancialModel, IndicatorSetModel, OhlcvModel


class TestFinancialHealthScore(unittest.TestCase):
    def setUp(self):
        self.feature = FinancialHealthScore()
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
        self.assertEqual(self.feature.feature_id, "F004_FinancialHealthScore")
        self.assertEqual(self.feature.feature_name, "財務健全性スコア")
        self.assertEqual(self.feature.feature_category, "Fundamental")

    def test_high_quality_balance_sheet_scores_100(self):
        # 自己資本比率 >= 75%、ネットキャッシュ >= 40%、利益剰余金比率 >= 60%、無借金(D/E=0) -> 100点
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            total_assets=1000.0,
            equity_ratio=80.0,
            cash_and_equivalents=500.0,
            short_term_debt=0.0,
            long_term_debt=0.0,
            retained_earnings=650.0,
            shareholders_equity=800.0,
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        self.assertEqual(len(results), 4)
        res = results[0]
        self.assertAlmostEqual(res.score, 100.0)
        self.assertAlmostEqual(res.metadata["available_weight"], 100.0)
        self.assertAlmostEqual(res.metadata["net_cash_ratio"], 0.50)
        self.assertAlmostEqual(res.metadata["retained_earnings_ratio"], 0.65)
        self.assertAlmostEqual(res.metadata["debt_to_equity"], 0.0)

    def test_unhealthy_insolvent_and_net_debt_scores_zero(self):
        # 自己資本比率 <= 10%、ネットデット <= -40%、利益剰余金大幅赤字、債務超過 -> 0点
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            total_assets=1000.0,
            equity_ratio=5.0,
            cash_and_equivalents=50.0,
            short_term_debt=300.0,
            long_term_debt=300.0,
            retained_earnings=-200.0,
            shareholders_equity=-100.0,
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        res = results[0]
        self.assertAlmostEqual(res.score, 0.0)
        self.assertIsNone(res.metadata["debt_to_equity"])
        self.assertAlmostEqual(res.metadata["available_weight"], 100.0)

    def test_insolvency_zero_subscore_not_treated_as_falsy(self):
        # de_sub == 0.0（債務超過）のみ取得可能でも None 扱いにならず 0.0 点（重み 20.0）になること
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            short_term_debt=100.0,
            shareholders_equity=0.0,
            net_assets=500.0,  # shareholders_equity=0.0 のため net_assets へフォールバックしない
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        res = results[0]
        self.assertAlmostEqual(res.score, 0.0)
        self.assertIsNone(res.metadata["debt_to_equity"])
        self.assertAlmostEqual(res.metadata["available_weight"], 20.0)

    def test_net_assets_fallback_when_shareholders_equity_missing(self):
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            long_term_debt=200.0,
            net_assets=400.0,  # D/E = 0.5 -> linear_scale(0.5, 2.0, 0.0, 0.0, 1.0) = 0.75
        )
        results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        res = results[0]
        self.assertAlmostEqual(res.metadata["debt_to_equity"], 0.5)
        self.assertAlmostEqual(res.score, 75.0)
        self.assertAlmostEqual(res.metadata["available_weight"], 20.0)

    def test_both_debts_none_prevents_zero_debt_assumption_and_rebalances_weight(self):
        # トヨタ・銀行等の借入金両方 None の銘柄では、有利子負債 0 とみなさずネットキャッシュ比率を欠損扱いにする
        fin_no_debt_cols = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            total_assets=1000.0,
            equity_ratio=42.5,  # 40点満点中 20.0点（ちょうど50%水準）
            cash_and_equivalents=500.0,
            short_term_debt=None,
            long_term_debt=None,
            retained_earnings=250.0,  # ratio=0.25 -> (0.35/0.70)=0.5 -> 20点満点中 10.0点
        )
        res = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_no_debt_cols)[0]
        self.assertIsNone(res.metadata["interest_bearing_debt"])
        self.assertIsNone(res.metadata["net_cash_ratio"])
        self.assertIsNone(res.metadata["debt_to_equity"])
        self.assertAlmostEqual(res.metadata["available_weight"], 60.0)
        # (20.0 + 10.0) / 60.0 * 100 = 50.0（もし借入金0扱いならネットキャッシュ50%で40点が入り 70点以上へ誤高評価される）
        self.assertAlmostEqual(res.score, 50.0)

        # 片方だけでも 0.0 が明示されていれば無借金として算出される
        fin_explicit_zero_debt = fin_no_debt_cols.model_copy(update={"short_term_debt": 0.0})
        res_explicit = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_explicit_zero_debt)[0]
        self.assertAlmostEqual(res_explicit.metadata["interest_bearing_debt"], 0.0)
        self.assertAlmostEqual(res_explicit.metadata["net_cash_ratio"], 0.50)
        self.assertGreater(res_explicit.score, res.score)

    def test_legacy_fallback_only_when_new_axes_unavailable(self):
        # 新軸全欠損かつレガシー4項目あり -> レガシー簡易判定（100点）
        fin_legacy_ok = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            eps=50.0,
            bps=1000.0,
            operating_profit=100.0,
            net_profit=50.0,
        )
        res_ok = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_legacy_ok)[0]
        self.assertAlmostEqual(res_ok.score, 100.0)
        self.assertAlmostEqual(res_ok.metadata["available_weight"], 0.0)

        # レガシー赤字・債務超過（0点）
        fin_legacy_bad = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            eps=10.0,
            bps=-10.0,
            operating_profit=-50.0,
            net_profit=-80.0,
        )
        res_bad = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_legacy_bad)[0]
        self.assertAlmostEqual(res_bad.score, 0.0)

        # レガシー項目の一部欠損 -> 中立 50.0
        fin_legacy_partial = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            eps=50.0,
            bps=1000.0,
            operating_profit=100.0,
            net_profit=None,
        )
        res_partial = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_legacy_partial)[0]
        self.assertAlmostEqual(res_partial.score, 50.0)

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
            equity_ratio=float("nan"),
            total_assets=float("inf"),
            cash_and_equivalents=100.0,
            short_term_debt=float("nan"),
            long_term_debt=float("-inf"),
            retained_earnings=float("nan"),
            shareholders_equity=float("inf"),
        )
        res = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_nan)[0]
        self.assertAlmostEqual(res.score, 50.0)
        self.assertAlmostEqual(res.metadata["available_weight"], 0.0)
        self.assertIsNone(res.metadata["equity_ratio"])
        self.assertIsNone(res.metadata["interest_bearing_debt"])

    def test_target_indices_matches_full_calculation(self):
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            total_assets=1000.0,
            equity_ratio=55.0,
            cash_and_equivalents=300.0,
            short_term_debt=50.0,
            long_term_debt=100.0,
            retained_earnings=400.0,
            shareholders_equity=550.0,
        )
        full_results = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)
        partial_results = self.feature.calculate(
            self.ohlcv_data, self.indicator_data, financial_data, target_indices=[1, -1]
        )
        self.assertEqual([r.date for r in partial_results], [full_results[1].date, full_results[-1].date])
        self.assertAlmostEqual(partial_results[0].score, full_results[1].score)
        self.assertAlmostEqual(partial_results[1].score, full_results[-1].score)
        self.assertEqual(partial_results[1].metadata, full_results[-1].metadata)


if __name__ == "__main__":
    unittest.main()
