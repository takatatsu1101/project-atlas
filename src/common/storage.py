"""
ストレージ共通ユーティリティ (Parquet, JSON, キャッシュ管理)
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union
import pandas as pd

from src.common.exceptions import DataCollectionError
from src.common.logger import get_logger

logger = get_logger(__name__)

class StorageManager:
    """ローカルファイルストレージ（Parquet, JSON）およびキャッシュの管理を行うクラス"""

    def __init__(self, base_dir: Optional[Union[str, Path]] = None):
        if base_dir is None:
            # デフォルトはプロジェクトルート配下の data/
            self.base_dir = Path(__file__).resolve().parent.parent.parent / "data"
        else:
            self.base_dir = Path(base_dir)

        self.price_dir = self.base_dir / "price"
        self.financial_dir = self.base_dir / "financial"
        self.cache_dir = self.base_dir / "cache"
        self.master_dir = self.base_dir / "master"

        # 必要なディレクトリの作成
        for d in [self.price_dir, self.financial_dir, self.cache_dir, self.master_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def save_parquet(self, df: pd.DataFrame, file_path: Union[str, Path]) -> None:
        """DataFrameをParquet形式で保存する"""
        try:
            path = Path(file_path)
            if not path.is_absolute():
                path = self.base_dir / path
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path, index=True)
            logger.info(f"Parquetファイルを保存しました: {path}")
        except Exception as e:
            logger.error(f"Parquetファイルの保存に失敗しました ({file_path}): {e}")
            raise DataCollectionError(f"Failed to save parquet: {e}")

    @staticmethod
    def _is_missing_column_error(exc: Exception) -> bool:
        """
        指定列が Parquet スキーマに存在しないことによる例外かを判定する。
        （pyarrow.lib.ArrowInvalid の 'No match for FieldRef' や KeyError 等を対象とし、
        ファイル破損等による ArrowInvalid / OSError はフォールバックさせない）
        """
        if isinstance(exc, KeyError):
            return True
        msg = str(exc).lower()
        return (
            "no match for fieldref" in msg
            or "not in index" in msg
            or "not present in" in msg
            or ("column" in msg and ("not found" in msg or "does not exist" in msg))
        )

    def load_parquet(
        self,
        file_path: Union[str, Path],
        columns: Optional[Sequence[str]] = None,
    ) -> Optional[pd.DataFrame]:
        """
        ParquetファイルからDataFrameを読み込む。
        - columns 指定時は列限定読込を行い、一部不在列によるエラー時のみ全列読込へフォールバックする。
        - columns に空シーケンス（[]）が指定された場合は（ファイルが存在すれば）空の DataFrame を返す。
        """
        try:
            path = Path(file_path)
            if not path.is_absolute():
                path = self.base_dir / path
            if not path.exists():
                logger.debug(f"Parquetファイルが存在しません: {path}")
                return None

            if columns is not None:
                cols_list = list(columns)
                if not cols_list:
                    return pd.DataFrame(columns=[])
                try:
                    df = pd.read_parquet(path, columns=cols_list)
                except Exception as col_err:
                    if not self._is_missing_column_error(col_err):
                        raise
                    logger.debug(
                        f"Parquet列限定読込に一部不在列が含まれるため全列読込へフォールバックします ({path}): {col_err}"
                    )
                    df = pd.read_parquet(path)
            else:
                df = pd.read_parquet(path)

            logger.info(f"Parquetファイルを読み込みました: {path}")
            return df
        except Exception as e:
            logger.error(f"Parquetファイルの読み込みに失敗しました ({file_path}): {e}")
            raise DataCollectionError(f"Failed to load parquet: {e}")

    def save_json(self, data: Any, file_path: Union[str, Path]) -> None:
        """データをJSON形式で保存する"""
        try:
            path = Path(file_path)
            if not path.is_absolute():
                path = self.base_dir / path
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info(f"JSONファイルを保存しました: {path}")
        except Exception as e:
            logger.error(f"JSONファイルの保存に失敗しました ({file_path}): {e}")
            raise DataCollectionError(f"Failed to save json: {e}")

    def load_json(self, file_path: Union[str, Path]) -> Optional[Any]:
        """JSONファイルからデータを読み込む"""
        try:
            path = Path(file_path)
            if not path.is_absolute():
                path = self.base_dir / path
            if not path.exists():
                logger.debug(f"JSONファイルが存在しません: {path}")
                return None
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.debug(f"JSONファイルを読み込みました: {path}")
            return data
        except Exception as e:
            logger.error(f"JSONファイルの読み込みに失敗しました ({file_path}): {e}")
            raise DataCollectionError(f"Failed to load json: {e}")
