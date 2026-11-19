import unittest
from datetime import date, datetime
from src.screener.screener import Screener, ScreeningCriteria
from src.model.data_models import MarketContextModel, ScoreResultModel, SymbolMarketMetricsModel


class TestScreenerAndRanking(unittest.TestCase):
    def _make_score(
        self,
        symbol: str,
        dt: date = date(2026, 1, 5),
        score_id: str = "S002_StrategyScore",
        total_score: float = 75.0,
        strategy_type: str = "pullback",
        trend_env_score: float = 70.0,
        pullback_score: float = 75.0,
        breakout_score: float = 50.0,
        fundamental_score: float = 65.0,
        gate1_passed: bool = True,
        include_gate1_meta: bool = True,
        double_top_confidence: float = 0.0,
    ) -> ScoreResultModel:
        metadata = {"double_top_confidence": double_top_confidence}
        if include_gate1_meta:
            metadata["gate1_passed"] = gate1_passed
        return ScoreResultModel(
            symbol=symbol,
            date=dt,
            score_id=score_id,
            total_score=total_score,
            strategy_type=strategy_type,
            sub_scores={
                "trend_env_score": trend_env_score,
                "pullback_strategy_score": pullback_score,
                "breakout_strategy_score": breakout_score,
                "fundamental_score": fundamental_score,
            },
            metadata=metadata,
        )

    def test_screener_filtering(self):
        screener = Screener()
        results = [
            ScoreResultModel(symbol="7203.T", date=datetime(2026, 1, 1), total_score=85.0, sub_scores={}, metadata={}),
            ScoreResultModel(symbol="9984.T", date=datetime(2026, 1, 1), total_score=55.0, sub_scores={}, metadata={}),
            ScoreResultModel(symbol="6758.T", date=datetime(2026, 1, 1), total_score=70.0, sub_scores={}, metadata={}),
        ]

        # 閾値 70 以上でフィルタリング（レガシー dict 後方互換）
        filtered = screener.apply_screener(results, {"min_total_score": 70.0})
        self.assertEqual(len(filtered), 2)
        symbols = [r.symbol for r in filtered]
        self.assertIn("7203.T", symbols)
        self.assertIn("6758.T", symbols)
        self.assertNotIn("9984.T", symbols)

    def test_criteria_excludes_gate1_failed_and_watch(self):
        """ScreeningCriteria で第1関門失敗および watch 銘柄を除外する"""
        screener = Screener()
        results = [
            self._make_score("7203.T", total_score=80.0, strategy_type="pullback", gate1_passed=True),
            self._make_score("9984.T", total_score=85.0, strategy_type="pullback", gate1_passed=False),
            self._make_score("6758.T", total_score=65.0, strategy_type="watch", gate1_passed=True),
            # gate1_passed がメタデータに無く trend_env_score が閾値未満の場合も除外
            self._make_score(
                "8035.T",
                total_score=75.0,
                strategy_type="breakout",
                trend_env_score=45.0,
                include_gate1_meta=False,
            ),
        ]

        filtered = screener.apply_screener(results, ScreeningCriteria())
        self.assertEqual([r.symbol for r in filtered], ["7203.T"])

    def test_criteria_allowed_strategies_and_thresholds(self):
        """戦略タイプ・各種スコア閾値・ダブルトップ信頼度上限でフィルタリングできる"""
        screener = Screener()
        results = [
            self._make_score(
                "1001.T",
                strategy_type="pullback",
                total_score=72.0,
                pullback_score=72.0,
                fundamental_score=60.0,
                double_top_confidence=30.0,
            ),
            self._make_score(
                "1002.T",
                strategy_type="breakout",
                total_score=78.0,
                breakout_score=78.0,
                fundamental_score=60.0,
                double_top_confidence=20.0,
            ),
            self._make_score(
                "1003.T",
                strategy_type="pullback",
                total_score=75.0,
                pullback_score=75.0,
                fundamental_score=40.0,  # ファンダ下限未満
            ),
            self._make_score(
                "1004.T",
                strategy_type="pullback",
                total_score=75.0,
                pullback_score=75.0,
                fundamental_score=70.0,
                double_top_confidence=70.0,  # ダブルトップ上限以上
            ),
        ]

        criteria = ScreeningCriteria(
            allowed_strategies=["pullback"],
            min_pullback_strategy_score=70.0,
            min_fundamental_score=55.0,
            max_double_top_confidence=70.0,
        )
        filtered = screener.apply_screener(results, criteria)
        self.assertEqual([r.symbol for r in filtered], ["1001.T"])

    def test_criteria_latest_only_per_symbol_and_score_id(self):
        """score_id 絞り込みと銘柄別最新日抽出（最新日が条件未達なら過去日を拾わない）"""
        screener = Screener()
        results = [
            # S001 は除外対象
            self._make_score("7203.T", dt=date(2026, 1, 10), score_id="S001_OverallScore", total_score=95.0),
            # 7203.T の過去日（高スコア）と最新日（低スコア -> 最新日基準で除外されるべき）
            self._make_score("7203.T", dt=date(2026, 1, 8), total_score=85.0),
            self._make_score("7203.T", dt=date(2026, 1, 10), total_score=45.0, strategy_type="watch"),
            # 6758.T の過去日（低スコア）と最新日（高スコア -> 抽出されるべき）
            self._make_score("6758.T", dt=date(2026, 1, 8), total_score=40.0, strategy_type="watch"),
            self._make_score("6758.T", dt=date(2026, 1, 10), total_score=82.0, strategy_type="breakout"),
        ]

        filtered = screener.apply_screener(results, ScreeningCriteria(latest_only_per_symbol=True))
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].symbol, "6758.T")
        self.assertEqual(filtered[0].date, date(2026, 1, 10))

    def test_strategy_specific_subscore_thresholds_only_apply_to_matching_strategy(self):
        """min_pullback_strategy_score / min_breakout_strategy_score は該当戦略のみに適用される"""
        screener = Screener()
        results = [
            # breakout 銘柄は pullback_score が低くても除外されない
            self._make_score(
                "2001.T",
                strategy_type="breakout",
                total_score=80.0,
                pullback_score=35.0,
                breakout_score=80.0,
            ),
            # breakout 銘柄で breakout_score が閾値未満 -> 除外
            self._make_score(
                "2002.T",
                strategy_type="breakout",
                total_score=72.0,
                pullback_score=85.0,
                breakout_score=72.0,
            ),
            # pullback 銘柄で pullback_score >= 70 -> breakout_score が低くても残る
            self._make_score(
                "1001.T",
                strategy_type="pullback",
                total_score=75.0,
                pullback_score=75.0,
                breakout_score=30.0,
            ),
            # pullback 銘柄で pullback_score < 70 -> 除外
            self._make_score(
                "1002.T",
                strategy_type="pullback",
                total_score=65.0,
                pullback_score=65.0,
                breakout_score=85.0,
            ),
        ]

        criteria = ScreeningCriteria(
            allowed_strategies=["pullback", "breakout"],
            min_pullback_strategy_score=70.0,
            min_breakout_strategy_score=75.0,
        )
        filtered = screener.apply_screener(results, criteria)
        self.assertEqual([r.symbol for r in filtered], ["2001.T", "1001.T"])

    def test_bearish_market_regime_raises_breakout_threshold_without_double_counting(self):
        """bearish 地合い時にブレイクアウト閾値のみが動的引き上げされ、metadata との二重加算も起きない"""
        screener = Screener()
        dt = date(2026, 3, 2)

        bo_70 = self._make_score(
            "3001.T",
            dt=dt,
            strategy_type="breakout",
            total_score=70.0,
            breakout_score=70.0,
        )
        bo_70.metadata["breakout_threshold_delta"] = 8.0

        bo_74 = self._make_score(
            "3002.T",
            dt=dt,
            strategy_type="breakout",
            total_score=74.0,
            breakout_score=74.0,
        )
        bo_74.metadata["breakout_threshold_delta"] = 8.0

        pb_66 = self._make_score(
            "3003.T",
            dt=dt,
            strategy_type="pullback",
            total_score=66.0,
            pullback_score=66.0,
        )
        pb_66.metadata["breakout_threshold_delta"] = 8.0

        bear_ctx = MarketContextModel(
            as_of_date=dt,
            is_active=True,
            universe_size=50,
            breadth_ratio=0.28,
            regime="bearish",
            breakout_threshold_delta=8.0,
            symbol_metrics={
                sym: SymbolMarketMetricsModel(symbol=sym, bar_date=dt)
                for sym in ("3001.T", "3002.T", "3003.T")
            },
        )
        criteria = ScreeningCriteria(min_total_score=65.0)
        # 65.0 + 8.0 = 73.0 が有効閾値（二重加算なら 81.0 になり 74.0 が落ちてしまう）
        filtered = screener.apply_screener(
            [bo_70, bo_74, pb_66], criteria, market_context=bear_ctx
        )
        self.assertEqual([r.symbol for r in filtered], ["3002.T", "3003.T"])

        # market_context 省略時でも metadata["breakout_threshold_delta"] で同様に機能
        filtered_meta = screener.apply_screener([bo_70, bo_74, pb_66], criteria)
        self.assertEqual([r.symbol for r in filtered_meta], ["3002.T", "3003.T"])

        # min_breakout_strategy_score 指定時も 64 + 8 = 72 となり 70 は除外、74 は通過
        criteria_bo = ScreeningCriteria(
            min_total_score=60.0,
            min_breakout_strategy_score=64.0,
        )
        filtered_bo_sub = screener.apply_screener(
            [bo_70, bo_74], criteria_bo, market_context=bear_ctx
        )
        self.assertEqual([r.symbol for r in filtered_bo_sub], ["3002.T"])

        # apply_market_regime_adjustment=False なら通常閾値 65.0 で通過
        criteria_disabled = ScreeningCriteria(
            min_total_score=65.0,
            apply_market_regime_adjustment=False,
        )
        filtered_disabled = screener.apply_screener(
            [bo_70, bo_74, pb_66], criteria_disabled, market_context=bear_ctx
        )
        self.assertEqual([r.symbol for r in filtered_disabled], ["3001.T", "3002.T", "3003.T"])

        # sym_ctx.bar_date=None かつ market_context.as_of_date != result.date なら過去日に誤適用されない
        past_bo_70 = self._make_score(
            "3004.T",
            dt=date(2026, 2, 20),
            strategy_type="breakout",
            total_score=70.0,
            breakout_score=70.0,
        )
        none_bar_ctx = MarketContextModel(
            as_of_date=date(2026, 3, 2),
            is_active=True,
            universe_size=50,
            regime="bearish",
            breakout_threshold_delta=8.0,
            symbol_metrics={
                "3004.T": SymbolMarketMetricsModel(symbol="3004.T", bar_date=None)
            },
        )
        filtered_mismatch = screener.apply_screener(
            [past_bo_70], criteria, market_context=none_bar_ctx
        )
        self.assertEqual([r.symbol for r in filtered_mismatch], ["3004.T"])


if __name__ == "__main__":
    unittest.main()
