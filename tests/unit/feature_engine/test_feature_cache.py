import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

import src.feature_engine  # レジストリ登録
from src.common.storage import StorageManager
from src.feature_engine.manager import FeatureManager, calculate_features, feature_manager
from src.indicator_calculator.calculator import IndicatorCalculator
from src.model.data_models import FinancialModel, OhlcvModel


def _make_ohlcv(symbol: str, start: date, days: int = 30) -> list[OhlcvModel]:
    bars: list[OhlcvModel] = []
    for i in range(days):
        close = 1000.0 + i * 10.0
        bars.append(
            OhlcvModel(
                symbol=symbol,
                date=start + timedelta(days=i),
                open=close - 5.0,
                high=close + 10.0,
                low=close - 10.0,
                close=close,
                volume=100_000 + i * 1000,
            )
        )
    return bars


def _make_financial(symbol: str, roe: float = 12.0) -> FinancialModel:
    return FinancialModel(
        symbol=symbol,
        fiscal_date=date(2025, 3, 31),
        eps=100.0,
        bps=1000.0,
        roe=roe,
        roa=6.0,
        per=12.0,
        pbr=1.2,
        revenue=20_000_000_000.0,
        operating_profit=2_000_000_000.0,
        net_profit=1_400_000_000.0,
        revenue_growth=10.0,
        net_profit_growth=15.0,
        equity_ratio=45.0,
    )


class TestFeatureCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = StorageManager(base_dir=self.temp_dir.name)
        self.manager = FeatureManager()
        self.manager.storage = self.storage

        self.ind_calc = IndicatorCalculator()
        self.ind_calc.storage = self.storage

        self.symbol = "7203.T"
        self.ohlcv = _make_ohlcv(self.symbol, date(2025, 1, 1), days=30)
        self.indicators = self.ind_calc.calculate_indicators(self.ohlcv, use_cache=False)
        self.fin = _make_financial(self.symbol, roe=12.0)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_saves_new_format_and_hits_cache(self):
        """新フォーマット(meta + items)で保存され、同一入力ではキャッシュヒットする"""
        first = self.manager.calculate_features(
            self.ohlcv,
            self.indicators,
            financial_data=self.fin,
            feature_ids=["F001_ProfitabilityScore"],
        )
        self.assertEqual(len(first), len(self.ohlcv))

        cache_path = "cache/features_7203.T_F001_ProfitabilityScore.json"
        raw = self.storage.load_json(cache_path)
        self.assertIsInstance(raw, dict)
        self.assertIn("meta", raw)
        self.assertIn("items", raw)
        self.assertEqual(raw["meta"]["dates"], [o.date.isoformat() for o in self.ohlcv])
        self.assertEqual(raw["meta"]["financial_signature"], self.fin.model_dump(mode="json"))

        # 2回目はキャッシュヒットし特徴量インスタンスの calculate が呼ばれない
        with patch.object(
            self.manager.registry.get_feature("F001_ProfitabilityScore"),
            "calculate",
            side_effect=AssertionError("キャッシュヒット時は再計算されないはず"),
        ):
            second = self.manager.calculate_features(
                self.ohlcv,
                self.indicators,
                financial_data=self.fin,
                feature_ids=["F001_ProfitabilityScore"],
            )
        self.assertEqual(len(second), len(first))
        self.assertAlmostEqual(second[-1].results[0].score, first[-1].results[0].score)

    def test_cache_miss_on_date_mismatch(self):
        """日付列が一致しない場合はキャッシュミスとして再計算する"""
        self.manager.calculate_features(
            self.ohlcv,
            self.indicators,
            financial_data=self.fin,
            feature_ids=["M001_MAAlignmentScore"],
        )

        shifted_ohlcv = _make_ohlcv(self.symbol, date(2025, 2, 1), days=30)
        shifted_ind = self.ind_calc.calculate_indicators(shifted_ohlcv, use_cache=False)
        res = self.manager.calculate_features(
            shifted_ohlcv,
            shifted_ind,
            financial_data=self.fin,
            feature_ids=["M001_MAAlignmentScore"],
        )
        self.assertEqual(res[0].date, date(2025, 2, 1))

    def test_cache_miss_on_financial_data_change(self):
        """financial_data が変更された場合はキャッシュミスとして再計算・更新する"""
        first = self.manager.calculate_features(
            self.ohlcv,
            self.indicators,
            financial_data=self.fin,
            feature_ids=["F001_ProfitabilityScore"],
        )
        fin_updated = _make_financial(self.symbol, roe=25.0)
        second = self.manager.calculate_features(
            self.ohlcv,
            self.indicators,
            financial_data=fin_updated,
            feature_ids=["F001_ProfitabilityScore"],
        )
        self.assertNotAlmostEqual(
            first[-1].results[0].raw_value,
            second[-1].results[0].raw_value,
        )

        # None への変更でもミスになること
        third = self.manager.calculate_features(
            self.ohlcv,
            self.indicators,
            financial_data=None,
            feature_ids=["F001_ProfitabilityScore"],
        )
        self.assertIsNone(
            self.storage.load_json("cache/features_7203.T_F001_ProfitabilityScore.json")[
                "meta"
            ]["financial_signature"]
        )
        self.assertEqual(len(third), len(self.ohlcv))

    def test_legacy_list_cache_is_invalidated_and_overwritten(self):
        """旧リスト形式のキャッシュはミス扱いとなり、新形式で上書きされる"""
        cache_path = "cache/features_7203.T_F001_ProfitabilityScore.json"
        legacy_payload = [
            {
                "symbol": self.symbol,
                "date": o.date.isoformat(),
                "results": [],
            }
            for o in self.ohlcv
        ]
        self.storage.save_json(legacy_payload, cache_path)

        res = self.manager.calculate_features(
            self.ohlcv,
            self.indicators,
            financial_data=self.fin,
            feature_ids=["F001_ProfitabilityScore"],
        )
        self.assertEqual(len(res), len(self.ohlcv))
        self.assertGreater(len(res[-1].results), 0)

        saved = self.storage.load_json(cache_path)
        self.assertIsInstance(saved, dict)
        self.assertIn("meta", saved)
        self.assertIn("items", saved)

    def test_cache_key_suffix_and_use_cache_false(self):
        """cache_key_suffix による分離と use_cache=False の読み書きスキップを確認"""
        self.manager.calculate_features(
            self.ohlcv,
            self.indicators,
            financial_data=self.fin,
            feature_ids=["F001_ProfitabilityScore"],
            cache_key_suffix="asof_2025-01-30",
        )
        suffixed_file = (
            self.storage.base_dir
            / "cache/features_7203.T_F001_ProfitabilityScore_asof_2025-01-30.json"
        )
        default_file = (
            self.storage.base_dir / "cache/features_7203.T_F001_ProfitabilityScore.json"
        )
        self.assertTrue(suffixed_file.exists())
        self.assertFalse(default_file.exists())

        # use_cache=False は読み込みも書き込みもしない
        self.manager.calculate_features(
            self.ohlcv,
            self.indicators,
            financial_data=self.fin,
            feature_ids=["F001_ProfitabilityScore"],
            use_cache=False,
            cache_key_suffix="nocache",
        )
        nocache_file = (
            self.storage.base_dir
            / "cache/features_7203.T_F001_ProfitabilityScore_nocache.json"
        )
        self.assertFalse(nocache_file.exists())

    def test_module_level_calculate_features_forwards_args(self):
        """モジュールレベル calculate_features が use_cache / cache_key_suffix を引き継ぐ"""
        orig_storage = feature_manager.storage
        try:
            feature_manager.storage = self.storage
            res = calculate_features(
                self.ohlcv,
                self.indicators,
                financial_data=self.fin,
                feature_ids=["F001_ProfitabilityScore"],
                use_cache=True,
                cache_key_suffix="mod_asof",
            )
            self.assertEqual(len(res), len(self.ohlcv))
            expected_path = (
                self.storage.base_dir
                / "cache/features_7203.T_F001_ProfitabilityScore_mod_asof.json"
            )
            self.assertTrue(expected_path.exists())
        finally:
            feature_manager.storage = orig_storage


if __name__ == "__main__":
    unittest.main()
