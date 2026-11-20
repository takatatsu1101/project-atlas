import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from src.model.data_models import (
    AnalysisResultModel,
    BenchmarkMetricsModel,
    FinancialModel,
    IndicatorSetModel,
    MarketContextModel,
    OhlcvModel,
    SectorMetricsModel,
    SymbolMarketMetricsModel,
)
from src.presentation.gemini_brief import (
    LocalCopyBriefDelivery,
    build_gemini_stock_brief_data,
    compute_recent_swing_levels,
    compute_volume_poc,
    export_gemini_brief,
    normalize_symbol,
    render_gemini_brief_markdown,
)
from src.presentation.presenter import Presenter


def _make_ohlcv_series(
    symbol: str,
    start_date: date,
    count: int,
    base_close: float = 1000.0,
) -> list[OhlcvModel]:
    bars: list[OhlcvModel] = []
    for i in range(count):
        d = start_date + timedelta(days=i)
        c = base_close + i * 5.0
        bars.append(
            OhlcvModel(
                symbol=symbol,
                date=d,
                open=c - 5.0,
                high=c + 15.0,
                low=c - 15.0,
                close=c,
                volume=100_000 + i * 1_000,
            )
        )
    return bars


class TestGeminiBrief(unittest.TestCase):
    def test_normalize_symbol(self):
        self.assertEqual(normalize_symbol("7203"), "7203.T")
        self.assertEqual(normalize_symbol("7203.t"), "7203.T")
        self.assertEqual(normalize_symbol(" 1306.T "), "1306.T")

    def test_compute_recent_swing_levels_prevents_lookahead_at_edge(self):
        """右端 pivot_window 本が未確定のバーはスイング高値・安値として確定させない"""
        base = date(2026, 1, 1)
        highs = [100, 105, 110, 120, 112, 108, 104, 103, 102, 130]
        lows = [95, 98, 92, 99, 101, 90, 96, 97, 98, 80]
        bars = [
            OhlcvModel(
                symbol="7203.T",
                date=base + timedelta(days=i),
                open=100.0,
                high=float(highs[i]),
                low=float(lows[i]),
                close=100.0,
                volume=100_000,
            )
            for i in range(len(highs))
        ]
        sh, sh_d, sl, sl_d = compute_recent_swing_levels(
            bars, lookback_bars=20, pivot_window=2
        )
        # index=9 (high=130, low=80) は右側2本がないため未確定。index=3 (120) と index=5 (90) が選ばれる
        self.assertEqual(sh, 120.0)
        self.assertEqual(sh_d, base + timedelta(days=3))
        self.assertEqual(sl, 90.0)
        self.assertEqual(sl_d, base + timedelta(days=5))

    def test_compute_volume_poc(self):
        """出来高が集中した価格帯の中心が POC として返る"""
        base = date(2026, 1, 1)
        bars = [
            OhlcvModel(symbol="7203.T", date=base, open=1000, high=1020, low=980, close=1000, volume=10_000),
            OhlcvModel(symbol="7203.T", date=base + timedelta(days=1), open=1200, high=1220, low=1180, close=1200, volume=500_000),
            OhlcvModel(symbol="7203.T", date=base + timedelta(days=2), open=1400, high=1420, low=1380, close=1400, volume=20_000),
        ]
        poc = compute_volume_poc(bars, lookback_bars=60, bins=10)
        self.assertIsNotNone(poc)
        self.assertGreater(poc, 1150.0)
        self.assertLess(poc, 1250.0)

    def test_build_gemini_stock_brief_data_as_of_date_isolation(self):
        """未来バーが混入していても as_of_date 以前のバーのみ参照して指標・15日OHLCVを構築する"""
        as_of = date(2026, 8, 28)
        # 210日分 + 未来5日分
        bars = _make_ohlcv_series("7203.T", as_of - timedelta(days=209), 215, base_close=2000.0)
        # 未来バーの終値を極端な値にする
        for future_bar in bars[-5:]:
            future_bar.close = 99999.0
            future_bar.high = 99999.0

        as_of_bar = [b for b in bars if b.date == as_of][0]
        res = AnalysisResultModel(
            rank=1,
            symbol="7203.T",
            company_name="トヨタ自動車",
            market="プライム",
            sector="輸送用機器",
            date=as_of,
            total_score=78.5,
            strategy_type="pullback",
            sub_scores={
                "pullback_strategy_score": 78.5,
                "breakout_strategy_score": 60.0,
                "trend_env_score": 72.0,
            },
            key_levels={"close": as_of_bar.close},
            reasons=["25日線押し目"],
        )
        fin = FinancialModel(
            symbol="7203.T",
            fiscal_date=date(2026, 3, 31),
            per=11.5,
            pbr=1.05,
            roe=12.4,
            revenue_growth=8.2,
            free_cash_flow=500_000_000_000.0,
            total_payout_ratio=45.0,
            consecutive_dividend_increase_years=4,
        )
        ctx = MarketContextModel(
            as_of_date=as_of,
            is_active=True,
            universe_size=100,
            valid_sma25_count=100,
            above_sma25_count=65,
            breadth_ratio=0.65,
            regime="bullish",
            symbol_metrics={
                "7203.T": SymbolMarketMetricsModel(
                    symbol="7203.T",
                    rs_percentile=82.0,
                    sector_momentum_score=74.0,
                    relative_valuation_z=0.45,
                )
            },
        )

        brief = build_gemini_stock_brief_data(
            result=res,
            ohlcv_list=bars,
            financial_data=fin,
            market_context=ctx,
            as_of_date=as_of,
        )
        self.assertFalse(brief.data_missing)
        self.assertAlmostEqual(brief.unit_capital, as_of_bar.close * 100.0)
        self.assertAlmostEqual(brief.gap_up_limit_price, as_of_bar.close * 1.03)
        self.assertEqual(len(brief.recent_ohlcv), 15)
        self.assertEqual(brief.recent_ohlcv[-1].date, as_of)
        self.assertNotEqual(brief.recent_ohlcv[-1].close, 99999.0)
        self.assertEqual([m.period for m in brief.ma_metrics], [5, 25, 75, 200])
        self.assertTrue(all(m.value is not None for m in brief.ma_metrics))
        self.assertEqual(brief.rs_percentile, 82.0)

    def test_render_and_export_gemini_brief_with_copy_fallback(self):
        """ブリーフレンダリング・latest出力・同期先コピー・未マウント警告フォールバックを検証する"""
        as_of = date(2026, 8, 28)
        bars = _make_ohlcv_series("6758.T", as_of - timedelta(days=69), 70, base_close=3000.0)
        watch_bars = _make_ohlcv_series("9984.T", as_of - timedelta(days=69), 70, base_close=4000.0)

        cand_res = AnalysisResultModel(
            rank=1,
            symbol="6758.T",
            company_name="ソニーG",
            market="プライム",
            sector="電気機器",
            date=as_of,
            total_score=80.0,
            strategy_type="breakout",
            key_levels={"close": bars[-1].close},
        )
        watch_res = AnalysisResultModel(
            rank=0,
            symbol="9984.T",
            company_name="ソフトバンクG",
            market="プライム",
            sector="情報・通信業",
            date=as_of,
            total_score=55.0,
            strategy_type="watch",
            key_levels={"close": watch_bars[-1].close},
        )
        ctx = MarketContextModel(
            as_of_date=as_of,
            is_active=True,
            universe_size=50,
            valid_sma25_count=50,
            above_sma25_count=32,
            breadth_ratio=0.64,
            regime="bullish",
            benchmark=BenchmarkMetricsModel(
                symbol="1306.T",
                close=2800.0,
                sma25=2750.0,
                sma75=2700.0,
                above_sma25=True,
                above_sma75=True,
                return_20d=3.5,
                return_60d=6.2,
                return_120d=-1.4,
            ),
            sector_metrics={
                "電気機器": SectorMetricsModel(
                    sector_33="電気機器",
                    member_count=10,
                    is_sufficient=True,
                    avg_return_20d=5.0,
                    above_sma25_ratio=0.80,
                    sector_momentum_score=85.0,
                ),
                "海運業": SectorMetricsModel(
                    sector_33="海運業",
                    member_count=6,
                    is_sufficient=True,
                    avg_return_20d=-3.0,
                    above_sma25_ratio=0.20,
                    sector_momentum_score=20.0,
                ),
            },
        )

        cand_brief = build_gemini_stock_brief_data(cand_res, bars, market_context=ctx, as_of_date=as_of)
        watch_brief = build_gemini_stock_brief_data(
            watch_res, watch_bars, market_context=ctx, as_of_date=as_of, is_watch_symbol=True
        )

        md = render_gemini_brief_markdown(
            candidate_items=[cand_brief],
            watch_items=[watch_brief],
            as_of_date=as_of,
            market_context=ctx,
            metadata={"processed_symbols_count": 50, "filtered_count": 5},
        )
        self.assertIn("1306.T", md)
        self.assertIn("20d=+3.50%, 60d=+6.20%, 120d=-1.40%", md)
        self.assertIn("電気機器", md)
        self.assertIn("+5.00%", md)
        self.assertIn("海運業", md)
        self.assertIn("-3.00%", md)
        self.assertIn("6758.T", md)
        self.assertIn("9984.T", md)
        self.assertIn("直近15営業日 OHLCV", md)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "output"
            copy_dir = Path(tmpdir) / "gdrive_sync"
            copy_dir.mkdir(parents=True, exist_ok=True)

            presenter = Presenter()
            paths = presenter.export_gemini_brief(
                candidate_items=[cand_brief],
                watch_items=[watch_brief],
                output_dir=out_dir,
                as_of_date=as_of,
                market_context=ctx,
                copy_dir=copy_dir,
            )
            self.assertTrue((out_dir / "gemini_brief_2026-08-28.md").exists())
            self.assertTrue((out_dir / "gemini_brief_latest.md").exists())
            self.assertTrue((copy_dir / "gemini_brief_2026-08-28.md").exists())
            self.assertTrue((copy_dir / "gemini_brief_latest.md").exists())
            self.assertIn("gemini_copy", paths)

            # 存在しない親ディレクトリ（未マウント想定）でもローカル出力は成功する
            unmounted = Path(tmpdir) / "nonexistent_mount" / "sub"
            fallback_paths = export_gemini_brief(
                md,
                output_dir=out_dir,
                as_of_date=as_of,
                deliveries=[LocalCopyBriefDelivery(unmounted)],
            )
            self.assertTrue(fallback_paths["gemini"].exists())
            self.assertNotIn("gemini_copy", fallback_paths)
            self.assertFalse(unmounted.exists())

    def test_edge_cases_and_delivery_exception_isolation(self):
        """breadth_ratio=None・空OHLCV・短期データ・indicator_sets指定・配信例外隔離を検証する"""
        as_of = date(2026, 8, 28)

        # lookback_bars <= 0 ガード
        bars_short = _make_ohlcv_series("7203.T", as_of - timedelta(days=4), 5, base_close=1000.0)
        self.assertEqual(compute_recent_swing_levels(bars_short, lookback_bars=0), (None, None, None, None))
        self.assertIsNone(compute_volume_poc(bars_short, lookback_bars=0))

        # 空 OHLCV -> data_missing=True
        empty_res = AnalysisResultModel(
            rank=1,
            symbol="7203.T",
            company_name="トヨタ",
            date=as_of,
            total_score=0.0,
            strategy_type="watch",
        )
        empty_brief = build_gemini_stock_brief_data(empty_res, [], as_of_date=as_of)
        self.assertTrue(empty_brief.data_missing)

        # 5日短期データ + indicator_sets 明示指定 + consecutive_dividend_increase_years=None
        inds = [
            IndicatorSetModel(
                symbol="7203.T",
                date=b.date,
                indicators={"SMA5": 1005.0, "ATR14": 25.0},
            )
            for b in bars_short
        ]
        short_res = AnalysisResultModel(
            rank=1,
            symbol="7203.T",
            company_name="トヨタ",
            date=as_of,
            total_score=70.0,
            strategy_type="pullback",
            key_levels={"close": bars_short[-1].close},
            financial_summary={"consecutive_dividend_increase_years": None},
        )
        short_brief = build_gemini_stock_brief_data(
            short_res, bars_short, indicator_sets=inds, as_of_date=as_of
        )
        self.assertFalse(short_brief.data_missing)
        self.assertEqual(short_brief.atr14, 25.0)
        self.assertEqual(len(short_brief.recent_ohlcv), 5)

        # breadth_ratio=None の MarketContext レンダリング
        ctx_none_breadth = MarketContextModel(
            as_of_date=as_of,
            is_active=True,
            universe_size=25,
            valid_sma25_count=10,
            above_sma25_count=5,
            breadth_ratio=None,
            regime="neutral",
        )
        md = render_gemini_brief_markdown(
            candidate_items=[short_brief, empty_brief],
            watch_items=[],
            as_of_date=as_of,
            market_context=ctx_none_breadth,
        )
        self.assertIn("Breadth (close > SMA25)**: N/A", md)
        self.assertIn("連続増配 `N/A`", md)
        self.assertNotIn("None年", md)

        # 配信バックエンドが例外を投げてもローカル出力は成功する
        class _BrokenDelivery:
            def deliver(self, files, as_of_date):
                raise RuntimeError("upload error")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "output"
            exported = export_gemini_brief(
                md,
                output_dir=out_dir,
                as_of_date=as_of,
                deliveries=[_BrokenDelivery()],
            )
            self.assertTrue(exported["gemini"].exists())
            self.assertTrue(exported["gemini_latest"].exists())


if __name__ == "__main__":
    unittest.main()
