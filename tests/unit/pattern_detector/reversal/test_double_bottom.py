import math
import time
import unittest
from datetime import date, timedelta

from src.pattern_detector.patterns.reversal.double_bottom import DoubleBottomPattern
from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternResultModel

class TestDoubleBottomPattern(unittest.TestCase):

    def setUp(self):
        self.pattern_detector = DoubleBottomPattern()
        self.symbol = "TEST"

    def test_pattern_properties(self):
        self.assertEqual(self.pattern_detector.pattern_id, "R001_DoubleBottom")
        self.assertEqual(self.pattern_detector.pattern_name, "ダブルボトム")
        self.assertEqual(self.pattern_detector.pattern_category, "Reversal")

    def test_detect_valid_double_bottom(self):
        # 典型的なダブルボトムが形成される16日分のOHLCVデータを構成
        # 1〜3日：下降
        # 4日目：谷1（底値80.0）
        # 5〜7日：一時反発
        # 8日目：ネックライン（高値100.0）
        # 9〜11日：再び下落
        # 12日目：谷2（底値80.5。谷1から0.6%の差）
        # 13〜15日：反発上昇
        # 16日目：ネックライン上抜け（終値102.0）
        prices = [
            (100, 102, 98, 99),   # 1
            (95, 97, 92, 93),     # 2
            (90, 92, 85, 86),     # 3
            (82, 85, 80, 81),     # 4 (谷1: index 3)
            (85, 90, 84, 88),     # 5
            (90, 95, 88, 93),     # 6
            (95, 98, 93, 96),     # 7
            (98, 100, 95, 97),    # 8 (ネック: index 7)
            (95, 97, 90, 92),     # 9
            (90, 92, 84, 85),     # 10
            (83, 85, 81, 82),     # 11
            (81, 84, 80.5, 83),   # 12 (谷2: index 11)
            (85, 90, 82, 89),     # 13
            (90, 95, 88, 94),     # 14
            (95, 100, 93, 98),    # 15
            (100, 103, 99, 102),  # 16 (終値 102.0 > ネック高 100.0 上抜け!)
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
        self.assertGreaterEqual(results[-1].confidence, 80.0) # 上抜け直後なので非常に高信頼度

    def test_detect_forming_double_bottom(self):
        # 形成途中（ネックラインに届いていないが、谷2から反発中）
        # 谷1: 80, ネック高: 100, 谷2: 80.5, 終値: 90.0 (反発中)
        prices = [
            (100, 102, 98, 99),   # 1
            (95, 97, 92, 93),     # 2
            (90, 92, 85, 86),     # 3
            (82, 85, 80, 81),     # 4 (谷1: index 3)
            (85, 90, 84, 88),     # 5
            (90, 95, 88, 93),     # 6
            (95, 98, 93, 96),     # 7
            (98, 100, 95, 97),    # 8 (ネック: index 7)
            (95, 97, 90, 92),     # 9
            (90, 92, 84, 85),     # 10
            (83, 85, 81, 82),     # 11
            (81, 84, 80.5, 83),   # 12 (谷2: index 11)
            (83, 86, 81, 84),     # 13
            (84, 88, 82, 86),     # 14
            (86, 92, 83, 90.0),   # 15 (終値 90.0 で反発上昇中。index 14)
        ]

        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, idx+1), open=p[0], high=p[1], low=p[2], close=p[3], volume=1000)
            for idx, p in enumerate(prices)
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=d.date, indicators={}) for d in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[-1].metadata["date"], date(2025, 1, 15))
        # ネックラインの下なので、完成よりは信頼度が低い
        self.assertTrue(40.0 <= results[-1].confidence <= 75.0)

    def test_broken_double_bottom(self):
        # サポート割れ（谷2の安値を割り込んで下落）
        prices = [
            (100, 102, 98, 99),   # 1
            (95, 97, 92, 93),     # 2
            (90, 92, 85, 86),     # 3
            (82, 85, 80, 81),     # 4 (谷1: index 3)
            (85, 90, 84, 88),     # 5
            (90, 95, 88, 93),     # 6
            (95, 98, 93, 96),     # 7
            (98, 100, 95, 97),    # 8 (ネック)
            (95, 97, 90, 92),     # 9
            (90, 92, 84, 85),     # 10
            (83, 85, 81, 82),     # 11
            (81, 84, 80.5, 83),   # 12 (谷2)
            (81, 83, 78, 79.0),   # 13 (サポート 80.5 を大きく割り込んで下落。不成立)
        ]

        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, idx+1), open=p[0], high=p[1], low=p[2], close=p[3], volume=1000)
            for idx, p in enumerate(prices)
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=d.date, indicators={}) for d in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        # サポートを割り込んだ日は検知されない
        if len(results) > 0:
            self.assertNotEqual(results[-1].metadata["date"], date(2025, 1, 13))

    def test_insufficient_data(self):
        # 15日未満のデータ
        results = self.pattern_detector.detect(self.ohlcv_data_insufficient if hasattr(self, 'ohlcv_data_insufficient') else [], [])
        self.assertEqual(len(results), 0)

    def _naive_double_bottom_detect(self, ohlcv_data):
        """旧 O(N^2) アルゴリズムと同等の参照実装（全日付一致検証用）"""
        results = []
        if len(ohlcv_data) < 15:
            return results
        for i in range(10, len(ohlcv_data)):
            current_close = ohlcv_data[i].close
            troughs = []
            for j in range(2, i - 2):
                low_j = ohlcv_data[j].low
                if (
                    low_j < ohlcv_data[j - 1].low
                    and low_j < ohlcv_data[j - 2].low
                    and low_j < ohlcv_data[j + 1].low
                    and low_j < ohlcv_data[j + 2].low
                ):
                    troughs.append(j)
            if len(troughs) < 2:
                continue
            v1_idx, v2_idx = troughs[-2], troughs[-1]
            v1_low, v2_low = ohlcv_data[v1_idx].low, ohlcv_data[v2_idx].low
            if abs(v1_low - v2_low) / v1_low > 0.025:
                continue
            neck_idx = v1_idx + 1
            for j in range(v1_idx + 1, v2_idx):
                if ohlcv_data[j].high > ohlcv_data[neck_idx].high:
                    neck_idx = j
            neck_high = ohlcv_data[neck_idx].high
            if current_close < min(v1_low, v2_low):
                continue
            confidence = self.pattern_detector._calculate_confidence({
                "close": current_close,
                "v2_low": v2_low,
                "neck_high": neck_high,
            })
            if confidence >= 40.0:
                results.append(PatternResultModel(
                    pattern_id=self.pattern_detector.pattern_id,
                    pattern_name=self.pattern_detector.pattern_name,
                    confidence=confidence,
                    metadata={
                        "date": ohlcv_data[i].date,
                        "v1_date": ohlcv_data[v1_idx].date,
                        "v2_date": ohlcv_data[v2_idx].date,
                        "neck_date": ohlcv_data[neck_idx].date,
                        "v1_low": v1_low,
                        "v2_low": v2_low,
                        "neck_high": neck_high,
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
                    close=wave + 1.0,
                    volume=1000,
                )
            )
        ind = [IndicatorSetModel(symbol=self.symbol, date=b.date, indicators={}) for b in bars]

        expected = self._naive_double_bottom_detect(bars)
        actual = self.pattern_detector.detect(bars, ind)
        self.assertGreater(len(expected), 0)
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            self.assertEqual(a.pattern_id, e.pattern_id)
            self.assertAlmostEqual(a.confidence, e.confidence, places=12)
            self.assertEqual(a.metadata, e.metadata)

        # target_indices（負インデックス・重複・範囲外含む）で全日付結果の該当分と一致
        detected_dates = {r.metadata["date"] for r in actual}
        target_idx = [-1, 30, 50, -1, 999, -999]
        target_dates = {bars[119].date, bars[30].date, bars[50].date}
        partial = self.pattern_detector.detect(bars, ind, target_indices=target_idx)
        expected_partial = [r for r in actual if r.metadata["date"] in target_dates]
        self.assertEqual(len(partial), len(expected_partial))
        self.assertEqual({r.metadata["date"] for r in partial}, detected_dates & target_dates)

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
                    close=wave + 2.0,
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

        # 2. 同値ネックライン（複数日の high が同値 100.0 のとき最初の日が採用される）
        tie_rows = [
            (100, 102, 98, 99),
            (95, 97, 92, 93),
            (90, 92, 85, 86),
            (82, 85, 80, 81),    # 谷1 (idx 3)
            (88, 95, 84, 90),
            (95, 100, 90, 97),   # ネック同値1 (idx 5)
            (95, 100, 90, 96),   # ネック同値2 (idx 6)
            (92, 96, 89, 93),
            (88, 92, 84, 85),
            (81, 84, 80.5, 83),  # 谷2 (idx 9)
            (85, 90, 82, 89),
            (90, 95, 88, 94),
            (95, 100, 93, 98),
            (100, 103, 99, 102),
            (101, 104, 99, 103),
        ]
        b_tie, i_tie = to_bars(tie_rows)
        res_tie = self.pattern_detector.detect(b_tie, i_tie)
        self.assertGreater(len(res_tie), 0)
        self.assertEqual(res_tie[-1].metadata["neck_date"], b_tie[5].date)

        # 3. 価格差 2.5% 境界（2.5% ちょうどは採用、2.51% は除外）
        rows_exact_25 = [
            (120, 122, 120, 121),
            (116, 118, 115, 116),
            (111, 113, 110, 111),
            (102, 105, 100.0, 101),  # 谷1 (idx 3)
            (109, 111, 108, 110),
            (113, 115, 112, 114),    # ネック (idx 5, high=115)
            (111, 113, 110, 111),
            (109, 111, 108, 109),
            (106, 108, 105, 106),
            (99, 101, 97.5, 100),    # 谷2 (idx 9): |100 - 97.5| / 100 = 0.025
            (103, 105, 102, 104),
            (109, 111, 108, 110),
            (113, 115, 112, 114),
            (116, 118, 115, 117),
            (117, 120, 116, 118),
        ]
        b_ok, i_ok = to_bars(rows_exact_25)
        self.assertGreater(len(self.pattern_detector.detect(b_ok, i_ok)), 0)

        rows_over_25 = list(rows_exact_25)
        rows_over_25[9] = (99, 101, 97.49, 100)  # 0.0251 > 0.025
        b_ng, i_ng = to_bars(rows_over_25)
        self.assertEqual(self.pattern_detector.detect(b_ng, i_ng), [])

        # 4. フラット極値（連続同値は厳密 < のため谷にならず未検出）
        flat_rows = list(tie_rows)
        flat_rows[3] = (82, 85, 80.0, 81)
        flat_rows[4] = (82, 85, 80.0, 81)
        b_flat, i_flat = to_bars(flat_rows)
        self.assertEqual(self.pattern_detector.detect(b_flat, i_flat), [])

        # 5. e1_val == 0 でも ZeroDivisionError にならずスキップされる
        zero_rows = list(tie_rows)
        zero_rows[3] = (82, 85, 0.0, 81)
        b_zero, i_zero = to_bars(zero_rows)
        self.assertEqual(self.pattern_detector.detect(b_zero, i_zero), [])

    def test_lookback_window_60_boundary_and_target_indices_consistency(self):
        """60日ウィンドウ境界（e1_idx >= i - 60 で検出、i - 61 で除外）と全履歴/単一日一致を検証"""
        base = date(2025, 1, 1)
        bars = []
        # 0..9: 下降トレンド（極値を作らない単調減少）
        for idx in range(10):
            p = 120.0 - idx * 2.0
            bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=idx), open=p, high=p + 1.0, low=p - 1.0, close=p, volume=1000))
        # idx 10: 谷1 (low=80.0)
        bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=10), open=82.0, high=84.0, low=80.0, close=82.0, volume=1000))
        # 11..14: 上昇してネック形成
        for idx, p in enumerate([85.0, 90.0, 95.0, 99.0], start=11):
            bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=idx), open=p, high=p + 1.0, low=p - 1.0, close=p, volume=1000))
        # idx 15: ネック (high=102.0)
        bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=15), open=100.0, high=102.0, low=98.0, close=100.0, volume=1000))
        # 16..19: 下降
        for idx, p in enumerate([95.0, 90.0, 86.0, 83.0], start=16):
            bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=idx), open=p, high=p + 1.0, low=p - 1.0, close=p, volume=1000))
        # idx 20: 谷2 (low=80.5)
        bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=20), open=82.0, high=84.0, low=80.5, close=82.0, volume=1000))
        # 21..75: 単調微増（新たな極値を作らず、ネック102.0を上抜けた状態を維持）
        for idx in range(21, 76):
            p = 84.0 + (idx - 21) * 0.5
            bars.append(OhlcvModel(symbol=self.symbol, date=base + timedelta(days=idx), open=p, high=p + 1.0, low=p - 1.0, close=p + 0.2, volume=1000))

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
