import math
import time
import unittest
from datetime import date, timedelta

from src.pattern_detector.patterns.reversal.double_top import DoubleTopPattern
from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternResultModel

class TestDoubleTopPattern(unittest.TestCase):

    def setUp(self):
        self.pattern_detector = DoubleTopPattern()
        self.symbol = "TEST"

    def test_pattern_properties(self):
        self.assertEqual(self.pattern_detector.pattern_id, "R002_DoubleTop")
        self.assertEqual(self.pattern_detector.pattern_name, "ダブルトップ")
        self.assertEqual(self.pattern_detector.pattern_category, "Reversal")

    def test_detect_valid_double_top(self):
        # 典型的なダブルトップが形成される16日分のOHLCVデータを構成
        # 1〜3日：上昇
        # 4日目：山1（高値120.0）
        # 5〜7日：一時下落
        # 8日目：ネックライン（安値100.0）
        # 9〜11日：再び上昇
        # 12日目：山2（高値119.5。山1から0.4%の差）
        # 13〜15日：下落
        # 16日目：ネックライン下抜け（終値98.0）
        prices = [
            (100, 102, 98, 101),   # 1
            (105, 108, 103, 107),  # 2
            (110, 115, 108, 114),  # 3
            (115, 120, 114, 118),  # 4 (山1: index 3)
            (112, 115, 108, 110),  # 5
            (105, 108, 102, 104),  # 6
            (101, 104, 100, 102),  # 7
            (100, 102, 100, 101),  # 8 (ネック: index 7)
            (103, 108, 102, 107),  # 9
            (110, 114, 108, 113),  # 10
            (114, 118, 112, 117),  # 11
            (116, 119.5, 115, 117),# 12 (山2: index 11)
            (112, 115, 108, 110),  # 13
            (105, 108, 102, 104),  # 14
            (101, 103, 99, 100),   # 15
            (99, 100, 95, 98.0),   # 16 (終値 98.0 < ネック安 100.0 下抜け!)
        ]

        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, idx+1), open=p[0], high=p[1], low=p[2], close=p[3], volume=1000)
            for idx, p in enumerate(prices)
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=d.date, indicators={}) for d in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        self.assertGreaterEqual(len(results), 1)
        # 16日目（最後のデータ）で検知されることを確認
        self.assertEqual(results[-1].metadata["date"], date(2025, 1, 16))
        self.assertGreaterEqual(results[-1].confidence, 80.0) # 下抜け直後なので非常に高信頼度

    def test_detect_forming_double_top(self):
        # 形成途中（ネックラインに届いていないが、山2から下落中）
        # 山1: 120, ネック安: 100, 山2: 119.5, 終値: 110.0 (下落中)
        prices = [
            (100, 102, 98, 101),   # 1
            (105, 108, 103, 107),  # 2
            (110, 115, 108, 114),  # 3
            (115, 120, 114, 118),  # 4 (山1: index 3)
            (112, 115, 108, 110),  # 5
            (105, 108, 102, 104),  # 6
            (101, 104, 100, 102),  # 7
            (100, 102, 100, 101),  # 8 (ネック: index 7)
            (103, 108, 102, 107),  # 9
            (110, 114, 108, 113),  # 10
            (114, 118, 112, 117),  # 11
            (116, 119.5, 115, 117),# 12 (山2: index 11)
            (113, 117, 112, 115),  # 13
            (111, 114, 108, 112),  # 14
            (108, 111, 106, 110.0),# 15 (終値 110.0 で下落中。index 14)
        ]

        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, idx+1), open=p[0], high=p[1], low=p[2], close=p[3], volume=1000)
            for idx, p in enumerate(prices)
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=d.date, indicators={}) for d in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[-1].metadata["date"], date(2025, 1, 15))
        # ネックラインの上なので、完成よりは信頼度が低い
        self.assertTrue(40.0 <= results[-1].confidence <= 75.0)

    def test_broken_double_top(self):
        # 抵抗線上抜け（山2の高値をさらに上抜けて上昇。不成立）
        prices = [
            (100, 102, 98, 101),   # 1
            (105, 108, 103, 107),  # 2
            (110, 115, 108, 114),  # 3
            (115, 120, 114, 118),  # 4 (山1: index 3)
            (112, 115, 108, 110),  # 5
            (105, 108, 102, 104),  # 6
            (101, 104, 100, 102),  # 7
            (100, 102, 100, 101),  # 8 (ネック)
            (103, 108, 102, 107),  # 9
            (110, 114, 108, 113),  # 10
            (114, 118, 112, 117),  # 11
            (116, 119.5, 115, 117),# 12 (山2)
            (118, 123, 116, 122.0),# 13 (天井 119.5 を上抜けて急騰。不成立)
        ]

        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, idx+1), open=p[0], high=p[1], low=p[2], close=p[3], volume=1000)
            for idx, p in enumerate(prices)
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=d.date, indicators={}) for d in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        # 上抜けした日は検知されない
        if len(results) > 0:
            self.assertNotEqual(results[-1].metadata["date"], date(2025, 1, 13))

    def test_insufficient_data(self):
        # 15日未満のデータ
        results = self.pattern_detector.detect([], [])
        self.assertEqual(len(results), 0)

    def _naive_double_top_detect(self, ohlcv_data):
        """旧 O(N^2) アルゴリズムと同等の参照実装（全日付一致検証用）"""
        results = []
        if len(ohlcv_data) < 15:
            return results
        for i in range(10, len(ohlcv_data)):
            current_close = ohlcv_data[i].close
            peaks = []
            for j in range(2, i - 2):
                high_j = ohlcv_data[j].high
                if (
                    high_j > ohlcv_data[j - 1].high
                    and high_j > ohlcv_data[j - 2].high
                    and high_j > ohlcv_data[j + 1].high
                    and high_j > ohlcv_data[j + 2].high
                ):
                    peaks.append(j)
            if len(peaks) < 2:
                continue
            t1_idx, t2_idx = peaks[-2], peaks[-1]
            t1_high, t2_high = ohlcv_data[t1_idx].high, ohlcv_data[t2_idx].high
            if abs(t1_high - t2_high) / t1_high > 0.025:
                continue
            neck_idx = t1_idx + 1
            for j in range(t1_idx + 1, t2_idx):
                if ohlcv_data[j].low < ohlcv_data[neck_idx].low:
                    neck_idx = j
            neck_low = ohlcv_data[neck_idx].low
            if current_close > max(t1_high, t2_high):
                continue
            confidence = self.pattern_detector._calculate_confidence({
                "close": current_close,
                "t2_high": t2_high,
                "neck_low": neck_low,
            })
            if confidence >= 40.0:
                results.append(PatternResultModel(
                    pattern_id=self.pattern_detector.pattern_id,
                    pattern_name=self.pattern_detector.pattern_name,
                    confidence=confidence,
                    metadata={
                        "date": ohlcv_data[i].date,
                        "t1_date": ohlcv_data[t1_idx].date,
                        "t2_date": ohlcv_data[t2_idx].date,
                        "neck_date": ohlcv_data[neck_idx].date,
                        "t1_high": t1_high,
                        "t2_high": t2_high,
                        "neck_low": neck_low,
                        "close": current_close,
                    },
                ))
        return results

    def test_matches_naive_reference_all_dates_and_target_indices(self):
        """O(N) 実装が旧アルゴリズムと全日付一致し、target_indices とも一致する"""
        bars = []
        base = date(2024, 1, 1)
        for i in range(120):
            wave = 100.0 + 10.0 * math.sin(i * 0.45)
            bars.append(
                OhlcvModel(
                    symbol=self.symbol,
                    date=base + timedelta(days=i),
                    open=wave,
                    high=wave + 3.0,
                    low=wave - 3.0,
                    close=wave - 1.0,
                    volume=1000,
                )
            )
        ind = [IndicatorSetModel(symbol=self.symbol, date=b.date, indicators={}) for b in bars]

        expected = self._naive_double_top_detect(bars)
        actual = self.pattern_detector.detect(bars, ind)
        self.assertGreater(len(expected), 0)
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            self.assertEqual(a.pattern_id, e.pattern_id)
            self.assertAlmostEqual(a.confidence, e.confidence, places=12)
            self.assertEqual(a.metadata, e.metadata)

        # target_indices 指定時の一致確認
        target_idx = [-1, 30, 50, -1, 999]
        target_dates = {bars[119].date, bars[30].date, bars[50].date}
        partial = self.pattern_detector.detect(bars, ind, target_indices=target_idx)
        expected_partial = [r for r in actual if r.metadata["date"] in target_dates]
        self.assertEqual(len(partial), len(expected_partial))
        for p, ep in zip(sorted(partial, key=lambda r: r.metadata["date"]), expected_partial):
            self.assertEqual(p.metadata, ep.metadata)
            self.assertAlmostEqual(p.confidence, ep.confidence, places=12)

    def test_long_series_2000_days_performance(self):
        """2000日系列を O(N) で高速に処理できる"""
        bars = []
        base = date(2018, 1, 1)
        for i in range(2000):
            wave = 1000.0 + 20.0 * math.sin(i * 0.4)
            bars.append(
                OhlcvModel(
                    symbol=self.symbol,
                    date=base + timedelta(days=i),
                    open=wave,
                    high=wave + 5.0,
                    low=wave - 5.0,
                    close=wave - 2.0,
                    volume=1000,
                )
            )
        ind = [IndicatorSetModel(symbol=self.symbol, date=b.date, indicators={}) for b in bars]
        t0 = time.perf_counter()
        results = self.pattern_detector.detect(bars, ind)
        elapsed = time.perf_counter() - t0
        self.assertGreater(len(results), 0)
        self.assertLess(elapsed, 0.5)

    def test_edge_cases_boundaries_tie_break_flat_and_zero_price(self):
        """14日以下・同値ネックライン・2.5%境界・フラット極値・e1_val==0 境界を検証"""
        base = date(2025, 2, 1)

        def to_bars(rows):
            bars = [
                OhlcvModel(
                    symbol=self.symbol,
                    date=base + timedelta(days=idx),
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=1000,
                )
                for idx, (o, h, l, c) in enumerate(rows)
            ]
            inds = [IndicatorSetModel(symbol=self.symbol, date=b.date, indicators={}) for b in bars]
            return bars, inds

        # 1. len == 14 (< 15) は空
        b14, i14 = to_bars([(100, 102, 98, 100)] * 14)
        self.assertEqual(self.pattern_detector.detect(b14, i14), [])

        # 2. 同値ネックライン（複数日の low が同値 100.0 のとき最初の日が採用される）
        tie_rows = [
            (100, 102, 98, 101),
            (105, 108, 103, 107),
            (110, 115, 108, 114),
            (115, 120, 114, 118),  # 山1 (idx 3)
            (108, 112, 104, 106),
            (102, 105, 100, 102),  # ネック同値1 (idx 5)
            (102, 105, 100, 103),  # ネック同値2 (idx 6)
            (108, 114, 105, 113),
            (114, 118, 112, 117),
            (116, 119.5, 115, 117),# 山2 (idx 9)
            (112, 115, 108, 110),
            (105, 108, 102, 104),
            (101, 103, 99, 100),
            (99, 100, 95, 98.0),
            (98, 99, 94, 97.0),
        ]
        b_tie, i_tie = to_bars(tie_rows)
        res_tie = self.pattern_detector.detect(b_tie, i_tie)
        self.assertGreater(len(res_tie), 0)
        self.assertEqual(res_tie[-1].metadata["neck_date"], b_tie[5].date)

        # 3. 価格差 2.5% 境界（2.5% ちょうどは採用、2.51% は除外）
        rows_exact_25 = [
            (80, 82, 78, 80),
            (85, 88, 84, 86),
            (90, 95, 89, 93),
            (96, 100.0, 94, 97),     # 山1 (idx 3)
            (92, 94, 88, 90),
            (88, 90, 85.0, 87),      # ネック (idx 5, low=85.0)
            (90, 92, 87, 91),
            (94, 96, 92, 95),
            (96, 99, 94, 98),
            (99, 102.5, 97, 100),    # 山2 (idx 9): |100 - 102.5| / 100 = 0.025
            (95, 98, 92, 94),
            (90, 94, 88, 89),
            (86, 89, 84, 86),
            (83, 85, 81, 82),
            (81, 83, 79, 80),
        ]
        b_ok, i_ok = to_bars(rows_exact_25)
        self.assertGreater(len(self.pattern_detector.detect(b_ok, i_ok)), 0)

        rows_over_25 = list(rows_exact_25)
        rows_over_25[9] = (99, 102.51, 97, 100)  # 0.0251 > 0.025
        b_ng, i_ng = to_bars(rows_over_25)
        self.assertEqual(self.pattern_detector.detect(b_ng, i_ng), [])

        # 4. フラット極値（連続同値は厳密 > のため山にならず未検出）
        flat_rows = list(tie_rows)
        flat_rows[3] = (115, 120.0, 114, 118)
        flat_rows[4] = (115, 120.0, 114, 118)
        b_flat, i_flat = to_bars(flat_rows)
        self.assertEqual(self.pattern_detector.detect(b_flat, i_flat), [])

        # 5. e1_val == 0 でも ZeroDivisionError にならずスキップされる
        zero_rows = list(tie_rows)
        zero_rows[3] = (0, 0.0, 0, 0)
        b_zero, i_zero = to_bars(zero_rows)
        self.assertEqual(self.pattern_detector.detect(b_zero, i_zero), [])

    def test_lookback_window_60_boundary_and_target_indices_consistency(self):
        """60日ウィンドウ境界（e1_idx >= i - 60 で検出、i - 61 で除外）と全履歴/単一日一致を検証"""
        base = date(2025, 1, 1)
        bars = []
        # 0..9: 上昇トレンド（極値を作らない単調増加）
        for idx in range(10):
            p = 80.0 + idx * 2.0
            bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=idx), open=p, high=p + 1.0, low=p - 1.0, close=p, volume=1000))
        # idx 10: 山1 (high=120.0)
        bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=10), open=118.0, high=120.0, low=116.0, close=118.0, volume=1000))
        # 11..14: 下落してネック形成
        for idx, p in enumerate([115.0, 110.0, 105.0, 101.0], start=11):
            bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=idx), open=p, high=p + 1.0, low=p - 1.0, close=p, volume=1000))
        # idx 15: ネック (low=98.0)
        bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=15), open=100.0, high=102.0, low=98.0, close=100.0, volume=1000))
        # 16..19: 上昇
        for idx, p in enumerate([105.0, 110.0, 114.0, 117.0], start=16):
            bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=idx), open=p, high=p + 1.0, low=p - 1.0, close=p, volume=1000))
        # idx 20: 山2 (high=119.5)
        bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=20), open=117.0, high=119.5, low=116.0, close=117.0, volume=1000))
        # 21..75: 単調微減（新たな極値を作らず、ネック98.0を下抜けた状態を維持）
        for idx in range(21, 76):
            p = 115.0 - (idx - 21) * 0.5
            bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=idx), open=p, high=p + 1.0, low=p - 1.0, close=p - 0.2, volume=1000))

        inds = [IndicatorSetModel(symbol=self.symbol, date=b.date, indicators={}) for b in bars]

        all_results = self.pattern_detector.detect(bars, inds, target_indices=None)
        detected_dates = {r.metadata["date"] for r in all_results}

        # i=70 (70 - 60 = 10 == e1_idx) はウィンドウ内なので検出される
        self.assertIn(bars[70].date, detected_dates)
        # i=71 (71 - 60 = 11 > e1_idx) はウィンドウ外なので除外される
        self.assertNotIn(bars[71].date, detected_dates)

        # target_indices=[70] / [71] の単一日評価が全履歴結果と完全一致する
        res_70 = self.pattern_detector.detect(bars, inds, target_indices=[70])
        res_71 = self.pattern_detector.detect(bars, inds, target_indices=[71])
        expected_70 = [r for r in all_results if r.metadata["date"] == bars[70].date]
        self.assertEqual(res_70, expected_70)
        self.assertEqual(res_71, [])

if __name__ == '__main__':
    unittest.main()
