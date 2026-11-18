
import math
import tempfile
import unittest
from datetime import date, timedelta
import pandas as pd
import numpy as np

from src.common.storage import StorageManager
from src.indicator_calculator.calculator import IndicatorCalculator, calculate_indicators
from src.model.data_models import OhlcvModel, IndicatorSetModel

class TestIndicatorCalculator(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.calculator = IndicatorCalculator()
        self.calculator.storage = StorageManager(base_dir=self.temp_dir.name)
        self.symbol = "TEST"
        self.ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100.0, high=105.0, low=98.0, close=103.0, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=103.0, high=107.0, low=102.0, close=106.0, volume=1100),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 3), open=106.0, high=110.0, low=105.0, close=109.0, volume=1200),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 4), open=109.0, high=112.0, low=108.0, close=111.0, volume=1300),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 5), open=111.0, high=115.0, low=110.0, close=114.0, volume=1400),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 6), open=114.0, high=118.0, low=113.0, close=117.0, volume=1500),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 7), open=117.0, high=120.0, low=116.0, close=119.0, volume=1600),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 8), open=119.0, high=123.0, low=118.0, close=122.0, volume=1700),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 9), open=122.0, high=125.0, low=121.0, close=124.0, volume=1800),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 10), open=124.0, high=127.0, low=123.0, close=126.0, volume=1900),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 11), open=126.0, high=129.0, low=125.0, close=128.0, volume=2000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 12), open=128.0, high=131.0, low=127.0, close=130.0, volume=2100),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 13), open=130.0, high=133.0, low=129.0, close=132.0, volume=2200),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 14), open=132.0, high=135.0, low=131.0, close=134.0, volume=2300),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 15), open=134.0, high=137.0, low=133.0, close=136.0, volume=2400),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 16), open=136.0, high=139.0, low=135.0, close=138.0, volume=2500),
        ]

    def test_calculate_sma(self):
        sma_5 = self.calculator.calculate_sma(self.ohlcv_data, 5)
        self.assertEqual(len(sma_5), len(self.ohlcv_data))
        # SMAは最初のperiod-1個はNaNになることを確認
        for i in range(4):
            self.assertTrue(np.isnan(sma_5[i]))
        self.assertFalse(np.isnan(sma_5[4]))
        # 期待値との比較 (手動で計算)
        self.assertAlmostEqual(sma_5[4], (103.0 + 106.0 + 109.0 + 111.0 + 114.0) / 5.0)
        self.assertAlmostEqual(sma_5[5], (106.0 + 109.0 + 111.0 + 114.0 + 117.0) / 5.0)

    def test_calculate_rsi(self):
        rsi_14 = self.calculator.calculate_rsi(self.ohlcv_data, 14)
        self.assertEqual(len(rsi_14), len(self.ohlcv_data))
        # RSIの具体的な値は計算が複雑なため、NaNでないことと範囲内であることを確認
        self.assertFalse(np.isnan(rsi_14[-1]))
        self.assertGreaterEqual(rsi_14[-1], 0)
        self.assertLessEqual(rsi_14[-1], 100)

    def test_calculate_macd(self):
        macd_data = self.calculator.calculate_macd(self.ohlcv_data)
        self.assertEqual(len(macd_data), len(self.ohlcv_data))
        self.assertIn("macd", macd_data[-1])
        self.assertIn("signal", macd_data[-1])
        self.assertIn("histogram", macd_data[-1])

    def test_calculate_indicators_integration(self):
        indicator_sets = self.calculator.calculate_indicators(self.ohlcv_data)
        self.assertEqual(len(indicator_sets), len(self.ohlcv_data))
        self.assertIsInstance(indicator_sets[0], IndicatorSetModel)
        self.assertIn("SMA5", indicator_sets[-1].indicators)
        self.assertIn("RSI14", indicator_sets[-1].indicators)
        self.assertIn("MACD", indicator_sets[-1].indicators)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_calculate_indicators_empty_data(self):
        indicator_sets = self.calculator.calculate_indicators([])
        self.assertEqual(len(indicator_sets), 0)

    def test_calculate_highest_high_and_lowest_low(self):
        highest = self.calculator.calculate_highest_high(self.ohlcv_data, 20)
        lowest = self.calculator.calculate_lowest_low(self.ohlcv_data, 20)
        self.assertEqual(len(highest), len(self.ohlcv_data))
        self.assertEqual(len(lowest), len(self.ohlcv_data))
        self.assertAlmostEqual(highest[0], 105.0)
        self.assertAlmostEqual(highest[-1], 139.0)
        self.assertAlmostEqual(lowest[0], 98.0)
        self.assertAlmostEqual(lowest[-1], 98.0)

    def test_calculate_atr_and_volume_ratio(self):
        atr = self.calculator.calculate_atr(self.ohlcv_data, 14)
        vol_ratio = self.calculator.calculate_volume_ratio(self.ohlcv_data, 20)
        self.assertEqual(len(atr), len(self.ohlcv_data))
        self.assertEqual(len(vol_ratio), len(self.ohlcv_data))
        # 初日のTRは high - low = 105 - 98 = 7.0
        self.assertAlmostEqual(atr[0], 7.0)
        self.assertGreater(atr[-1], 0.0)
        # 初日の出来高倍率は 1000 / 1000 = 1.0
        self.assertAlmostEqual(vol_ratio[0], 1.0)
        # 最終日の出来高倍率は 2500 / mean(1000..2500=1750)
        self.assertAlmostEqual(vol_ratio[-1], 2500.0 / 1750.0)

    def test_volume_ratio_zero_division(self):
        zero_vol_data = [
            OhlcvModel(symbol="ZERO", date=date(2025, 1, 1), open=100.0, high=105.0, low=95.0, close=100.0, volume=0),
            OhlcvModel(symbol="ZERO", date=date(2025, 1, 2), open=100.0, high=105.0, low=95.0, close=100.0, volume=0),
        ]
        indicator_sets = self.calculator.calculate_indicators(zero_vol_data)
        self.assertEqual(len(indicator_sets), 2)
        self.assertIn("HIGHEST_HIGH_20", indicator_sets[-1].indicators)
        self.assertIn("LOWEST_LOW_20", indicator_sets[-1].indicators)
        self.assertIn("ATR14", indicator_sets[-1].indicators)
        self.assertNotIn("VOLUME_RATIO", indicator_sets[-1].indicators)

    def test_stale_cache_without_lowest_low_recalculates(self):
        # LOWEST_LOW_20 を含まない旧形式キャッシュを作成
        stale_cache = [
            {
                "symbol": self.symbol,
                "date": o.date.isoformat(),
                "indicators": {"SMA5": 100.0},
            }
            for o in self.ohlcv_data
        ]
        self.calculator.storage.save_json(stale_cache, f"cache/indicators_{self.symbol}.json")

        indicator_sets = self.calculator.calculate_indicators(self.ohlcv_data)
        self.assertEqual(len(indicator_sets), len(self.ohlcv_data))
        self.assertIn("HIGHEST_HIGH_20", indicator_sets[-1].indicators)
        self.assertIn("LOWEST_LOW_20", indicator_sets[-1].indicators)
        self.assertIn("ATR14", indicator_sets[-1].indicators)
        self.assertIn("VOLUME_RATIO", indicator_sets[-1].indicators)

    def test_cache_miss_when_intermediate_date_differs(self):
        """長さ・最終日が同じでも途中の日付列が異なる場合は誤ってキャッシュヒットしない"""
        self.calculator.calculate_indicators(self.ohlcv_data)

        # 2番目の日付だけ別日に差し替え（長さ・最終日は同一）
        shifted = list(self.ohlcv_data)
        shifted[1] = OhlcvModel(
            symbol=self.symbol,
            date=date(2024, 12, 31),
            open=103.0,
            high=107.0,
            low=102.0,
            close=500.0,
            volume=1100,
        )
        recalculated = self.calculator.calculate_indicators(shifted)
        self.assertEqual(recalculated[1].date, date(2024, 12, 31))
        self.assertNotAlmostEqual(
            recalculated[4].indicators["SMA5"],
            (103.0 + 106.0 + 109.0 + 111.0 + 114.0) / 5.0,
        )

    def test_cache_key_suffix_isolates_cache_files(self):
        """cache_key_suffix 指定時は通常キャッシュと別ファイルに保存・参照される"""
        self.calculator.calculate_indicators(self.ohlcv_data, cache_key_suffix="asof_2025-01-16")

        suffix_path = self.calculator.storage.base_dir / f"cache/indicators_{self.symbol}_asof_2025-01-16.json"
        default_path = self.calculator.storage.base_dir / f"cache/indicators_{self.symbol}.json"
        self.assertTrue(suffix_path.exists())
        self.assertFalse(default_path.exists())

    def test_use_cache_false_skips_read_and_write(self):
        """use_cache=False の場合は既存キャッシュを読まず、新規保存もしない"""
        # 偽キャッシュ（close=9999 で作ったようなダミー値）を配置
        fake_cache = [
            {
                "symbol": self.symbol,
                "date": o.date.isoformat(),
                "indicators": {"SMA5": 9999.0, "LOWEST_LOW_20": 9999.0},
            }
            for o in self.ohlcv_data
        ]
        self.calculator.storage.save_json(fake_cache, f"cache/indicators_{self.symbol}.json")

        # use_cache=False なら偽キャッシュを使わずに再計算する
        res = self.calculator.calculate_indicators(self.ohlcv_data, use_cache=False)
        self.assertAlmostEqual(
            res[4].indicators["SMA5"],
            (103.0 + 106.0 + 109.0 + 111.0 + 114.0) / 5.0,
        )

        # suffix 付きで use_cache=False ならキャッシュファイルを作成しない
        self.calculator.calculate_indicators(
            self.ohlcv_data, use_cache=False, cache_key_suffix="nocache_test"
        )
        nocache_path = (
            self.calculator.storage.base_dir
            / f"cache/indicators_{self.symbol}_nocache_test.json"
        )
        self.assertFalse(nocache_path.exists())

    def test_module_level_calculate_indicators_forwards_cache_args(self):
        """モジュールレベル calculate_indicators が use_cache / cache_key_suffix を引き継ぐ"""
        from src.indicator_calculator import calculator as calc_mod

        orig_storage = calc_mod.indicator_calculator.storage
        try:
            calc_mod.indicator_calculator.storage = StorageManager(base_dir=self.temp_dir.name)
            res = calculate_indicators(
                self.ohlcv_data, use_cache=True, cache_key_suffix="mod_test"
            )
            self.assertEqual(len(res), len(self.ohlcv_data))
            expected_path = (
                calc_mod.indicator_calculator.storage.base_dir
                / f"cache/indicators_{self.symbol}_mod_test.json"
            )
            self.assertTrue(expected_path.exists())
        finally:
            calc_mod.indicator_calculator.storage = orig_storage

    def test_vectorized_calculate_indicators_matches_individual_methods_all_dates(self):
        """一括ベクトル版 calculate_indicators と個別メソッドが全日付・全9指標で完全一致する"""
        bars = []
        base = date(2025, 1, 1)
        for i in range(100):
            close = 1000.0 + (i % 7) * 5.0 + i * 2.0
            bars.append(
                OhlcvModel(
                    symbol="VEC",
                    date=base + timedelta(days=i),
                    open=close - 3.0,
                    high=close + 6.0,
                    low=close - 6.0,
                    close=close,
                    volume=0 if i == 0 else 1000 + i * 50,
                )
            )

        ind_sets = self.calculator.calculate_indicators(bars, use_cache=True)
        self.assertEqual(len(ind_sets), len(bars))

        sma5 = self.calculator.calculate_sma(bars, 5)
        sma25 = self.calculator.calculate_sma(bars, 25)
        sma75 = self.calculator.calculate_sma(bars, 75)
        rsi14 = self.calculator.calculate_rsi(bars, 14)
        macd = self.calculator.calculate_macd(bars)
        hh20 = self.calculator.calculate_highest_high(bars, 20)
        ll20 = self.calculator.calculate_lowest_low(bars, 20)
        atr14 = self.calculator.calculate_atr(bars, 14)
        vr20 = self.calculator.calculate_volume_ratio(bars, 20)

        for i, ind_set in enumerate(ind_sets):
            ind = ind_set.indicators
            for key, arr in (
                ("SMA5", sma5),
                ("SMA25", sma25),
                ("SMA75", sma75),
                ("RSI14", rsi14),
                ("HIGHEST_HIGH_20", hh20),
                ("LOWEST_LOW_20", ll20),
                ("ATR14", atr14),
            ):
                if math.isnan(arr[i]):
                    self.assertNotIn(key, ind)
                else:
                    self.assertIs(type(ind[key]), float)
                    self.assertAlmostEqual(ind[key], arr[i], places=12)

            self.assertEqual(set(ind["MACD"].keys()), {"macd", "signal", "histogram"})
            for m_key in ("macd", "signal", "histogram"):
                self.assertIs(type(ind["MACD"][m_key]), float)
                self.assertAlmostEqual(ind["MACD"][m_key], macd[i][m_key], places=12)

            if vr20[i] is None:
                self.assertNotIn("VOLUME_RATIO", ind)
            else:
                self.assertIs(type(ind["VOLUME_RATIO"]), float)
                self.assertAlmostEqual(ind["VOLUME_RATIO"], vr20[i], places=12)

        # キャッシュ再読込でも全日付・全9指標・型が一致することを確認
        cached_sets = self.calculator.calculate_indicators(bars, use_cache=True)
        self.assertEqual(len(cached_sets), len(ind_sets))
        for orig, cached in zip(ind_sets, cached_sets):
            self.assertEqual(cached.symbol, orig.symbol)
            self.assertEqual(cached.date, orig.date)
            self.assertEqual(set(cached.indicators.keys()), set(orig.indicators.keys()))
            for k, orig_val in orig.indicators.items():
                cached_val = cached.indicators[k]
                if k == "MACD":
                    for m_key in ("macd", "signal", "histogram"):
                        self.assertIs(type(cached_val[m_key]), float)
                        self.assertAlmostEqual(cached_val[m_key], orig_val[m_key], places=12)
                else:
                    self.assertIs(type(cached_val), float)
                    self.assertAlmostEqual(cached_val, orig_val, places=12)

if __name__ == '__main__':
    unittest.main()
