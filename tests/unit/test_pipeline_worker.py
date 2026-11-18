from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from src.common.storage import StorageManager
from src.config.screening_config import AtlasScreeningConfig
from src.pipeline_worker import (
    _WORKER_STATE,
    init_pipeline_worker,
    process_batch_symbol_task,
    process_symbol_task,
)


class TestPipelineWorker(unittest.TestCase):
    def tearDown(self):
        _WORKER_STATE.clear()

    def test_uninitialized_worker_tasks_return_error_without_raising(self):
        """未初期化状態で process_symbol_task / process_batch_symbol_task を呼んでも例外にせずエラーを返す"""
        _WORKER_STATE.clear()

        res_single = process_symbol_task({"symbol": "7203.T"})
        self.assertFalse(res_single["ok"])
        self.assertEqual(res_single["symbol"], "7203.T")
        self.assertIn("初期化されていません", res_single["error"])

        res_batch = process_batch_symbol_task({"symbol": "7203.T"})
        self.assertFalse(res_batch["ok"])
        self.assertEqual(res_batch["symbol"], "7203.T")
        self.assertIn("初期化されていません", res_batch["error"])

    def test_init_pipeline_worker_uses_injected_storage_and_runs_read_only(self):
        """init_pipeline_worker が注入ストレージを使用し、読取専用で単一/一括タスクを実行できる"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            storage = StorageManager(base_dir=tmp_path)
            start = date(2025, 1, 1)
            dates = [start + timedelta(days=i) for i in range(90)]
            df = pd.DataFrame(
                [
                    {
                        "date": d,
                        "open": 1000.0 + i * 2.0,
                        "high": 1010.0 + i * 2.0,
                        "low": 995.0 + i * 2.0,
                        "close": 1005.0 + i * 2.0,
                        "volume": 300_000,
                    }
                    for i, d in enumerate(dates)
                ]
            )
            storage.save_parquet(df, "price/7203.T.parquet")
            storage.save_json(
                {"item": {"7203": ["2025/03", "90000", "0", "0", "0", "0", "0", "1200.0", "45.0"]}},
                "financial/0025-fy-balance-sheet.json",
            )
            storage.save_json(
                {"item": {"7203": ["2025/03", "50000000000", "5000000000", "5200000000", "3500000000", "150.0", "15.0", "8.0"]}},
                "financial/0025-fy-profit-and-loss.json",
            )

            irbank_local = tmp_path / "irbank_local"
            irbank_user = tmp_path / "irbank_user"
            irbank_local.mkdir(parents=True, exist_ok=True)
            irbank_user.mkdir(parents=True, exist_ok=True)

            config = AtlasScreeningConfig()
            with patch("src.data_collector.collector.os.makedirs") as mock_makedirs:
                init_pipeline_worker(
                    config.model_dump(mode="json"),
                    storage_base_dir=str(tmp_path),
                    irbank_cache_dir=str(tmp_path / "cache"),
                    local_irbank_dir=str(irbank_local),
                    user_irbank_dir=str(irbank_user),
                )
            # create_dirs=False のため DataCollector 側で不要な mkdir が走らない
            mock_makedirs.assert_not_called()
            self.assertEqual(_WORKER_STATE["collector"].storage.base_dir, tmp_path)
            self.assertEqual(_WORKER_STATE["indicator_calculator"].storage.base_dir, tmp_path)
            self.assertEqual(_WORKER_STATE["feature_manager"].storage.base_dir, tmp_path)

            res_single = process_symbol_task(
                {
                    "symbol": "7203.T",
                    "effective_start": dates[0],
                    "fetch_end": dates[-1],
                    "fetch_as_of": dates[-1],
                    "as_of_date": dates[-1],
                    "effective_fiscal_year": 2025,
                    "should_check_liquidity": False,
                    "use_bulk_eval_ohlcv": False,
                    "use_cache": True,
                    "use_feature_cache": True,
                    "cache_key_suffix": f"asof_{dates[-1].isoformat()}",
                }
            )
            self.assertTrue(res_single["ok"])
            self.assertEqual(len(res_single["score_results"]), 1)

            res_batch = process_batch_symbol_task(
                {
                    "symbol": "7203.T",
                    "symbol_dates": [dates[-10], dates[-1]],
                    "global_start": dates[0],
                    "global_eval_end": dates[-1],
                    "fiscal_year": 2025,
                    "lookback_days": 365,
                    "should_check_liquidity": False,
                    "use_cache": True,
                    "use_feature_cache": True,
                }
            )
            self.assertTrue(res_batch["ok"])
            self.assertEqual(sorted(res_batch["per_date_outputs"].keys()), [dates[-10], dates[-1]])
            # 読取専用のため cache/ 配下へ JSON ファイルは一切書き込まれない
            self.assertEqual(list((tmp_path / "cache").glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
