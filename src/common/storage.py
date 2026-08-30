"""
ストレージ共通ユーティリティ (Parquet, JSON, キャッシュ管理)
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union
import pandas as pd

from src.common.exceptions import DataCollectorError
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

        # 必要なディレクトリの作成
        for d in [self.price_dir, self.financial_dir, self.cache_dir]:
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
            raise DataCollectorError(f"Failed to save parquet: {e}")

    def load_parquet(self, file_path: Union[str, Path]) -> Optional[pd.DataFrame]:
        """ParquetファイルからDataFrameを読み込む"""
        try:
            path = Path(file_path)
            if not path.is_absolute():
                path = self.base_dir / path
            if not path.exists():
                logger.debug(f"Parquetファイルが存在しません: {path}")
                return None
            df = pd.read_parquet(path)
            logger.info(f"Parquetファイルを読み込みました: {path}")
            return df
        except Exception as e:
            logger.error(f"Parquetファイルの読み込みに失敗しました ({file_path}): {e}")
            raise DataCollectorError(f"Failed to load parquet: {e}")

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
            raise DataCollectorError(f"Failed to save json: {e}")

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
            logger.info(f"JSONファイルを読み込みました: {path}")
            return data
        except Exception as e:
            logger.error(f"JSONファイルの読み込みに失敗しました ({file_path}): {e}")
            raise DataCollectorError(f"Failed to load json: {e}")
