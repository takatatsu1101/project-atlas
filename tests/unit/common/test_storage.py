"""
ストレージ共通ユーティリティの単体テスト
"""

import tempfile
from pathlib import Path
import pandas as pd
import pytest

from src.common.storage import StorageManager
from src.common.exceptions import DataCollectorError

@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield StorageManager(base_dir=tmpdir)

def test_parquet_save_and_load(temp_storage):
    df = pd.DataFrame({
        "Open": [100.0, 101.0],
        "Close": [102.0, 103.0]
    }, index=pd.to_datetime(["2026-01-01", "2026-01-02"]))

    file_rel_path = "price/test_stock.parquet"
    temp_storage.save_parquet(df, file_rel_path)

    loaded_df = temp_storage.load_parquet(file_rel_path)
    assert loaded_df is not None
    assert len(loaded_df) == 2
    assert "Close" in loaded_df.columns

def test_parquet_not_found(temp_storage):
    loaded_df = temp_storage.load_parquet("price/non_existent.parquet")
    assert loaded_df is None

def test_json_save_and_load(temp_storage):
    data = {"ticker": "7203", "name": "トヨタ自動車", "profit": 1000000}
    file_rel_path = "financial/7203.json"
    
    temp_storage.save_json(data, file_rel_path)

    loaded_data = temp_storage.load_json(file_rel_path)
    assert loaded_data is not None
    assert loaded_data["ticker"] == "7203"
    assert loaded_data["profit"] == 1000000

def test_json_not_found(temp_storage):
    loaded_data = temp_storage.load_json("financial/non_existent.json")
    assert loaded_data is None
