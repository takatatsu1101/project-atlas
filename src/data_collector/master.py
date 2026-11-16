"""
東証上場銘柄マスタ管理モジュール
"""

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin
import pandas as pd
import requests

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
_JPX_LISTED_PAGE_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


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

        existing_defaults = [
            (idx, master_dir / filename)
            for idx, filename in enumerate(_DEFAULT_MASTER_FILENAMES)
            if (master_dir / filename).exists()
        ]
        if existing_defaults:
            # 複数形式が存在する場合は更新日時が最新のファイルを優先し、同値なら parquet > json > csv
            _, best_path = max(
                existing_defaults,
                key=lambda item: (item[1].stat().st_mtime_ns, -item[0]),
            )
            return best_path

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

    @staticmethod
    def _col_letters_to_index(col_letters: str) -> int:
        """Excel 列文字（例: 'A', 'Z', 'AA'）を 0 始まりの列インデックスへ変換する"""
        idx = 0
        for ch in col_letters.upper():
            if not ("A" <= ch <= "Z"):
                raise DataCollectionError(f"不正なセル列参照です: {col_letters}")
            idx = idx * 26 + (ord(ch) - ord("A") + 1)
        return idx - 1

    @staticmethod
    def _extract_cell_ref_col_index(cell_ref: Optional[str], fallback_idx: int) -> int:
        """セル参照（例: 'C5'）から 0 始まりの列インデックスを解決する"""
        if not cell_ref:
            return fallback_idx
        match = re.match(r"^([A-Za-z]+)", cell_ref.strip())
        if not match:
            return fallback_idx
        return MasterManager._col_letters_to_index(match.group(1))

    @staticmethod
    def _local_tag(tag: str) -> str:
        """XML 名前空間を除いたローカルタグ名を返す"""
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    @classmethod
    def _extract_rst_text(cls, container: ET.Element) -> str:
        """<si> / <is> 要素からふりがな(<rPh>)を除外して本文テキストのみを抽出する"""
        parts: List[str] = []
        for child in container:
            tag = cls._local_tag(child.tag)
            if tag == "t":
                parts.append(child.text or "")
            elif tag == "r":
                for sub in child:
                    if cls._local_tag(sub.tag) == "t":
                        parts.append(sub.text or "")
        return "".join(parts)

    @classmethod
    def _read_shared_strings(cls, zf: zipfile.ZipFile) -> List[str]:
        """xl/sharedStrings.xml が存在する場合に共有文字列リストを読み込む"""
        if "xl/sharedStrings.xml" not in zf.namelist():
            return []
        try:
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        except ET.ParseError as e:
            raise DataCollectionError(f"JPX Excel の共有文字列XML解析に失敗しました: {e}") from e

        strings: List[str] = []
        for elem in root:
            if cls._local_tag(elem.tag) != "si":
                continue
            strings.append(cls._extract_rst_text(elem))
        return strings

    @classmethod
    def _resolve_worksheet_names(cls, zf: zipfile.ZipFile) -> List[str]:
        """zip 内のワークシート XML パス一覧をシート番号順で返す"""
        candidates = [
            name
            for name in zf.namelist()
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        ]
        if not candidates:
            raise DataCollectionError("JPX Excel 内にワークシートXMLが見つかりません。")

        def _sheet_sort_key(name: str) -> tuple:
            match = re.search(r"sheet(\d+)\.xml$", name)
            return (0, int(match.group(1)), name) if match else (1, 0, name)

        return sorted(candidates, key=_sheet_sort_key)

    @classmethod
    def _extract_worksheet_rows(
        cls,
        sheet_root: ET.Element,
        shared_strings: List[str],
    ) -> List[Dict[int, str]]:
        """ワークシート XML から空行を除いたセル辞書リストを抽出する"""
        rows: List[Dict[int, str]] = []
        for elem in sheet_root.iter():
            if cls._local_tag(elem.tag) != "row":
                continue

            row_cells: Dict[int, str] = {}
            next_col_idx = 0
            for cell in elem:
                if cls._local_tag(cell.tag) != "c":
                    continue

                col_idx = cls._extract_cell_ref_col_index(cell.attrib.get("r"), next_col_idx)
                next_col_idx = col_idx + 1
                cell_type = cell.attrib.get("t")

                val_text = ""
                if cell_type == "inlineStr":
                    is_elem = next(
                        (child for child in cell if cls._local_tag(child.tag) == "is"),
                        None,
                    )
                    val_text = cls._extract_rst_text(is_elem if is_elem is not None else cell)
                else:
                    v_elem = next(
                        (child for child in cell if cls._local_tag(child.tag) == "v"),
                        None,
                    )
                    raw_val = v_elem.text if v_elem is not None and v_elem.text is not None else ""
                    if cell_type == "s":
                        if raw_val == "":
                            val_text = ""
                        else:
                            try:
                                ss_idx = int(raw_val)
                                val_text = shared_strings[ss_idx]
                            except (ValueError, IndexError) as e:
                                raise DataCollectionError(
                                    f"JPX Excel の共有文字列インデックスが不正です: {raw_val}"
                                ) from e
                    else:
                        val_text = raw_val

                if val_text != "":
                    row_cells[col_idx] = val_text

            if row_cells:
                rows.append(row_cells)
        return rows

    @staticmethod
    def _is_header_row(row_cells: Dict[int, str]) -> bool:
        """コード列と銘柄名列の両方を含むヘッダー行か判定する"""
        normalized = {val.strip().lower() for val in row_cells.values() if val.strip()}
        has_code = "コード" in normalized or "code" in normalized
        has_name = "銘柄名" in normalized or "name" in normalized
        return has_code and has_name

    def fetch_jpx_master_url(
        self,
        page_url: str = _JPX_LISTED_PAGE_URL,
        timeout: int = 15,
    ) -> str:
        """
        JPX「東証上場銘柄一覧」ページから data_j.xlsx の絶対 URL を抽出して返す。
        旧 .xls 形式のみが存在する場合は DataCollectionError を送出する。
        """
        try:
            response = requests.get(page_url, headers=_REQUEST_HEADERS, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as e:
            raise DataCollectionError(f"JPX 銘柄一覧ページの取得に失敗しました ({page_url}): {e}") from e

        hrefs = re.findall(r'href=["\']([^"\']+)["\']', response.text, flags=re.IGNORECASE)
        for href in hrefs:
            if "data_j.xlsx" in href.lower():
                return urljoin(page_url, href)

        if any("data_j.xls" in href.lower() for href in hrefs):
            raise DataCollectionError(
                f"JPX 銘柄マスタの旧Excel形式(.xls)は未対応です（.xlsxのみ対応）: {page_url}"
            )

        raise DataCollectionError(
            f"JPX ページから data_j.xlsx へのリンクを抽出できませんでした ({page_url})"
        )

    def parse_jpx_xlsx(self, xlsx_bytes: bytes) -> List[StockMasterModel]:
        """
        JPX の東証上場銘柄一覧 .xlsx バイナリを標準ライブラリのみでパースし、
        StockMasterModel のリストを返す。
        """
        if not xlsx_bytes:
            raise DataCollectionError("JPX Excel データが空です。")

        try:
            with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zf:
                shared_strings = self._read_shared_strings(zf)
                sheet_names = self._resolve_worksheet_names(zf)
                target_rows: Optional[List[Dict[int, str]]] = None
                header_idx: Optional[int] = None

                for sheet_name in sheet_names:
                    try:
                        sheet_root = ET.fromstring(zf.read(sheet_name))
                    except ET.ParseError as e:
                        raise DataCollectionError(f"JPX Excel のシートXML解析に失敗しました: {e}") from e

                    rows = self._extract_worksheet_rows(sheet_root, shared_strings)
                    for idx, row_cells in enumerate(rows):
                        if self._is_header_row(row_cells):
                            target_rows = rows
                            header_idx = idx
                            break
                    if target_rows is not None:
                        break
        except zipfile.BadZipFile as e:
            raise DataCollectionError(f"不正な .xlsx バイナリです（ZIP展開失敗）: {e}") from e

        if target_rows is None or header_idx is None:
            raise DataCollectionError("JPX Excel 内に有効なヘッダー行（コード・銘柄名）が見つかりません。")

        data_rows = target_rows[header_idx + 1:]
        if not data_rows:
            raise DataCollectionError("JPX Excel にヘッダー行以降のデータ行が含まれていません。")

        header_row = target_rows[header_idx]
        headers: Dict[int, str] = {
            col_idx: val.strip()
            for col_idx, val in header_row.items()
            if val.strip()
        }

        records: List[Dict[str, Any]] = []
        for row_cells in data_rows:
            record: Dict[str, Any] = {}
            for col_idx, header_name in headers.items():
                if col_idx in row_cells:
                    record[header_name] = row_cells[col_idx]
            if record:
                records.append(record)

        models = self._records_to_models(records)
        if not models:
            raise DataCollectionError("JPX Excel から有効な銘柄レコードを抽出できませんでした。")
        return models

    def update_from_jpx(
        self,
        file_path: Optional[Union[str, Path]] = None,
        timeout: int = 15,
    ) -> List[StockMasterModel]:
        """
        JPX 公式サイトから最新の東証上場銘柄一覧（.xlsx）を取得・パースし、マスタファイルへ保存する。
        file_path 省略時は既存のデフォルトマスタ形式（存在しない場合は CSV）へ保存する。
        """
        xlsx_url = self.fetch_jpx_master_url(timeout=timeout)
        logger.info(f"JPX 銘柄マスタをダウンロード中...: {xlsx_url}")
        try:
            response = requests.get(xlsx_url, headers=_REQUEST_HEADERS, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as e:
            raise DataCollectionError(f"JPX 銘柄マスタのダウンロードに失敗しました ({xlsx_url}): {e}") from e

        models = self.parse_jpx_xlsx(response.content)
        target_path = file_path
        if target_path is None:
            target_path = self._resolve_default_master_path() or "master/tse_listed_stocks.csv"
        self.save_master(models, file_path=target_path)
        return models
