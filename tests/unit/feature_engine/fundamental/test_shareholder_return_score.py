import unittest
from datetime import date, timedelta
from types import SimpleNamespace

import src.feature_engine  # レジストリ登録を確認するためパッケージをインポート
from src.feature_engine.features.fundamental.shareholder_return_score import ShareholderReturnScore
from src.feature_engine.registry import feature_registry
from src.model.data_models import FinancialModel, IndicatorSetModel, OhlcvModel


class TestShareholderReturnScore(unittest.TestCase):
    def setUp(self):
        self.feature = ShareholderReturnScore()
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

    def test_feature_properties_and_registry(self):
        self.assertEqual(self.feature.feature_id, "F006_ShareholderReturnScore")
        self.assertEqual(self.feature.feature_name, "株主還元スコア")
        self.assertEqual(self.feature.feature_category, "Fundamental")
        registered_ids = [f["feature_id"] for f in feature_registry.list_features()]
        self.assertIn("F006_ShareholderReturnScore", registered_ids)

    def test_high_shareholder_return_scores_100(self):
        # 連続増配5年、総還元性向45%、積極的自社株買い(純利益の30%+直近3期全回)、DOE 6% -> 100点
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            net_profit=1000.0,
            dividend_per_share=120.0,
            total_dividends=150.0,
            share_buyback=300.0,
            payout_ratio=15.0,
            total_payout_ratio=45.0,
            doe=6.0,
            consecutive_dividend_increase_years=5,
            consecutive_non_decrease_years=5,
            buyback_count_3y=3,
        )
        res = self.feature.calculate(self.ohlcv_data, self.indicator_data, financial_data)[0]
        self.assertAlmostEqual(res.score, 100.0)
        self.assertAlmostEqual(res.metadata["available_weight"], 100.0)
        self.assertEqual(res.metadata["consecutive_dividend_increase_years"], 5)
        self.assertEqual(res.metadata["buyback_count_3y"], 3)

    def test_over_payout_takoashi_and_deficit_dividend_penalized(self):
        # タコ足配当 (>100%) および赤字配当 (<0%) は適正帯 (30〜60%) より低く評価される
        base = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            dividend_per_share=50.0,
            total_payout_ratio=45.0,
        )
        takoashi_120 = base.model_copy(update={"total_payout_ratio": 120.0})
        takoashi_160 = base.model_copy(update={"total_payout_ratio": 160.0})
        deficit = base.model_copy(update={"total_payout_ratio": -25.0})

        s_base = self.feature.calculate(self.ohlcv_data, self.indicator_data, base)[0].score
        s_120 = self.feature.calculate(self.ohlcv_data, self.indicator_data, takoashi_120)[0].score
        s_160 = self.feature.calculate(self.ohlcv_data, self.indicator_data, takoashi_160)[0].score
        s_def = self.feature.calculate(self.ohlcv_data, self.indicator_data, deficit)[0].score

        self.assertGreater(s_base, s_120)
        self.assertGreater(s_120, s_160)
        self.assertEqual(s_160, s_def)  # 150%以上と赤字配当は軸2がともに0.0点

    def test_no_buyback_and_historical_buyback_scoring(self):
        # 関連フィールドありで自社株買い無し -> 軸3は 4.0点
        fin_no_bb = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            dividend_per_share=50.0,  # 履歴なし配当あり -> 17.5 / 35
            payout_ratio=40.0,  # 30.0 / 30
        )
        res_no_bb = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_no_bb)[0]
        # (17.5 + 30.0 + 4.0) / 85.0 * 100 = 60.588235...
        self.assertAlmostEqual(res_no_bb.metadata["available_weight"], 85.0)
        self.assertAlmostEqual(res_no_bb.score, (51.5 / 85.0) * 100.0)

        # 今期は無しだが直近3期に2回自社株買い実施
        fin_hist_bb = fin_no_bb.model_copy(update={"buyback_count_3y": 2})
        res_hist_bb = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_hist_bb)[0]
        self.assertGreater(res_hist_bb.score, res_no_bb.score)

        # net_profit 欠損かつ buyback_count_3y 欠損で今期自社株買いあり -> 10 + 2.5 + 2.0 = 14.5
        fin_curr_bb_only = fin_no_bb.model_copy(update={"share_buyback": 100.0})
        res_curr_bb = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_curr_bb_only)[0]
        self.assertAlmostEqual(res_curr_bb.score, ((17.5 + 30.0 + 14.5) / 85.0) * 100.0)

    def test_dividend_momentum_variants_and_zero_dividend(self):
        # 連続非減配5年 (連続増配0年) vs 履歴なし無配
        fin_non_dec = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            consecutive_dividend_increase_years=0,
            consecutive_non_decrease_years=5,
        )
        res_non_dec = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_non_dec)[0]
        # 軸1: 18.0, 軸3: 4.0, weight=55.0 -> 22.0 / 55.0 * 100 = 40.0
        self.assertAlmostEqual(res_non_dec.score, 40.0)

        fin_zero_div = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            dividend_per_share=0.0,
        )
        res_zero_div = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_zero_div)[0]
        # 軸1: 3.0, 軸3: 4.0, weight=55.0 -> 7.0 / 55.0 * 100
        self.assertAlmostEqual(res_zero_div.score, (7.0 / 55.0) * 100.0)

    def test_doe_evaluation(self):
        # DOE 単独 + 自社株買い無し軸(20)での評価推移
        fin_doe_neg = FinancialModel(symbol=self.symbol, fiscal_date=date(2025, 3, 31), doe=-1.0)
        fin_doe_mid = FinancialModel(symbol=self.symbol, fiscal_date=date(2025, 3, 31), doe=2.5)
        fin_doe_ideal = FinancialModel(symbol=self.symbol, fiscal_date=date(2025, 3, 31), doe=6.0)
        fin_doe_high = FinancialModel(symbol=self.symbol, fiscal_date=date(2025, 3, 31), doe=15.0)

        s_neg = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_doe_neg)[0].score
        s_mid = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_doe_mid)[0].score
        s_ideal = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_doe_ideal)[0].score
        s_high = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_doe_high)[0].score

        self.assertLess(s_neg, s_mid)
        self.assertLess(s_mid, s_ideal)
        self.assertGreater(s_ideal, s_high)

    def test_missing_all_return_fields_returns_neutral_50(self):
        self.assertEqual(self.feature.calculate(self.ohlcv_data, [], None), [])
        res_none = self.feature.calculate(self.ohlcv_data, self.indicator_data, None)[0]
        self.assertAlmostEqual(res_none.score, 50.0)

        # net_profit だけ存在しても、株主還元関連9フィールドが全て None なら中立 50.0
        fin_no_return = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            net_profit=500.0,
        )
        res_no_return = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_no_return)[0]
        self.assertAlmostEqual(res_no_return.score, 50.0)
        self.assertAlmostEqual(res_no_return.metadata["available_weight"], 0.0)

    def test_nan_and_inf_guards(self):
        fin_all_nan = SimpleNamespace(
            dividend_per_share=float("nan"),
            total_dividends=float("inf"),
            share_buyback=float("-inf"),
            payout_ratio=float("nan"),
            total_payout_ratio=float("inf"),
            doe=float("nan"),
            consecutive_dividend_increase_years=float("nan"),
            consecutive_non_decrease_years=float("inf"),
            buyback_count_3y=True,  # bool も弾かれること
            net_profit=1000.0,
        )
        res = self.feature.calculate(self.ohlcv_data, self.indicator_data, fin_all_nan)[0]
        self.assertAlmostEqual(res.score, 50.0)
        self.assertAlmostEqual(res.metadata["available_weight"], 0.0)
        self.assertIsNone(res.metadata["dividend_per_share"])
        self.assertIsNone(res.metadata["buyback_count_3y"])

    def test_target_indices_matches_full_calculation(self):
        financial_data = FinancialModel(
            symbol=self.symbol,
            fiscal_date=date(2025, 3, 31),
            net_profit=1000.0,
            dividend_per_share=80.0,
            payout_ratio=35.0,
            doe=5.0,
            consecutive_dividend_increase_years=3,
            buyback_count_3y=1,
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
