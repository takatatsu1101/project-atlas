import unittest
from datetime import date, timedelta
from typing import Dict, List, Optional

from pydantic import ValidationError

from src.model.data_models import (
    FinancialModel,
    IndicatorSetModel,
    MarketContextModel,
    OhlcvModel,
    StockMasterModel,
    SymbolMarketSnapshot,
)
from src.score_engine.market_context import (
    MarketContextConfig,
    build_market_context,
    compute_benchmark_metrics,
    extract_symbol_market_snapshot,
)


def _make_ohlcv_series(
    symbol: str,
    start_date: date,
    closes: List[float],
) -> List[OhlcvModel]:
    bars: List[OhlcvModel] = []
    for i, c in enumerate(closes):
        dt = start_date + timedelta(days=i)
        bars.append(
            OhlcvModel(
                symbol=symbol,
                date=dt,
                open=c - 1.0,
                high=c + 2.0,
                low=c - 2.0,
                close=c,
                volume=100_000,
            )
        )
    return bars


class TestMarketContext(unittest.TestCase):
    def test_market_context_config_validation(self):
        cfg = MarketContextConfig()
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.benchmark_symbol, "1306.T")
        self.assertEqual(cfg.min_universe_size, 20)
        self.assertEqual(cfg.min_sector_size, 5)

        with self.assertRaises(ValidationError):
            MarketContextConfig(benchmark_symbol="   ")
        with self.assertRaises(ValidationError):
            MarketContextConfig(min_universe_size=0)
        with self.assertRaises(ValidationError):
            MarketContextConfig(min_universe_size=True)  # type: ignore[arg-type]
        with self.assertRaises(ValidationError):
            MarketContextConfig(min_sector_size=1)
        with self.assertRaises(ValidationError):
            MarketContextConfig(rs_weight_short=0.0, rs_weight_medium=0.0, rs_weight_long=0.0)
        with self.assertRaises(ValidationError):
            MarketContextConfig(breadth_bearish_threshold=0.70, breadth_bullish_threshold=0.50)
        with self.assertRaises(ValidationError):
            MarketContextConfig(breadth_severe_bearish_threshold=0.45, breadth_bearish_threshold=0.40)
        with self.assertRaises(ValidationError):
            MarketContextConfig(pullback_rs_positive_factor=1.5)
        with self.assertRaises(ValidationError):
            MarketContextConfig(breakout_bearish_score_penalty=-1.0)
        with self.assertRaises(ValidationError):
            MarketContextConfig(breakout_bearish_threshold_delta=-1.0)
        with self.assertRaises(ValidationError):
            MarketContextConfig(rs_adjustment_max=float("nan"))

    def test_extract_symbol_market_snapshot_from_indicators_and_fallback(self):
        start_dt = date(2025, 1, 1)
        # 125 本の終値（100.0 -> 224.0、日次 +1.0）
        closes = [100.0 + i for i in range(125)]
        bars = _make_ohlcv_series("7203.T", start_dt, closes)
        latest_dt = bars[-1].date
        fin = FinancialModel(
            symbol="7203.T",
            fiscal_date=date(2025, 3, 31),
            per=12.5,
            pbr=1.1,
            roe=14.2,
        )

        # 1. indicator_slice に SMA25 が含まれる場合はそちらを使用
        inds = [
            IndicatorSetModel(
                symbol="7203.T",
                date=latest_dt,
                indicators={"SMA25": 200.0},
            )
        ]
        snap = extract_symbol_market_snapshot("7203.T", bars, inds, fin)
        self.assertEqual(snap.symbol, "7203.T")
        self.assertEqual(snap.bar_date, latest_dt)
        self.assertAlmostEqual(snap.close, 224.0)
        self.assertAlmostEqual(snap.sma25, 200.0)
        self.assertTrue(snap.above_sma25)
        self.assertAlmostEqual(snap.return_20d, (224.0 / 204.0 - 1.0) * 100.0)
        self.assertAlmostEqual(snap.return_60d, (224.0 / 164.0 - 1.0) * 100.0)
        self.assertAlmostEqual(snap.return_120d, (224.0 / 104.0 - 1.0) * 100.0)
        self.assertAlmostEqual(snap.per, 12.5)
        self.assertAlmostEqual(snap.pbr, 1.1)
        self.assertAlmostEqual(snap.roe, 14.2)

        # 2. indicator_slice 無しでも直近25本平均でフォールバック算出、履歴不足時は 120d=None
        short_bars = _make_ohlcv_series("6758.T", start_dt, [100.0 + i for i in range(65)])
        snap_fb = extract_symbol_market_snapshot("6758.T", short_bars, None, None)
        expected_sma25 = sum(range(140, 165)) / 25.0
        self.assertAlmostEqual(snap_fb.sma25, expected_sma25)
        self.assertTrue(snap_fb.above_sma25)
        self.assertIsNotNone(snap_fb.return_20d)
        self.assertIsNotNone(snap_fb.return_60d)
        self.assertIsNone(snap_fb.return_120d)

        # 3. 25本未満は sma25=None, above_sma25=None
        tiny_bars = _make_ohlcv_series("9984.T", start_dt, [100.0 + i for i in range(10)])
        snap_tiny = extract_symbol_market_snapshot("9984.T", tiny_bars)
        self.assertIsNone(snap_tiny.sma25)
        self.assertIsNone(snap_tiny.above_sma25)
        self.assertIsNone(snap_tiny.return_20d)

    def test_benchmark_and_market_context_block_lookahead_bias(self):
        """as_of_date より後のベンチマークバー・未来日スナップショットを改ざんしても過去断面が1ビットも変化しない"""
        as_of = date(2025, 6, 1)
        start_dt = date(2025, 1, 1)
        past_len = (as_of - start_dt).days + 1  # 152 本

        bench_past = _make_ohlcv_series("1306.T", start_dt, [2500.0 + i * 2.0 for i in range(past_len)])
        bench_future_a = _make_ohlcv_series(
            "1306.T",
            as_of + timedelta(days=1),
            [3000.0 + i * 10.0 for i in range(30)],
        )
        bench_future_b = _make_ohlcv_series(
            "1306.T",
            as_of + timedelta(days=1),
            [10.0 if i % 2 == 0 else 99999.0 for i in range(30)],
        )

        bm_a = compute_benchmark_metrics(bench_past + bench_future_a, as_of)
        bm_b = compute_benchmark_metrics(bench_past + bench_future_b, as_of)
        self.assertEqual(bm_a.model_dump(), bm_b.model_dump())
        self.assertTrue(bm_a.available)
        self.assertEqual(bm_a.bar_date, as_of)

        cfg = MarketContextConfig(min_universe_size=5, min_sector_size=2)
        base_snaps = [
            SymbolMarketSnapshot(
                symbol=f"{1000 + i}.T",
                bar_date=as_of,
                close=1000.0 + i * 10.0,
                sma25=950.0,
                above_sma25=True,
                return_20d=float(i),
                return_60d=float(i * 2),
                per=12.0 + i,
                pbr=1.0 + 0.1 * i,
                roe=10.0 + i,
            )
            for i in range(6)
        ]
        future_snaps_a = base_snaps + [
            SymbolMarketSnapshot(
                symbol="9999.T",
                bar_date=as_of + timedelta(days=1),
                close=5000.0,
                above_sma25=False,
                return_20d=-40.0,
            )
        ]
        future_snaps_b = base_snaps + [
            SymbolMarketSnapshot(
                symbol="9999.T",
                bar_date=as_of + timedelta(days=5),
                close=1.0,
                above_sma25=True,
                return_20d=200.0,
            )
        ]
        masters = [
            StockMasterModel(
                code=str(1000 + i),
                symbol=f"{1000 + i}.T",
                name=f"銘柄{i}",
                market="プライム",
                sector_33="電気機器",
            )
            for i in range(6)
        ]

        ctx_a = build_market_context(
            as_of_date=as_of,
            snapshots=future_snaps_a,
            master_map=masters,
            benchmark_ohlcv=bench_past + bench_future_a,
            config=cfg,
        )
        ctx_b = build_market_context(
            as_of_date=as_of,
            snapshots=future_snaps_b,
            master_map=masters,
            benchmark_ohlcv=bench_past + bench_future_b,
            config=cfg,
        )
        self.assertEqual(ctx_a.model_dump(), ctx_b.model_dump())
        self.assertNotIn("9999.T", ctx_a.symbol_metrics)
        self.assertEqual(ctx_a.universe_size, 6)

    def test_rs_sector_momentum_and_relative_valuation_scoring(self):
        """対TOPIX RS順位（120日欠損フォールバック含む）・33業種モメンタム・業種内相対バリュエーションの計算を検証"""
        as_of = date(2025, 7, 1)
        start_dt = date(2025, 1, 1)
        n_days = (as_of - start_dt).days + 1
        # ベンチマークは横ばい（リターン 0%、close >= SMA25）
        bench_bars = _make_ohlcv_series("1306.T", start_dt, [2000.0] * n_days)

        cfg = MarketContextConfig(min_universe_size=10, min_sector_size=5)
        masters: List[StockMasterModel] = []
        snaps: List[SymbolMarketSnapshot] = []

        # 強い業種「電気機器」(5銘柄: リターン +10%〜+20%、全員 close > SMA25)
        for i in range(5):
            sym = f"600{i}.T"
            masters.append(
                StockMasterModel(
                    code=f"600{i}",
                    symbol=sym,
                    name=f"電機{i}",
                    market="プライム",
                    sector_33="電気機器",
                )
            )
            # 6004 は 120日リターン欠損(None)、6000..6003 は 120日あり
            # 6004 は PER=8 / PBR=0.6 / ROE=20 で同業種内最割安・高ROE
            snaps.append(
                SymbolMarketSnapshot(
                    symbol=sym,
                    bar_date=as_of,
                    close=1500.0,
                    sma25=1400.0,
                    above_sma25=True,
                    return_20d=25.0 if i == 4 else (10.0 + i * 2.5),
                    return_60d=35.0 if i == 4 else (15.0 + i * 3.0),
                    return_120d=None if i == 4 else 20.0 + i * 4.0,
                    per=25.0 - i * 4.0,
                    pbr=2.2 - i * 0.4,
                    roe=8.0 + i * 3.0,
                )
            )

        # 弱い業種「小売業」(5銘柄: リターン -10%〜-2%、全員 close <= SMA25)
        for i in range(5):
            sym = f"800{i}.T"
            masters.append(
                StockMasterModel(
                    code=f"800{i}",
                    symbol=sym,
                    name=f"小売{i}",
                    market="プライム",
                    sector_33="小売業",
                )
            )
            snaps.append(
                SymbolMarketSnapshot(
                    symbol=sym,
                    bar_date=as_of,
                    close=900.0,
                    sma25=1000.0,
                    above_sma25=False,
                    return_20d=-10.0 + i * 2.0,
                    return_60d=-12.0 + i * 2.0,
                    return_120d=-15.0 + i * 2.0,
                    per=15.0,  # 全員同値 -> std=0 ガードで Z スコア中立(None)
                    pbr=1.2,
                    roe=10.0,
                )
            )

        # 少数業種「海運業」(2銘柄 < min_sector_size=5 -> 業種モメンタム・相対バリュエーションは None/0.0)
        for i in range(2):
            sym = f"910{i}.T"
            masters.append(
                StockMasterModel(
                    code=f"910{i}",
                    symbol=sym,
                    name=f"海運{i}",
                    market="プライム",
                    sector_33="海運業",
                )
            )
            snaps.append(
                SymbolMarketSnapshot(
                    symbol=sym,
                    bar_date=as_of,
                    close=1200.0,
                    sma25=1150.0,
                    above_sma25=True,
                    return_20d=3.0,
                    return_60d=4.0,
                    return_120d=5.0,
                    per=7.0,
                    pbr=0.5,
                    roe=22.0,
                )
            )

        ctx = build_market_context(
            as_of_date=as_of,
            snapshots=snaps,
            master_map=masters,
            benchmark_ohlcv=bench_bars,
            config=cfg,
        )

        self.assertTrue(ctx.is_active)
        self.assertEqual(ctx.universe_size, 12)
        self.assertEqual(ctx.regime, "neutral")  # Breadth 7/12 = 58.3% (< 60%)

        # 電気機器は小売業より業種モメンタムスコアが高い
        self.assertTrue(ctx.sector_metrics["電気機器"].is_sufficient)
        self.assertAlmostEqual(ctx.sector_metrics["電気機器"].sector_momentum_score, 100.0)
        self.assertAlmostEqual(ctx.sector_metrics["小売業"].sector_momentum_score, 0.0)
        self.assertFalse(ctx.sector_metrics["海運業"].is_sufficient)
        self.assertIsNone(ctx.sector_metrics["海運業"].sector_momentum_score)

        # 6004.T: 120日欠損でも 20/60日で計算され RS上位 & 電機業種 & 最割安高ROE -> プラス補正
        #         押し目買いでは正の RS 補正が pullback_rs_positive_factor(0.3) で抑制されるため pullback < breakout
        m_top = ctx.symbol_metrics["6004.T"]
        self.assertIsNotNone(m_top.composite_excess_return)
        self.assertAlmostEqual(m_top.rs_percentile, 100.0)
        self.assertAlmostEqual(m_top.rs_adjustment, cfg.rs_adjustment_max)
        self.assertAlmostEqual(m_top.sector_momentum_adjustment, cfg.sector_momentum_adjustment_max)
        self.assertGreater(m_top.relative_valuation_z, 0.0)
        self.assertGreater(m_top.relative_valuation_adjustment, 0.0)
        self.assertLess(m_top.pullback_adjustment, m_top.breakout_adjustment)
        self.assertGreater(m_top.pullback_adjustment, 5.0)
        self.assertLessEqual(m_top.breakout_adjustment, cfg.total_adjustment_cap)
        self.assertAlmostEqual(m_top.total_adjustment, m_top.breakout_adjustment)

        # 8000.T: RS最下位 & 小売弱業種 & PER/PBR/ROE 全員同値で std=0 ガード -> 負の RS 減点は押し目でも同額適用
        m_low = ctx.symbol_metrics["8000.T"]
        self.assertAlmostEqual(m_low.rs_percentile, 0.0)
        self.assertAlmostEqual(m_low.rs_adjustment, -cfg.rs_adjustment_max)
        self.assertAlmostEqual(m_low.sector_momentum_adjustment, -cfg.sector_momentum_adjustment_max)
        self.assertIsNone(m_low.relative_valuation_z)
        self.assertAlmostEqual(m_low.relative_valuation_adjustment, 0.0)
        self.assertAlmostEqual(m_low.pullback_adjustment, m_low.breakout_adjustment)
        self.assertAlmostEqual(m_low.total_adjustment, -cfg.total_adjustment_cap)

        # 9100.T: 少数業種(2件 < min_sector_size=5) のため業種モメンタム・相対バリュエーションは中立(0.0)
        m_small_sec = ctx.symbol_metrics["9100.T"]
        self.assertIsNone(m_small_sec.sector_momentum_score)
        self.assertAlmostEqual(m_small_sec.sector_momentum_adjustment, 0.0)
        self.assertIsNone(m_small_sec.relative_valuation_z)
        self.assertAlmostEqual(m_small_sec.relative_valuation_adjustment, 0.0)

    def test_market_regime_transitions_and_fallback_without_benchmark(self):
        """bullish / neutral / bearish（二極化極端低下含む）の境界条件とベンチマーク欠損時フォールバックを検証"""
        as_of = date(2025, 7, 1)
        start_dt = date(2025, 1, 1)
        n_days = (as_of - start_dt).days + 1
        cfg = MarketContextConfig(
            min_universe_size=20,
            breadth_severe_bearish_threshold=0.35,
            breadth_bearish_threshold=0.40,
            breakout_bearish_threshold_delta=8.0,
            breakout_bearish_score_penalty=6.0,
        )

        # ベンチマーク上昇トレンド (close > SMA25) vs 下降トレンド (close < SMA25)
        bench_up = _make_ohlcv_series("1306.T", start_dt, [2000.0 + i * 2.0 for i in range(n_days)])
        bench_down = _make_ohlcv_series("1306.T", start_dt, [2500.0 - i * 3.0 for i in range(n_days)])

        def _make_snaps(above_count: int, total_count: int, r20_val: float) -> List[SymbolMarketSnapshot]:
            return [
                SymbolMarketSnapshot(
                    symbol=f"{1000 + i}.T",
                    bar_date=as_of,
                    close=1000.0,
                    sma25=950.0 if i < above_count else 1050.0,
                    above_sma25=(i < above_count),
                    return_20d=r20_val,
                )
                for i in range(total_count)
            ]

        # 1. Breadth 38% (19/50, 35% <= 38% < 40%) かつ TOPIX < SMA25 -> bearish, delta=8.0, score_penalty=6.0
        ctx_bear = build_market_context(
            as_of, _make_snaps(19, 50, -3.0), benchmark_ohlcv=bench_down, config=cfg
        )
        self.assertEqual(ctx_bear.regime, "bearish")
        self.assertAlmostEqual(ctx_bear.breadth_ratio, 0.38)
        self.assertAlmostEqual(ctx_bear.breakout_threshold_delta, 8.0)
        self.assertAlmostEqual(ctx_bear.breakout_score_penalty, 6.0)

        # 2. Breadth 38% (35% <= 38% < 40%) かつ TOPIX >= SMA25 -> neutral, delta=0.0, score_penalty=0.0
        ctx_neutral_topix_up = build_market_context(
            as_of, _make_snaps(19, 50, -3.0), benchmark_ohlcv=bench_up, config=cfg
        )
        self.assertEqual(ctx_neutral_topix_up.regime, "neutral")
        self.assertAlmostEqual(ctx_neutral_topix_up.breakout_threshold_delta, 0.0)
        self.assertAlmostEqual(ctx_neutral_topix_up.breakout_score_penalty, 0.0)

        # 3. Breadth 30% (15/50 < 35% 極端悪化) かつ TOPIX >= SMA25 -> 二極化地合い悪化ガードで bearish
        ctx_severe_bear = build_market_context(
            as_of, _make_snaps(15, 50, -2.0), benchmark_ohlcv=bench_up, config=cfg
        )
        self.assertEqual(ctx_severe_bear.regime, "bearish")
        self.assertAlmostEqual(ctx_severe_bear.breadth_ratio, 0.30)
        self.assertAlmostEqual(ctx_severe_bear.breakout_threshold_delta, 8.0)
        self.assertAlmostEqual(ctx_severe_bear.breakout_score_penalty, 6.0)

        # 4. Breadth 70% (35/50 >= 60%) かつ TOPIX >= SMA25 -> bullish
        ctx_bull = build_market_context(
            as_of, _make_snaps(35, 50, 4.0), benchmark_ohlcv=bench_up, config=cfg
        )
        self.assertEqual(ctx_bull.regime, "bullish")
        self.assertAlmostEqual(ctx_bull.breakout_threshold_delta, 0.0)
        self.assertAlmostEqual(ctx_bull.breakout_score_penalty, 0.0)

        # 5. ベンチマーク欠損時はユニバース20日リターン中央値 (< 0) で bearish 判定可能
        ctx_no_bench_bear = build_market_context(
            as_of, _make_snaps(19, 50, -4.0), benchmark_ohlcv=None, config=cfg
        )
        self.assertFalse(ctx_no_bench_bear.benchmark.available)
        self.assertEqual(ctx_no_bench_bear.regime, "bearish")
        self.assertAlmostEqual(ctx_no_bench_bear.breakout_threshold_delta, 8.0)
        self.assertAlmostEqual(ctx_no_bench_bear.breakout_score_penalty, 6.0)

    def test_insufficient_universe_disabled_and_frozen_model(self):
        """少銘柄ガード・無効化フラグ・読み取り専用モデル(frozen=True)・調整上限キャップを検証"""
        as_of = date(2025, 7, 1)
        snaps = [
            SymbolMarketSnapshot(
                symbol=f"{1000 + i}.T",
                bar_date=as_of,
                close=1000.0,
                above_sma25=False,
                return_20d=-5.0,
            )
            for i in range(5)
        ]

        # 1. 少銘柄ガード (5 < min_universe_size=20)
        ctx_small = build_market_context(as_of, snaps, config=MarketContextConfig())
        self.assertFalse(ctx_small.is_active)
        self.assertEqual(ctx_small.inactive_reason, "insufficient_universe")
        self.assertEqual(ctx_small.regime, "unknown")
        self.assertAlmostEqual(ctx_small.breakout_threshold_delta, 0.0)
        self.assertEqual(ctx_small.symbol_metrics, {})

        # 2. enabled=False
        ctx_disabled = build_market_context(
            as_of, snaps, config=MarketContextConfig(enabled=False, min_universe_size=2)
        )
        self.assertFalse(ctx_disabled.is_active)
        self.assertEqual(ctx_disabled.inactive_reason, "disabled")

        # 3. total_adjustment_cap の上限/下限クリップと frozen=True
        cfg_cap = MarketContextConfig(
            min_universe_size=5,
            min_sector_size=5,
            rs_adjustment_max=8.0,
            sector_momentum_adjustment_max=5.0,
            relative_valuation_adjustment_max=5.0,
            total_adjustment_cap=6.0,
        )
        masters = [
            StockMasterModel(
                code=str(1000 + i),
                symbol=f"{1000 + i}.T",
                name=f"M{i}",
                market="プライム",
                sector_33="電気機器" if i < 5 else "小売業",
            )
            for i in range(10)
        ]
        snaps_cap = [
            SymbolMarketSnapshot(
                symbol=f"{1000 + i}.T",
                bar_date=as_of,
                close=1000.0,
                sma25=900.0 if i < 5 else 1100.0,
                above_sma25=(i < 5),
                return_20d=20.0 - i * 4.0,
                return_60d=20.0 - i * 4.0,
                per=5.0 + i * 5.0,
                pbr=0.5 + i * 0.3,
                roe=25.0 - i * 2.0,
            )
            for i in range(10)
        ]
        ctx_cap = build_market_context(as_of, snaps_cap, master_map=masters, config=cfg_cap)
        self.assertTrue(ctx_cap.is_active)
        self.assertLessEqual(ctx_cap.symbol_metrics["1000.T"].total_adjustment, 6.0)
        self.assertGreaterEqual(ctx_cap.symbol_metrics["1009.T"].total_adjustment, -6.0)

        # frozen=True により再代入不可
        self.assertIsInstance(ctx_cap, MarketContextModel)
        with self.assertRaises(ValidationError):
            ctx_cap.regime = "hacked"  # type: ignore[misc]

        summary = ctx_cap.to_regime_summary()
        self.assertEqual(summary["as_of_date"], as_of.isoformat())
        self.assertTrue(summary["is_active"])
        self.assertIn("regime", summary)

    def test_nan_inf_direct_snapshot_and_tied_midrank_percentiles(self):
        """直接入力スナップショットの NaN/inf が +100/+cap 化けせず除外され、全員同値リターンが 50.0 になることを検証"""
        as_of = date(2025, 7, 1)
        cfg = MarketContextConfig(min_universe_size=5, min_sector_size=5)
        masters = [
            StockMasterModel(
                code=str(1000 + i),
                symbol=f"{1000 + i}.T",
                name=f"M{i}",
                market="プライム",
                sector_33="電気機器",
            )
            for i in range(6)
        ]

        # 全員同値リターン (5.0%) かつ 1005.T に NaN/inf を直接混入
        snaps = [
            SymbolMarketSnapshot(
                symbol=f"{1000 + i}.T",
                bar_date=as_of,
                close=1000.0,
                sma25=float("nan") if i == 5 else 950.0,
                above_sma25=True,
                return_20d=float("nan") if i == 5 else 5.0,
                return_60d=float("inf") if i == 5 else 5.0,
                return_120d=float("-inf") if i == 5 else 5.0,
                per=float("nan") if i == 5 else (10.0 + i),
                pbr=float("inf") if i == 5 else (1.0 + 0.1 * i),
                roe=float("-inf") if i == 5 else (10.0 + i),
            )
            for i in range(6)
        ]
        # close=NaN の銘柄はユニバースから安全除外される
        snaps.append(
            SymbolMarketSnapshot(
                symbol="9999.T",
                bar_date=as_of,
                close=float("nan"),
                return_20d=50.0,
            )
        )

        ctx = build_market_context(as_of, snaps, master_map=masters, config=cfg)
        self.assertTrue(ctx.is_active)
        self.assertEqual(ctx.universe_size, 6)
        self.assertNotIn("9999.T", ctx.symbol_metrics)

        # 全員同値リターン -> 中点順位パーセンタイルは全員 50.0、RS補正は 0.0
        for i in range(5):
            m = ctx.symbol_metrics[f"{1000 + i}.T"]
            self.assertAlmostEqual(m.rs_percentile, 50.0)
            self.assertAlmostEqual(m.rs_adjustment, 0.0)

        # NaN/inf 混入銘柄 (1005.T) は非有限値が None 扱いとなり、+100 や +cap へ化けない
        m_nan = ctx.symbol_metrics["1005.T"]
        self.assertIsNone(m_nan.return_20d)
        self.assertIsNone(m_nan.return_60d)
        self.assertIsNone(m_nan.return_120d)
        self.assertIsNone(m_nan.composite_excess_return)
        self.assertIsNone(m_nan.rs_percentile)
        self.assertAlmostEqual(m_nan.rs_adjustment, 0.0)
        self.assertIsNone(m_nan.relative_valuation_z)
        self.assertAlmostEqual(ctx.sector_metrics["電気機器"].avg_return_20d, 5.0)
        self.assertEqual(ctx.valid_sma25_count, 5)


if __name__ == "__main__":
    unittest.main()
