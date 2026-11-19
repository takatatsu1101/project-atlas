import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.evaluator import Evaluator, ForwardReturnEvaluator
from src.model.data_models import (
    AnalysisResultModel,
    BatchBacktestSummaryModel,
    FeatureResultModel,
    OhlcvModel,
)


def _build_candidate(
    symbol: str,
    signal_date: date,
    strategy_type: str = "pullback",
    close_price: float | None = 1000.0,
    rank: int = 1,
    total_score: float = 80.0,
) -> AnalysisResultModel:
    key_levels = {"close": close_price} if close_price is not None else {}
    return AnalysisResultModel(
        symbol=symbol,
        company_name=f"{symbol}社",
        market="プライム",
        sector="電気機器",
        date=signal_date,
        strategy_type=strategy_type,
        rank=rank,
        total_score=total_score,
        key_levels=key_levels,
    )


def _build_bars(
    symbol: str,
    start_date: date,
    closes: list[float],
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> list[OhlcvModel]:
    bars: list[OhlcvModel] = []
    for idx, c in enumerate(closes):
        o = opens[idx] if opens is not None else c
        h = highs[idx] if highs is not None else c + 10.0
        l = lows[idx] if lows is not None else c - 10.0
        bars.append(
            OhlcvModel(
                symbol=symbol,
                date=start_date + timedelta(days=idx),
                open=o,
                high=h,
                low=l,
                close=c,
                volume=100_000,
            )
        )
    return bars


class TestForwardReturnEvaluator(unittest.TestCase):
    def test_alias_exists(self):
        self.assertIs(Evaluator, ForwardReturnEvaluator)

    def test_compute_default_fetch_end(self):
        as_of = date(2025, 1, 10)
        expected = min(date.today(), as_of + timedelta(days=20 * 2 + 30))
        self.assertEqual(
            ForwardReturnEvaluator.compute_default_fetch_end(as_of, [20, 5]),
            expected,
        )
        self.assertEqual(
            ForwardReturnEvaluator.compute_default_fetch_end(datetime(2025, 1, 10, 15, 0), [20]),
            expected,
        )

    def test_evaluate_horizons_5_20_60_mfe_mae_and_strategy_summary(self):
        """5/20/60営業日後リターン・MFE/MAE・勝率・中央値・戦略別集計を正確に計算する"""
        as_of = date(2025, 1, 10)
        cand1 = _build_candidate(
            "7203.T", as_of, strategy_type="pullback", close_price=1000.0, rank=1, total_score=88.0
        )
        cand2 = _build_candidate(
            "6758.T", as_of, strategy_type="pullback", close_price=2000.0, rank=2, total_score=84.0
        )
        cand3 = _build_candidate(
            "9984.T", as_of, strategy_type="breakout", close_price=500.0, rank=3, total_score=80.0
        )

        # cand1: +5日=1050 (+5%), +20日=1100 (+10%), +60日=1200 (+20%), 最高値1250 (+25%), 最安値950 (-5%)
        closes1 = [1000.0] + [1010.0] * 60
        highs1 = [1005.0] + [1020.0] * 60
        lows1 = [995.0] + [990.0] * 60
        closes1[5] = 1050.0
        closes1[20] = 1100.0
        closes1[60] = 1200.0
        highs1[3] = 1120.0  # 5日窓内最高値 -> MFE +12%
        lows1[2] = 950.0    # 全窓内最安値 -> MAE -5%
        highs1[30] = 1250.0 # 60日窓内最高値 -> MFE +25%
        bars1 = _build_bars("7203.T", as_of, closes1, highs=highs1, lows=lows1)

        # cand2: +5日=1900 (-5%), +20日=1800 (-10%), +60日=2100 (+5%)
        closes2 = [2000.0] + [1980.0] * 60
        highs2 = [2010.0] + [2020.0] * 60
        lows2 = [1990.0] + [1960.0] * 60
        closes2[5] = 1900.0
        lows2[5] = 1880.0
        closes2[20] = 1800.0
        lows2[20] = 1760.0
        closes2[60] = 2100.0
        highs2[60] = 2160.0
        bars2 = _build_bars("6758.T", as_of, closes2, highs=highs2, lows=lows2)

        # cand3: +5日=550 (+10%), +20日=600 (+20%), +60日=450 (-10%)
        closes3 = [500.0] + [510.0] * 60
        highs3 = [505.0] + [520.0] * 60
        lows3 = [495.0] + [490.0] * 60
        closes3[5] = 550.0
        highs3[5] = 560.0
        closes3[20] = 600.0
        highs3[20] = 620.0
        closes3[60] = 450.0
        lows3[60] = 440.0
        bars3 = _build_bars("9984.T", as_of, closes3, highs=highs3, lows=lows3)

        evaluator = ForwardReturnEvaluator(collector=MagicMock())
        summary = evaluator.evaluate(
            [cand1, cand2, cand3],
            as_of_date=as_of,
            ohlcv_map={"7203.T": bars1, "6758.T": bars2, "9984.T": bars3},
            horizons=[5, 20, 60],
            entry_price_mode="signal_close",
        )

        self.assertEqual(summary.total_candidates, 3)
        self.assertEqual(summary.horizons, [5, 20, 60])

        # +5日全体: returns = [+5%, -5%, +10%] -> avg=10/3, median=+5%, win=2/3 (66.67%), best=9984.T, worst=6758.T
        h5 = summary.overall_summary[5]
        self.assertEqual(h5.evaluated_count, 3)
        self.assertEqual(h5.win_count, 2)
        self.assertAlmostEqual(h5.win_rate_pct, 200.0 / 3.0)
        self.assertAlmostEqual(h5.avg_return_pct, 10.0 / 3.0)
        self.assertAlmostEqual(h5.median_return_pct, 5.0)
        self.assertEqual(h5.best_symbol, "9984.T")
        self.assertAlmostEqual(h5.best_return_pct, 10.0)
        self.assertEqual(h5.worst_symbol, "6758.T")
        self.assertAlmostEqual(h5.worst_return_pct, -5.0)

        # +5日 MFE/MAE: cand1 MFE=+12%, MAE=-5%
        item1 = summary.items[0]
        self.assertAlmostEqual(item1.horizons[5].mfe_pct, 12.0)
        self.assertAlmostEqual(item1.horizons[5].mae_pct, -5.0)
        self.assertTrue(item1.horizons[5].is_win)
        self.assertAlmostEqual(item1.horizons[60].mfe_pct, 25.0)

        # +60日全体: returns = [+20%, +5%, -10%] -> avg=5%, median=+5%, win=2/3
        h60 = summary.overall_summary[60]
        self.assertAlmostEqual(h60.avg_return_pct, 5.0)
        self.assertAlmostEqual(h60.median_return_pct, 5.0)
        self.assertEqual(h60.best_symbol, "7203.T")
        self.assertEqual(h60.worst_symbol, "9984.T")

        # 戦略別集計
        self.assertIn("pullback", summary.strategy_summary)
        self.assertIn("breakout", summary.strategy_summary)
        pb_5 = summary.strategy_summary["pullback"][5]
        self.assertEqual(pb_5.total_candidates, 2)
        self.assertEqual(pb_5.evaluated_count, 2)
        self.assertAlmostEqual(pb_5.win_rate_pct, 50.0)
        self.assertAlmostEqual(pb_5.avg_return_pct, 0.0)
        bo_20 = summary.strategy_summary["breakout"][20]
        self.assertEqual(bo_20.evaluated_count, 1)
        self.assertAlmostEqual(bo_20.avg_return_pct, 20.0)

    def test_partial_horizon_unreached_and_next_open_mode(self):
        """一部ホライズン未到達と next_open モード・重複日付後勝ち整列を検証する"""
        as_of = date(2025, 3, 1)
        cand = _build_candidate("7203.T", as_of, close_price=1000.0)

        # シグナル翌日(3/2)から7営業日分のバーを生成（逆順＆重複入り）
        bars = [
            OhlcvModel(symbol="7203.T", date=date(2025, 3, 2), open=1010.0, high=1020.0, low=990.0, close=1015.0, volume=100),
            # 同一日付3/2の重複（後勝ちで open=1020.0 が使われること）
            OhlcvModel(symbol="7203.T", date=date(2025, 3, 2), open=1020.0, high=1030.0, low=1000.0, close=1025.0, volume=100),
        ]
        # 3/3 .. 3/8 の6日分を追加（合計7フォワードバー）
        for offset in range(2, 8):
            dt = date(2025, 3, 1) + timedelta(days=offset)
            bars.append(
                OhlcvModel(
                    symbol="7203.T",
                    date=dt,
                    open=1050.0,
                    high=1122.0 if offset == 5 else 1080.0,
                    low=969.0 if offset == 4 else 1010.0,
                    close=1122.0 if offset == 5 else 1060.0,
                    volume=100,
                )
            )
        # あえて逆順で渡す
        reversed_bars = list(reversed(bars))
        # 後勝ちテストのため 3/2 の正しい方を後ろに配置
        reversed_bars = [b for b in reversed_bars if b.date != date(2025, 3, 2)] + bars[:2]

        evaluator = ForwardReturnEvaluator(collector=MagicMock())
        item = evaluator.evaluate_candidate(
            cand,
            reversed_bars,
            as_of_date=as_of,
            horizons=[5, 20],
            entry_price_mode="next_open",
        )
        self.assertEqual(item.status, "evaluated")
        self.assertAlmostEqual(item.entry_price, 1020.0)
        # 5営業日目は 3/6 (3/2, 3/3, 3/4, 3/5, 3/6)
        h5 = item.horizons[5]
        self.assertTrue(h5.available)
        self.assertEqual(h5.target_date, date(2025, 3, 6))
        self.assertAlmostEqual(h5.return_pct, (1122.0 - 1020.0) / 1020.0 * 100.0)
        self.assertAlmostEqual(h5.mfe_pct, (1122.0 - 1020.0) / 1020.0 * 100.0)
        self.assertAlmostEqual(h5.mae_pct, (969.0 - 1020.0) / 1020.0 * 100.0)
        # 20営業日は未到達
        self.assertFalse(item.horizons[20].available)

    def test_signal_close_fallback_and_missing_or_no_forward_data(self):
        """key_levels欠損時のOHLCV直近終値フォールバックとデータ欠損時のステータスを検証"""
        as_of = date(2025, 4, 1)
        # key_levels なし -> signal_date(4/1) 以下の直近バー close=1500.0 を利用
        cand_fb = _build_candidate("1111.T", as_of, close_price=None)
        bars_fb = _build_bars("1111.T", date(2025, 3, 31), [1480.0, 1500.0, 1530.0, 1560.0])

        # フォワードバーなし
        cand_no_fwd = _build_candidate("2222.T", as_of, close_price=1000.0)
        bars_no_fwd = _build_bars("2222.T", date(2025, 3, 30), [990.0, 1000.0])

        # エントリー価格欠損 (key_levelsも直近バーもなし、または<=0)
        cand_missing = _build_candidate("3333.T", as_of, close_price=None)
        bars_missing = _build_bars("3333.T", date(2025, 4, 2), [1000.0, 1010.0])

        # next_open で forward_bars 空 -> no_forward_data
        cand_next_empty = _build_candidate("4444.T", as_of, close_price=1000.0)

        evaluator = ForwardReturnEvaluator(collector=MagicMock())
        item_fb = evaluator.evaluate_candidate(cand_fb, bars_fb, as_of, horizons=[2])
        self.assertEqual(item_fb.status, "evaluated")
        self.assertAlmostEqual(item_fb.entry_price, 1500.0)
        self.assertAlmostEqual(item_fb.horizons[2].return_pct, 4.0)

        item_no_fwd = evaluator.evaluate_candidate(cand_no_fwd, bars_no_fwd, as_of, horizons=[5])
        self.assertEqual(item_no_fwd.status, "no_forward_data")
        self.assertFalse(item_no_fwd.horizons[5].available)

        item_missing = evaluator.evaluate_candidate(cand_missing, bars_missing, as_of, horizons=[5])
        self.assertEqual(item_missing.status, "missing_entry_price")
        self.assertIsNone(item_missing.entry_price)
        self.assertFalse(item_missing.horizons[5].available)

        item_next_empty = evaluator.evaluate_candidate(
            cand_next_empty, bars_no_fwd, as_of, horizons=[5], entry_price_mode="next_open"
        )
        self.assertEqual(item_next_empty.status, "no_forward_data")

        # 評価対象0件のサマリーでは統計値が None になること
        summary = evaluator.evaluate(
            [cand_no_fwd, cand_missing],
            as_of_date=as_of,
            ohlcv_map={"2222.T": bars_no_fwd, "3333.T": bars_missing},
            horizons=[5],
        )
        h5_sum = summary.overall_summary[5]
        self.assertEqual(h5_sum.total_candidates, 2)
        self.assertEqual(h5_sum.evaluated_count, 0)
        self.assertIsNone(h5_sum.win_rate_pct)
        self.assertIsNone(h5_sum.avg_return_pct)
        self.assertIsNone(h5_sum.median_return_pct)
        self.assertIsNone(h5_sum.best_symbol)

    def test_collector_integration_and_error_resilience(self):
        """ohlcv_map 未指定時に DataCollector から取得し、取得例外時も継続することを検証"""
        as_of = date(2025, 5, 1)
        cand_ok = _build_candidate("7203.T", as_of, close_price=1000.0)
        cand_err = _build_candidate("9999.T", as_of, close_price=1000.0)

        bars_ok = _build_bars("7203.T", as_of, [1000.0, 1020.0, 1040.0, 1060.0, 1080.0, 1100.0])

        mock_collector = MagicMock()
        mock_collector.collect_ohlcv_data.side_effect = [
            bars_ok,
            RuntimeError("yfinance timeout"),
        ]

        evaluator = ForwardReturnEvaluator(collector=mock_collector)
        summary = evaluator.evaluate(
            [cand_ok, cand_err],
            as_of_date=as_of,
            ohlcv_map=None,
            horizons=[5],
            eval_end_date=date(2025, 5, 20),
        )

        self.assertEqual(mock_collector.collect_ohlcv_data.call_count, 2)
        first_call = mock_collector.collect_ohlcv_data.call_args_list[0]
        self.assertEqual(
            first_call.args,
            ("7203.T", as_of - timedelta(days=7), date(2025, 5, 20)),
        )
        self.assertEqual(first_call.kwargs, {"as_of_date": date(2025, 5, 20)})

        self.assertEqual(summary.items[0].status, "evaluated")
        self.assertAlmostEqual(summary.items[0].horizons[5].return_pct, 10.0)
        self.assertEqual(summary.items[1].status, "no_forward_data")
        self.assertEqual(summary.overall_summary[5].evaluated_count, 1)

    def test_holiday_signal_date_fallback_uses_lookback_margin(self):
        """signal_date が休場日かつ key_levels 欠損時、7日前からの取得データで直前営業日終値にフォールバックする"""
        # 2025-05-03(土・休場日) を基準日とする
        as_of = date(2025, 5, 3)
        cand = _build_candidate("7203.T", as_of, close_price=None)

        # 直前営業日 2025-05-02(金) の終値 1000.0 + 翌営業日以降のフォワードバー
        bars = [
            OhlcvModel(symbol="7203.T", date=date(2025, 5, 2), open=990.0, high=1010.0, low=985.0, close=1000.0, volume=1000),
            OhlcvModel(symbol="7203.T", date=date(2025, 5, 7), open=1010.0, high=1030.0, low=1005.0, close=1020.0, volume=1000),
            OhlcvModel(symbol="7203.T", date=date(2025, 5, 8), open=1020.0, high=1060.0, low=1015.0, close=1050.0, volume=1000),
        ]

        mock_collector = MagicMock()
        mock_collector.collect_ohlcv_data.return_value = bars

        evaluator = ForwardReturnEvaluator(collector=mock_collector)
        summary = evaluator.evaluate(
            [cand],
            as_of_date=as_of,
            ohlcv_map=None,
            horizons=[2],
            eval_end_date=date(2025, 5, 15),
        )

        call_args = mock_collector.collect_ohlcv_data.call_args
        self.assertEqual(
            call_args.args,
            ("7203.T", as_of - timedelta(days=7), date(2025, 5, 15)),
        )
        item = summary.items[0]
        self.assertEqual(item.status, "evaluated")
        self.assertAlmostEqual(item.entry_price, 1000.0)
        self.assertAlmostEqual(item.horizons[2].return_pct, 5.0)

    def test_datetime_and_date_mixed_bars_do_not_raise_type_error(self):
        """date 型と datetime 型のバーが混在してもソート・重複排除・比較で TypeError が起きない"""
        as_of = date(2025, 6, 1)
        cand = _build_candidate("7203.T", as_of, close_price=None)

        mixed_bars = [
            SimpleNamespace(symbol="7203.T", date=datetime(2025, 6, 3, 15, 0), open=1020.0, high=1040.0, low=1010.0, close=1030.0, volume=100),
            SimpleNamespace(symbol="7203.T", date=date(2025, 6, 1), open=990.0, high=1010.0, low=980.0, close=1000.0, volume=100),
            # 同日重複（datetime のほうが後なので後勝ち close=1050.0）
            SimpleNamespace(symbol="7203.T", date=date(2025, 6, 2), open=1000.0, high=1020.0, low=995.0, close=1010.0, volume=100),
            SimpleNamespace(symbol="7203.T", date=datetime(2025, 6, 2, 9, 0), open=1005.0, high=1060.0, low=1000.0, close=1050.0, volume=100),
        ]

        evaluator = ForwardReturnEvaluator(collector=MagicMock())
        item = evaluator.evaluate_candidate(cand, mixed_bars, as_of_date=as_of, horizons=[2])
        self.assertEqual(item.status, "evaluated")
        self.assertAlmostEqual(item.entry_price, 1000.0)
        self.assertEqual(item.horizons[2].target_date, date(2025, 6, 3))
        self.assertNotIsInstance(item.horizons[2].target_date, datetime)
        self.assertAlmostEqual(item.horizons[2].return_pct, 3.0)
        self.assertAlmostEqual(item.horizons[2].mfe_pct, 6.0)

    def test_aggregate_batch_summaries_cross_dates_and_strategies(self):
        """aggregate_batch_summaries が複数基準日・複数戦略の検証結果を昇順かつ横断で集計する"""
        evaluator = ForwardReturnEvaluator(collector=MagicMock())
        d1 = date(2025, 5, 1)
        d2 = date(2025, 6, 2)

        # d1: pullback (+10%), breakout (-5%)
        ohlcv_d1 = {
            "7203.T": _build_bars("7203.T", d1, [1000.0, 1020.0, 1100.0]),
            "6758.T": _build_bars("6758.T", d1, [1000.0, 980.0, 950.0]),
        }
        sum_d1 = evaluator.evaluate(
            [
                _build_candidate("7203.T", d1, strategy_type="pullback", close_price=1000.0, rank=1),
                _build_candidate("6758.T", d1, strategy_type="breakout", close_price=1000.0, rank=2),
            ],
            as_of_date=d1,
            ohlcv_map=ohlcv_d1,
            horizons=[2],
        )

        # d2: pullback (+20%)
        ohlcv_d2 = {
            "9984.T": _build_bars("9984.T", d2, [1000.0, 1100.0, 1200.0]),
        }
        sum_d2 = evaluator.evaluate(
            [
                _build_candidate("9984.T", d2, strategy_type="pullback", close_price=1000.0, rank=1),
            ],
            as_of_date=d2,
            ohlcv_map=ohlcv_d2,
            horizons=[2],
        )

        # わざと降順で渡しても昇順ソートされて横断集計される
        batch = ForwardReturnEvaluator.aggregate_batch_summaries(
            {d2: sum_d2, d1: sum_d1},
            horizons=[2],
            entry_price_mode="signal_close",
        )
        self.assertIsInstance(batch, BatchBacktestSummaryModel)
        self.assertEqual(batch.as_of_dates, [d1, d2])
        self.assertEqual(batch.total_dates, 2)
        self.assertEqual(batch.total_candidates, 3)

        overall_2 = batch.aggregated_overall_summary[2]
        self.assertEqual(overall_2.total_candidates, 3)
        self.assertEqual(overall_2.evaluated_count, 3)
        self.assertEqual(overall_2.win_count, 2)
        self.assertAlmostEqual(overall_2.win_rate_pct, 2 / 3 * 100.0)
        self.assertAlmostEqual(overall_2.avg_return_pct, (10.0 - 5.0 + 20.0) / 3.0)
        self.assertAlmostEqual(overall_2.median_return_pct, 10.0)
        self.assertEqual(overall_2.best_symbol, "9984.T")
        self.assertEqual(overall_2.worst_symbol, "6758.T")

        pullback_2 = batch.aggregated_strategy_summary["pullback"][2]
        self.assertEqual(pullback_2.evaluated_count, 2)
        self.assertEqual(pullback_2.win_count, 2)
        self.assertAlmostEqual(pullback_2.avg_return_pct, 15.0)

        breakout_2 = batch.aggregated_strategy_summary["breakout"][2]
        self.assertEqual(breakout_2.evaluated_count, 1)
        self.assertEqual(breakout_2.win_count, 0)
        self.assertAlmostEqual(breakout_2.avg_return_pct, -5.0)

    def test_evaluate_with_ohlcv_map_respects_eval_end_date(self):
        """ohlcv_map 指定時でも eval_end_date を超える未来バーは除外して評価する"""
        evaluator = ForwardReturnEvaluator(collector=MagicMock())
        as_of = date(2025, 5, 1)
        # 5日分（5/2〜5/6）のバーがあるが、eval_end_date=5/4 なら 2営業日分しか使えない -> horizon=5 は未到達
        bars = _build_bars("7203.T", as_of, [1000.0, 1010.0, 1020.0, 1030.0, 1040.0, 1050.0])
        cand = _build_candidate("7203.T", as_of, close_price=1000.0)

        summary = evaluator.evaluate(
            [cand],
            as_of_date=as_of,
            ohlcv_map={"7203.T": bars},
            horizons=[2, 5],
            eval_end_date=date(2025, 5, 4),
        )
        item = summary.items[0]
        self.assertTrue(item.horizons[2].available)
        self.assertEqual(item.horizons[2].target_date, date(2025, 5, 3))
        self.assertFalse(item.horizons[5].available)

    def test_evaluate_with_passed_candidates_and_cache_reuse(self):
        """passed_candidates 指定時に全通過銘柄サマリーと特徴量別分位評価を集計し、重複評価をキャッシュ再利用する"""
        as_of = date(2025, 5, 1)
        bars_map = {
            "1001.T": _build_bars("1001.T", as_of, [1000.0, 1020.0, 1050.0]),  # +5%
            "1002.T": _build_bars("1002.T", as_of, [1000.0, 1010.0, 1020.0]),  # +2%
            "1003.T": _build_bars("1003.T", as_of, [1000.0, 1000.0, 1000.0]),  # 0%
            "1004.T": _build_bars("1004.T", as_of, [1000.0, 990.0, 980.0]),    # -2%
            "1005.T": _build_bars("1005.T", as_of, [1000.0, 960.0, 900.0]),    # -10%
        }

        mock_collector = MagicMock()
        mock_collector.collect_ohlcv_data.side_effect = (
            lambda sym, start, end, as_of_date=None: bars_map[sym]
        )
        evaluator = ForwardReturnEvaluator(collector=mock_collector)

        def _cand(sym: str, f_score: float, strategy: str = "pullback", rank: int = 1):
            c = _build_candidate(sym, as_of, strategy_type=strategy, close_price=1000.0, rank=rank)
            c.feature_results = [
                FeatureResultModel(
                    feature_id="F001_Trend",
                    feature_name="トレンド強度",
                    score=f_score,
                    raw_value=f_score,
                )
            ]
            return c

        passed = [
            _cand("1001.T", 90.0, "pullback", 1),
            _cand("1002.T", 70.0, "pullback", 2),
            _cand("1003.T", 50.0, "breakout", 3),
            _cand("1004.T", 30.0, "breakout", 4),
            _cand("1005.T", 10.0, "breakout", 5),
        ]
        top_candidates = [passed[0]]

        summary = evaluator.evaluate(
            top_candidates,
            as_of_date=as_of,
            horizons=[2],
            passed_candidates=passed,
        )

        # 1001.T は top_candidates で既に評価済みなので collect_ohlcv_data は計5回のみ
        self.assertEqual(mock_collector.collect_ohlcv_data.call_count, 5)
        self.assertEqual(summary.total_candidates, 1)
        self.assertEqual(summary.overall_summary[2].win_count, 1)

        self.assertEqual(summary.passed_total_candidates, 5)
        passed_overall = summary.passed_overall_summary[2]
        self.assertEqual(passed_overall.total_candidates, 5)
        self.assertEqual(passed_overall.evaluated_count, 5)
        self.assertEqual(passed_overall.win_count, 2)
        self.assertAlmostEqual(passed_overall.avg_return_pct, (-10.0 - 2.0 + 0.0 + 2.0 + 5.0) / 5.0)
        self.assertEqual(summary.passed_strategy_summary["pullback"][2].evaluated_count, 2)
        self.assertEqual(summary.passed_strategy_summary["breakout"][2].evaluated_count, 3)

        fq = summary.feature_quantile_summary["F001_Trend"][2]
        self.assertEqual(fq.feature_name, "トレンド強度")
        self.assertEqual(fq.total_samples, 5)
        self.assertEqual(fq.unique_score_count, 5)
        self.assertEqual(fq.top_count, 1)
        self.assertEqual(fq.bottom_count, 1)
        self.assertAlmostEqual(fq.top_win_rate_pct, 100.0)
        self.assertAlmostEqual(fq.top_avg_return_pct, 5.0)
        self.assertAlmostEqual(fq.bottom_win_rate_pct, 0.0)
        self.assertAlmostEqual(fq.bottom_avg_return_pct, -10.0)
        self.assertAlmostEqual(fq.spread_return_pct, 15.0)
        self.assertAlmostEqual(fq.spread_win_rate_pct, 100.0)

    def test_compute_feature_quantiles_small_sample_guard_and_constant_score(self):
        """サンプル数 < 5 では統計を None にし、定数スコア・非有限値を適切に扱う"""
        as_of = date(2025, 5, 1)
        evaluator = ForwardReturnEvaluator(collector=MagicMock())
        ohlcv_map = {
            f"100{i}.T": _build_bars(f"100{i}.T", as_of, [1000.0, 1010.0, 1000.0 + i * 10.0])
            for i in range(1, 6)
        }
        cands = []
        for i in range(1, 6):
            c = _build_candidate(f"100{i}.T", as_of, close_price=1000.0, rank=i)
            c.feature_results = [
                # 4件のみ（5件目は NaN なので除外される） -> 少サンプルガード対象
                FeatureResultModel(
                    feature_id="F_SMALL",
                    feature_name="少サンプル特徴量",
                    score=float("nan") if i == 5 else float(i * 10),
                    raw_value=0.0,
                ),
                # 全5件とも同点（定数化検出: unique_score_count == 1）
                FeatureResultModel(
                    feature_id="F_CONST",
                    feature_name="定数特徴量",
                    score=50.0,
                    raw_value=0.0,
                ),
            ]
            cands.append(c)

        summary = evaluator.evaluate(
            cands,
            as_of_date=as_of,
            ohlcv_map=ohlcv_map,
            horizons=[2],
            passed_candidates=cands,
        )

        small_row = summary.feature_quantile_summary["F_SMALL"][2]
        self.assertEqual(small_row.total_samples, 4)
        self.assertEqual(small_row.unique_score_count, 4)
        self.assertEqual(small_row.top_count, 0)
        self.assertIsNone(small_row.top_avg_return_pct)
        self.assertIsNone(small_row.bottom_avg_return_pct)
        self.assertIsNone(small_row.spread_return_pct)

        const_row = summary.feature_quantile_summary["F_CONST"][2]
        self.assertEqual(const_row.total_samples, 5)
        self.assertEqual(const_row.unique_score_count, 1)
        self.assertEqual(const_row.top_count, 1)
        self.assertEqual(const_row.bottom_count, 1)
        # 決定的ソート (50.0, symbol, signal_date): bottom=1001.T (+1%), top=1005.T (+5%)
        self.assertAlmostEqual(const_row.bottom_avg_return_pct, 1.0)
        self.assertAlmostEqual(const_row.top_avg_return_pct, 5.0)
        self.assertAlmostEqual(const_row.spread_return_pct, 4.0)

    def test_aggregate_batch_summaries_with_passed_pool_and_feature_quantiles(self):
        """一括バックテストで全期間プールの全通過サマリーおよび特徴量別分位評価を集計する"""
        evaluator = ForwardReturnEvaluator(collector=MagicMock())
        d1 = date(2025, 5, 1)
        d2 = date(2025, 6, 2)

        def _cand(sym: str, dt: date, f_score: float, strat: str = "pullback"):
            c = _build_candidate(sym, dt, strategy_type=strat, close_price=1000.0)
            c.feature_results = [
                FeatureResultModel(
                    feature_id="F001_Mom",
                    feature_name="モメンタム",
                    score=f_score,
                    raw_value=f_score,
                )
            ]
            return c

        # d1: 3件 (+10%, +4%, -2%)
        ohlcv_d1 = {
            "1001.T": _build_bars("1001.T", d1, [1000.0, 1050.0, 1100.0]),
            "1002.T": _build_bars("1002.T", d1, [1000.0, 1020.0, 1040.0]),
            "1003.T": _build_bars("1003.T", d1, [1000.0, 990.0, 980.0]),
        }
        passed_d1 = [
            _cand("1001.T", d1, 90.0, "pullback"),
            _cand("1002.T", d1, 60.0, "pullback"),
            _cand("1003.T", d1, 30.0, "breakout"),
        ]
        sum_d1, items_d1 = evaluator.evaluate_with_passed(
            passed_d1[:1], as_of_date=d1, ohlcv_map=ohlcv_d1, horizons=[2], passed_candidates=passed_d1
        )
        # 単日では3件のため分位統計は None
        self.assertIsNone(sum_d1.feature_quantile_summary["F001_Mom"][2].spread_return_pct)

        # d2: 2件 (+20%, -10%)
        ohlcv_d2 = {
            "2001.T": _build_bars("2001.T", d2, [1000.0, 1100.0, 1200.0]),
            "2002.T": _build_bars("2002.T", d2, [1000.0, 950.0, 900.0]),
        }
        passed_d2 = [
            _cand("2001.T", d2, 95.0, "pullback"),
            _cand("2002.T", d2, 10.0, "breakout"),
        ]
        sum_d2, items_d2 = evaluator.evaluate_with_passed(
            passed_d2[:1], as_of_date=d2, ohlcv_map=ohlcv_d2, horizons=[2], passed_candidates=passed_d2
        )

        batch = ForwardReturnEvaluator.aggregate_batch_summaries(
            {d1: sum_d1, d2: sum_d2},
            horizons=[2],
            entry_price_mode="signal_close",
            passed_items_all=items_d1 + items_d2,
            passed_records_all=list(zip(passed_d1 + passed_d2, items_d1 + items_d2)),
        )

        self.assertEqual(batch.total_candidates, 2)
        self.assertEqual(batch.passed_total_candidates, 5)
        self.assertEqual(batch.aggregated_passed_overall_summary[2].evaluated_count, 5)
        self.assertEqual(batch.aggregated_passed_overall_summary[2].win_count, 3)
        self.assertEqual(batch.aggregated_passed_strategy_summary["pullback"][2].evaluated_count, 3)
        self.assertEqual(batch.aggregated_passed_strategy_summary["breakout"][2].evaluated_count, 2)

        # 全期間プールで5件揃うため、上位20% (2001.T: +20%) vs 下位20% (2002.T: -10%) が算出される
        fq = batch.aggregated_feature_quantile_summary["F001_Mom"][2]
        self.assertEqual(fq.total_samples, 5)
        self.assertEqual(fq.unique_score_count, 5)
        self.assertAlmostEqual(fq.top_avg_return_pct, 20.0)
        self.assertAlmostEqual(fq.bottom_avg_return_pct, -10.0)
        self.assertAlmostEqual(fq.spread_return_pct, 30.0)

    def test_evaluate_single_candidate_cache_preserves_candidate_attributes(self):
        """キャッシュヒット時でも各候補固有の rank / strategy_type / total_score が引き継がれる"""
        as_of = date(2025, 5, 1)
        bars = _build_bars("1001.T", as_of, [1000.0, 1020.0, 1050.0])
        mock_collector = MagicMock()
        mock_collector.collect_ohlcv_data.return_value = bars
        evaluator = ForwardReturnEvaluator(collector=mock_collector)

        cand1 = _build_candidate("1001.T", as_of, strategy_type="pullback", close_price=1000.0, rank=1)
        cand1.total_score = 88.0
        cand2 = _build_candidate("1001.T", as_of, strategy_type="breakout", close_price=1000.0, rank=3)
        cand2.total_score = 72.5

        eval_cache = {}
        item1 = evaluator._evaluate_single_candidate(cand1, as_of, [2], "signal_close", None, None, eval_cache)
        item2 = evaluator._evaluate_single_candidate(cand2, as_of, [2], "signal_close", None, None, eval_cache)

        self.assertEqual(mock_collector.collect_ohlcv_data.call_count, 1)
        self.assertEqual(item1.rank, 1)
        self.assertEqual(item1.strategy_type, "pullback")
        self.assertAlmostEqual(item1.total_score, 88.0)
        self.assertEqual(item2.rank, 3)
        self.assertEqual(item2.strategy_type, "breakout")
        self.assertAlmostEqual(item2.total_score, 72.5)

    def test_compute_feature_quantiles_includes_market_context_subscores(self):
        """sub_scores に含まれる MarketContext 由来指標が MC_* として分位評価される"""
        evaluator = ForwardReturnEvaluator(collector=MagicMock())
        as_of = date(2025, 6, 2)
        returns = [10.0, 5.0, 2.0, -3.0, -8.0]
        ohlcv_map = {
            f"100{i}.T": _build_bars(f"100{i}.T", as_of, [1000.0, 1000.0, 1000.0 * (1.0 + r / 100.0)])
            for i, r in enumerate(returns)
        }
        passed = []
        for i in range(5):
            cand = _build_candidate(f"100{i}.T", as_of, close_price=1000.0)
            cand.sub_scores = {
                "rs_score": 100.0 - i * 25.0,
                "sector_momentum_score": 90.0 - i * 20.0,
                "relative_valuation_score": 80.0 - i * 15.0,
            }
            passed.append(cand)

        summary, _ = evaluator.evaluate_with_passed(
            passed[:1], as_of_date=as_of, ohlcv_map=ohlcv_map, horizons=[2], passed_candidates=passed
        )
        for mc_id in ("MC_RS_Rank", "MC_SectorMomentum", "MC_RelativeValuation"):
            self.assertIn(mc_id, summary.feature_quantile_summary)
            row = summary.feature_quantile_summary[mc_id][2]
            self.assertEqual(row.total_samples, 5)
            self.assertAlmostEqual(row.top_avg_return_pct, 10.0)
            self.assertAlmostEqual(row.bottom_avg_return_pct, -8.0)
            self.assertAlmostEqual(row.spread_return_pct, 18.0)


if __name__ == "__main__":
    unittest.main()
