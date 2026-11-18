
import unittest
from datetime import date, timedelta
from typing import List, Dict, Any
from unittest.mock import patch
import math
import pandas as pd

import src.pattern_detector
from src.pattern_detector.interfaces import IPattern
from src.pattern_detector.manager import PatternManager, detect_patterns
from src.pattern_detector.patterns.candlestick import HammerPattern
from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternResultModel

class TestHammerPattern(unittest.TestCase):

    def setUp(self):
        self.pattern_detector = HammerPattern()
        self.symbol = "TEST"

    def test_pattern_properties(self):
        self.assertEqual(self.pattern_detector.pattern_id, "P001_Hammer")
        self.assertEqual(self.pattern_detector.pattern_name, "ハンマー")
        self.assertEqual(self.pattern_detector.pattern_category, "Candlestick")

    def test_detect_valid_hammer(self):
        # 典型的なハンマーパターンデータ
        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=102, low=90, close=101, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=95, high=100, low=80, close=98, volume=1500), # ハンマー
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={}) for _ in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], PatternResultModel)
        self.assertEqual(results[0].pattern_id, self.pattern_detector.pattern_id)
        self.assertGreaterEqual(results[0].confidence, 0)
        self.assertLessEqual(results[0].confidence, 100)
        self.assertEqual(results[0].metadata["date"], date(2025, 1, 2))

    def test_detect_no_hammer(self):
        # ハンマーではないデータ（長い上ヒゲ）
        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=110, low=95, close=101, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=95, high=110, low=96, close=97, volume=1500), # 上ヒゲが長い
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={}) for _ in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        self.assertEqual(len(results), 0)

    def test_detect_inverted_hammer(self):
        # 逆ハンマー（下ヒゲが短い）
        ohlcv_data = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=100, high=110, low=98, close=101, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=95, high=110, low=90, close=97, volume=1500), # 逆ハンマー
        ]
        indicator_data = [IndicatorSetModel(symbol=self.symbol, date=date(2025, 1, 1), indicators={}) for _ in ohlcv_data]

        results = self.pattern_detector.detect(ohlcv_data, indicator_data)
        self.assertEqual(len(results), 0) # ハンマーとしては検出されない

    def test_detect_empty_data(self):
        results = self.pattern_detector.detect([], [])
        self.assertEqual(len(results), 0)

    def test_calculate_confidence(self):
        # 理想的なハンマー
        conf1 = self.pattern_detector._calculate_confidence({"body": 1, "lower_shadow": 5, "upper_shadow": 0.1, "open": 100})
        self.assertGreater(conf1, 80)
        
        # 下ヒゲは長いが上ヒゲも少しある
        conf2 = self.pattern_detector._calculate_confidence({"body": 1, "lower_shadow": 3, "upper_shadow": 1, "open": 100})
        self.assertLess(conf2, conf1)
        self.assertGreater(conf2, 50)

        # 実体なし、下ヒゲあり
        conf3 = self.pattern_detector._calculate_confidence({"body": 0, "lower_shadow": 10, "upper_shadow": 0, "open": 100})
        self.assertEqual(conf3, 100.0) # bodyが0でも高信頼度

    def test_hammer_target_indices_and_manager_latest_only(self):
        """HammerPattern と PatternManager.detect_patterns の latest_only / target_indices 対応"""
        bars = [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 1), open=95, high=100, low=80, close=98, volume=1500),  # ハンマー
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 2), open=100, high=102, low=98, close=101, volume=1000),
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 3), open=95, high=100, low=80, close=98, volume=1500),  # ハンマー
        ]
        inds = [IndicatorSetModel(symbol=self.symbol, date=b.date, indicators={}) for b in bars]

        # target_indices=[2] なら最終日のみ検出
        res_last = self.pattern_detector.detect(bars, inds, target_indices=[-1])
        self.assertEqual([r.metadata["date"] for r in res_last], [date(2025, 1, 3)])

        # PatternManager で全パターン latest_only=True と latest_only=False の最終日一致確認
        full_bars = []
        base = date(2025, 1, 1)
        for i in range(30):
            wave = 100.0 + 10.0 * math.sin(i * 0.45)
            full_bars.append(
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
        # 最終日をハンマーにする
        full_bars[-1] = OhlcvModel(
            symbol=self.symbol,
            date=base + timedelta(days=29),
            open=95.0,
            high=100.0,
            low=80.0,
            close=98.0,
            volume=1500,
        )
        full_inds = [IndicatorSetModel(symbol=self.symbol, date=b.date, indicators={}) for b in full_bars]

        all_sets = detect_patterns(full_bars, full_inds, latest_only=False)
        latest_sets = detect_patterns(full_bars, full_inds, latest_only=True)
        latest_date = full_bars[-1].date
        expected_latest = [ps for ps in all_sets if ps.date == latest_date]
        self.assertEqual(latest_sets, expected_latest)
        self.assertEqual(len(latest_sets), 1)
        self.assertEqual(latest_sets[0].date, latest_date)

        # target_indices 非対応のカスタムパターンに対するフォールバックフィルタ
        class LegacyPattern(IPattern):
            pattern_id = "LEGACY_P"
            pattern_name = "レガシー"
            pattern_category = "Custom"

            def detect(self, ohlcv_data, indicator_data):
                return [
                    PatternResultModel(
                        pattern_id=self.pattern_id,
                        pattern_name=self.pattern_name,
                        confidence=80.0,
                        metadata={"date": b.date},
                    )
                    for b in ohlcv_data
                ]

            def _calculate_confidence(self, props):
                return 80.0

        mgr = PatternManager()
        with patch.object(mgr.registry, "get_pattern", return_value=LegacyPattern()):
            filtered = mgr.detect_patterns(
                bars, inds, pattern_ids=["LEGACY_P"], latest_only=True
            )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].date, date(2025, 1, 3))

        # ohlcv_data と indicator_data の長さ不一致時、共通長最終日で評価される
        long_bars = bars + [
            OhlcvModel(symbol=self.symbol, date=date(2025, 1, 4), open=95, high=100, low=80, close=98, volume=1500)
        ]
        res_mismatch = detect_patterns(
            long_bars, inds, pattern_ids=["P001_Hammer"], latest_only=True
        )
        self.assertEqual(len(res_mismatch), 1)
        self.assertEqual(res_mismatch[0].date, date(2025, 1, 3))

if __name__ == '__main__':
    unittest.main()
