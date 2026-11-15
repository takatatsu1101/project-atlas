"""
東証上場銘柄マスタ管理モジュール
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import pandas as pd

from src.common.exceptions import DataCollectionError
from src.common.logger import get_logger
from src.common.storage import StorageManager
from src.model.data_models import StockMasterModel

logger = get_logger(__name__)

# JPX 日本語列名と内部フィールド名のマッピング
_JPX_COLUMN_MAP: Dict[str, str] = {
    "コード": "code",
    "銘柄名": "name",
    "市場・商品区分": "market",
    "33業種区分": "sector_33",
    "17業種区分": "sector_17",
    "規模区分": "scale",
}

_DEFAULT_MASTER_FILENAMES = (
    "tse_listed_stocks.parquet",
    "tse_listed_stocks.json",
    "tse_listed_stocks.csv",
)

_SUPPORTED_EXTENSIONS = (".parquet", ".json", ".csv")


def normalize_market_name(market: str) -> str:
    """
    市場区分名を正規化する。
    例: "プライム（内国株式）" -> "プライム"
    """
    if not market:
        return ""
    cleaned = re.sub(r"[（(].*?[）)]", "", str(market)).strip()
    return cleaned if cleaned else str(market).strip()


def _clean_optional_str(value: Any) -> Optional[str]:
    """欠損値やハイフンを None に正規化する"""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    if text == "" or text == "-" or text.lower() == "nan":
        return None
    return text


class MasterManager:
    """東証上場銘柄マスタの読み込み・保存を管理するクラス"""

    def __init__(self, storage: Optional[StorageManager] = None):
        self.storage = storage or StorageManager()

    def _resolve_default_master_path(self) -> Optional[Path]:
        """data/master/ 配下からデフォルトのマスタファイルを探索する"""
        master_dir = self.storage.master_dir
        if not master_dir.exists():
            return None

        for filename in _DEFAULT_MASTER_FILENAMES:
            candidate = master_dir / filename
            if candidate.exists():
                return candidate

        for ext in _SUPPORTED_EXTENSIONS:
            matches = sorted(master_dir.glob(f"*{ext}"))
            if matches:
                return matches[0]

        return None

    def _read_csv_with_fallback(self, path: Path) -> pd.DataFrame:
        """UTF-8-SIG / UTF-8 / CP932 の順で CSV を読み込む"""
        last_error: Optional[Exception] = None
        for encoding in ("utf-8-sig", "utf-8", "cp932"):
            try:
                return pd.read_csv(path, dtype=str, encoding=encoding)
            except UnicodeDecodeError as e:
                last_error = e
                continue
            except Exception as e:
                raise DataCollectionError(f"銘柄マスタCSVの読み込みに失敗しました ({path}): {e}") from e

        raise DataCollectionError(f"銘柄マスタCSVの文字コード判別に失敗しました ({path}): {last_error}")

    def _records_to_models(self, records: List[Dict[str, Any]]) -> List[StockMasterModel]:
        """辞書レコードのリストを StockMasterModel のリストへ変換する"""
        models: List[StockMasterModel] = []
        for raw in records:
            # 日本語列名を英語キーへマッピング（英語キーがあればそちらを優先）
            normalized: Dict[str, Any] = {}
            for key, val in raw.items():
                mapped_key = _JPX_COLUMN_MAP.get(key, key)
                if mapped_key not in normalized or normalized[mapped_key] is None:
                    normalized[mapped_key] = val

            raw_code = _clean_optional_str(normalized.get("code"))
            name = _clean_optional_str(normalized.get("name"))
            if not raw_code or not name:
                continue

            code = re.sub(r"\.T$", "", raw_code, flags=re.IGNORECASE).upper()

            raw_symbol = _clean_optional_str(normalized.get("symbol"))
            if raw_symbol:
                symbol = raw_symbol.upper() if raw_symbol.lower().endswith(".t") else raw_symbol
            else:
                symbol = f"{code}.T"

            raw_market = _clean_optional_str(normalized.get("market")) or ""
            market = normalize_market_name(raw_market)

            models.append(
                StockMasterModel(
                    code=code,
                    symbol=symbol,
                    name=name,
                    market=market,
                    sector_33=_clean_optional_str(normalized.get("sector_33")),
                    sector_17=_clean_optional_str(normalized.get("sector_17")),
                    scale=_clean_optional_str(normalized.get("scale")),
                )
            )
        return models

    def load_master(self, file_path: Optional[Union[str, Path]] = None) -> List[StockMasterModel]:
        """
        銘柄マスタを読み込み、StockMasterModel のリストを返す。
        ファイルが存在しない場合は空リストを返す。
        """
        if file_path is None:
            target_path = self._resolve_default_master_path()
            if target_path is None:
                logger.info("銘柄マスタファイルが見つかりませんでした。")
                return []
        else:
            target_path = Path(file_path)
            if not target_path.is_absolute():
                target_path = self.storage.base_dir / target_path
            if not target_path.exists():
                logger.info(f"指定された銘柄マスタファイルが存在しません: {target_path}")
                return []

        suffix = target_path.suffix.lower()
        if suffix == ".csv":
            df = self._read_csv_with_fallback(target_path)
            records = df.to_dict(orient="records")
        elif suffix == ".json":
            data = self.storage.load_json(target_path)
            if not data:
                return []
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
                records = data["items"]
            else:
                raise DataCollectionError(f"銘柄マスタJSONの形式が不正です: {target_path}")
        elif suffix == ".parquet":
            df = self.storage.load_parquet(target_path)
            if df is None or df.empty:
                return []
            records = df.to_dict(orient="records")
        else:
            raise DataCollectionError(f"未対応のマスタファイル拡張子です: {suffix}")

        models = self._records_to_models(records)
        logger.info(f"銘柄マスタを読み込みました: {target_path} ({len(models)}件)")
        return models

    def save_master(
        self,
        stocks: List[StockMasterModel],
        file_path: Union[str, Path] = "master/tse_listed_stocks.csv",
    ) -> None:
        """
        銘柄マスタを指定形式（.csv / .json / .parquet）で保存する。
        """
        target_path = Path(file_path)
        if not target_path.is_absolute():
            target_path = self.storage.base_dir / target_path
        target_path.parent.mkdir(parents=True, exist_ok=True)

        suffix = target_path.suffix.lower()
        records = [stock.model_dump() for stock in stocks]

        if suffix == ".csv":
            columns = list(StockMasterModel.model_fields.keys())
            df = pd.DataFrame(records, columns=columns)
            df.to_csv(target_path, index=False, encoding="utf-8-sig")
            logger.info(f"銘柄マスタCSVを保存しました: {target_path} ({len(stocks)}件)")
        elif suffix == ".json":
            self.storage.save_json(records, target_path)
        elif suffix == ".parquet":
            columns = list(StockMasterModel.model_fields.keys())
            df = pd.DataFrame(records, columns=columns)
            self.storage.save_parquet(df, target_path)
        else:
            raise DataCollectionError(f"未対応のマスタファイル拡張子です: {suffix}")
