"""
ストレージ共通ユーティリティの単体テスト
"""

import tempfile
from pathlib import Path
import pandas as pd
import pytest

from src.common.storage import StorageManager
from src.common.exceptions import DataCollectionError

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


def test_parquet_load_with_columns(temp_storage):
    """columns 指定時は指定列のみが読み込まれる"""
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "open": [100.0, 101.0],
        "close": [102.0, 103.0],
        "dividends": [0.0, 10.0],
    })
    file_rel_path = "price/columns_test.parquet"
    temp_storage.save_parquet(df, file_rel_path)

    loaded = temp_storage.load_parquet(file_rel_path, columns=["date", "close"])
    assert loaded is not None
    assert list(loaded.columns) == ["date", "close"]
    assert len(loaded) == 2


def test_parquet_load_with_empty_columns_returns_empty_dataframe(temp_storage):
    """columns=[] 指定時はファイル存在時に空 DataFrame、不在時に None を返す"""
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "close": [102.0]})
    file_rel_path = "price/empty_cols_test.parquet"
    temp_storage.save_parquet(df, file_rel_path)

    loaded_empty = temp_storage.load_parquet(file_rel_path, columns=[])
    assert loaded_empty is not None
    assert loaded_empty.empty
    assert list(loaded_empty.columns) == []

    assert temp_storage.load_parquet("price/no_such_file.parquet", columns=[]) is None


def test_parquet_load_with_missing_column_fallbacks_to_full_read(temp_storage):
    """旧ファイル等で一部列が存在しない場合のみ全列読込へフォールバックする"""
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "close": [102.0, 103.0],
    })
    file_rel_path = "price/legacy_columns.parquet"
    temp_storage.save_parquet(df, file_rel_path)

    loaded = temp_storage.load_parquet(
        file_rel_path, columns=["date", "close", "non_existent_col"]
    )
    assert loaded is not None
    assert set(["date", "close"]).issubset(loaded.columns)
    assert len(loaded) == 2


def test_parquet_load_corrupt_file_raises_data_collection_error(temp_storage, monkeypatch):
    """ファイル破損等の真のエラー時はフォールバックせず DataCollectionError を送出する"""
    bad_path = temp_storage.price_dir / "corrupt.parquet"
    bad_path.write_bytes(b"not a valid parquet file")

    with pytest.raises(DataCollectionError):
        temp_storage.load_parquet(bad_path, columns=["date", "close"])

    # 非列不在の OSError モック時は全列フォールバックしないことも確認
    call_count = {"n": 0}

    def raise_oserror(*args, **kwargs):
        call_count["n"] += 1
        raise OSError("corrupt disk sector")

    monkeypatch.setattr(pd, "read_parquet", raise_oserror)
    with pytest.raises(DataCollectionError):
        temp_storage.load_parquet(bad_path, columns=["date", "close"])
    assert call_count["n"] == 1
