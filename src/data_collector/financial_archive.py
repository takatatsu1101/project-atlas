"""
財務キャッシュ（data/financial/*.json）の ZIP アーカイブ化・検証付き展開・Google Drive 同期モジュール

GitHub Actions 等のクラウド実行環境から IR BANK への直接アクセス（レートリミット・HTTP 302 ブロック）を
発生させないため、手元環境の財務 JSON 群を単一 ZIP（financial_data.zip）として Google Drive 経由で
安全に引き継ぐ機能を提供する。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import List, Optional, Sequence, Union
import zipfile

from src.common.logger import get_logger
from src.presentation.gemini_brief import GoogleDriveBriefDelivery

logger = get_logger(__name__)

DEFAULT_FINANCIAL_ARCHIVE_NAME: str = "financial_data.zip"
_MAX_SINGLE_JSON_BYTES: int = 100 * 1024 * 1024  # 1ファイル上限 100MB
_MAX_TOTAL_JSON_BYTES: int = 500 * 1024 * 1024  # 合計展開上限 500MB


def has_cached_financial_files(
    financial_dir: Union[str, Path] = "./data/financial",
) -> bool:
    """financial_dir 内に有効な財務 JSON ファイル（*-fy-*.json）が1件以上存在するか判定する。"""
    fin_dir = Path(financial_dir)
    if not fin_dir.is_dir():
        return False
    for path in fin_dir.glob("*.json"):
        if (
            not path.name.startswith(".")
            and "-fy-" in path.name
            and path.is_file()
            and path.stat().st_size > 0
        ):
            return True
    return False


def _atomic_write_bytes(target_path: Path, data: bytes) -> None:
    """同一ディレクトリ内の一時ファイル経由で原子的にバイト列を書き込む。"""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=".tmp",
        dir=str(target_path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fp:
            fp.write(data)
        os.replace(tmp_path, target_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def pack_financial_archive(
    financial_dir: Union[str, Path] = "./data/financial",
    archive_path: Union[str, Path] = f"./output/{DEFAULT_FINANCIAL_ARCHIVE_NAME}",
) -> Path:
    """
    financial_dir 直下の財務 JSON ファイル群を単一 ZIP アーカイブへ圧縮する。
    """
    fin_dir = Path(financial_dir)
    if not fin_dir.is_dir():
        raise FileNotFoundError(f"財務データディレクトリが見つかりません: {fin_dir}")

    json_files = sorted(
        p
        for p in fin_dir.glob("*.json")
        if p.is_file() and not p.name.startswith(".") and p.stat().st_size > 0
    )
    if not json_files:
        raise ValueError(f"圧縮対象の財務 JSON ファイルが見つかりません: {fin_dir}")

    out_path = Path(archive_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{out_path.name}.",
        suffix=".tmp",
        dir=str(out_path.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with zipfile.ZipFile(
            tmp_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as zf:
            for json_file in json_files:
                zf.write(json_file, arcname=json_file.name)
        os.replace(tmp_path, out_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    size_mb = out_path.stat().st_size / (1024 * 1024)
    logger.info(
        f"財務データ ZIP を作成しました: {out_path} ({len(json_files)} 件, {size_mb:.2f} MB)"
    )
    return out_path


def extract_financial_archive(
    archive_path: Union[str, Path],
    financial_dir: Union[str, Path] = "./data/financial",
) -> List[Path]:
    """
    ZIP アーカイブから財務 JSON ファイルを検証付きで financial_dir 直下へ安全に展開する。
    - パストラバーサル（Zip Slip）やサイズ上限超過（Zip Bomb）を厳格に拒否する。
    - macOS Finder 圧縮時に混入する __MACOSX や隠しファイル（.*）、サブディレクトリ階層を適切に処理する。
    """
    zip_path = Path(archive_path)
    if not zip_path.is_file():
        raise FileNotFoundError(f"展開対象の ZIP ファイルが見つかりません: {zip_path}")

    dest_dir = Path(financial_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest_dir.resolve()

    extracted: List[Path] = []
    total_bytes = 0

    try:
        with zipfile.ZipFile(zip_path, mode="r") as zf:
            for info in zf.infolist():
                raw_parts = info.filename.replace("\\", "/").split("/")
                parts = [pt for pt in raw_parts if pt and pt != "."]
                if not parts:
                    continue
                if ".." in parts:
                    raise ValueError(
                        f"不正な相対パスを含む ZIP エントリを拒否しました: {info.filename}"
                    )
                if info.is_dir():
                    continue
                if "__MACOSX" in parts:
                    continue

                base_name = parts[-1]
                if base_name.startswith(".") or not base_name.lower().endswith(".json"):
                    continue

                if info.file_size > _MAX_SINGLE_JSON_BYTES:
                    raise ValueError(
                        f"ZIP エントリのサイズが上限を超えています ({info.file_size} bytes): {base_name}"
                    )

                with zf.open(info, mode="r") as entry_fp:
                    data = entry_fp.read(_MAX_SINGLE_JSON_BYTES + 1)
                if len(data) > _MAX_SINGLE_JSON_BYTES:
                    raise ValueError(
                        f"展開データの実サイズが上限を超えています: {base_name}"
                    )

                total_bytes += len(data)
                if total_bytes > _MAX_TOTAL_JSON_BYTES:
                    raise ValueError(
                        "ZIP アーカイブの合計展開サイズが上限を超えています。"
                    )

                try:
                    parsed = json.loads(data.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    raise ValueError(
                        f"財務 JSON ファイルの形式が不正です ({base_name}): {e}"
                    ) from e
                if not isinstance(parsed, dict):
                    raise ValueError(
                        f"財務 JSON のルート要素がオブジェクトではありません: {base_name}"
                    )

                target_path = (dest_dir / base_name).resolve()
                if target_path.parent != dest_resolved:
                    raise ValueError(
                        f"展開先ディレクトリ外への書き込みを拒否しました: {info.filename}"
                    )

                _atomic_write_bytes(target_path, data)
                extracted.append(target_path)
    except zipfile.BadZipFile as e:
        raise ValueError(f"破損または不正な ZIP ファイルです ({zip_path}): {e}") from e

    if not extracted:
        raise ValueError(
            f"ZIP アーカイブ内に有効な財務 JSON ファイルが含まれていません: {zip_path}"
        )

    extracted_sorted = sorted(set(extracted))
    logger.info(
        f"財務データ ZIP を展開しました: {len(extracted_sorted)} 件 -> {dest_dir}"
    )
    return extracted_sorted


def restore_financial_data_from_drive(
    drive_delivery: GoogleDriveBriefDelivery,
    financial_dir: Union[str, Path] = "./data/financial",
    archive_name: str = DEFAULT_FINANCIAL_ARCHIVE_NAME,
    force: bool = False,
) -> List[Path]:
    """
    financial_dir が空（または force=True）の場合、Google Drive から financial_data.zip を
    ダウンロードして展開する。キャッシュが存在する場合は通信を行わず既存ファイル一覧を返す。
    """
    fin_dir = Path(financial_dir)
    if not force and has_cached_financial_files(fin_dir):
        existing = sorted(
            p for p in fin_dir.glob("*.json") if p.is_file() and not p.name.startswith(".")
        )
        logger.info(
            f"ローカル財務キャッシュが既に存在するため Drive からの取得をスキップします ({len(existing)} 件): {fin_dir}"
        )
        return existing

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_zip = Path(tmpdir) / archive_name
        downloaded = drive_delivery.download_named_file(archive_name, tmp_zip)
        if downloaded is None:
            raise FileNotFoundError(
                f"Google ドライブの指定フォルダ内に '{archive_name}' が見つかりません。"
                f"手元で作成した {archive_name} を Google ドライブフォルダへ配置してください。"
            )
        return extract_financial_archive(downloaded, financial_dir=fin_dir)


def upload_financial_data_to_drive(
    drive_delivery: GoogleDriveBriefDelivery,
    financial_dir: Union[str, Path] = "./data/financial",
    archive_name: str = DEFAULT_FINANCIAL_ARCHIVE_NAME,
) -> str:
    """ローカル financial_dir を ZIP 圧縮し、Google Drive 指定フォルダへ新規作成または上書きアップロードする。"""
    clean_name = str(archive_name or "").strip()
    if not clean_name or "/" in clean_name or "\\" in clean_name:
        raise ValueError(f"不正なアーカイブファイル名です: {archive_name}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_zip = Path(tmpdir) / clean_name
        pack_financial_archive(financial_dir=financial_dir, archive_path=tmp_zip)
        return drive_delivery.upload_single_file(tmp_zip)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="財務キャッシュ（data/financial）ZIP パッケージ作成・Google Drive 同期ツール"
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--pack",
        action="store_true",
        help="ローカル data/financial/*.json を ZIP ファイルへ圧縮する",
    )
    mode_group.add_argument(
        "--upload",
        action="store_true",
        help="ローカル data/financial/*.json を ZIP 化して Google Drive フォルダへアップロードする",
    )
    mode_group.add_argument(
        "--restore",
        action="store_true",
        help="Google Drive フォルダから financial_data.zip をダウンロードして展開する",
    )
    parser.add_argument(
        "--financial-dir",
        type=str,
        default="./data/financial",
        help="財務 JSON ディレクトリパス（デフォルト: ./data/financial）",
    )
    parser.add_argument(
        "--archive-path",
        type=str,
        default=f"./output/{DEFAULT_FINANCIAL_ARCHIVE_NAME}",
        help="--pack 時の出力先 ZIP パス（デフォルト: ./output/financial_data.zip）",
    )
    parser.add_argument(
        "--archive-name",
        type=str,
        default=DEFAULT_FINANCIAL_ARCHIVE_NAME,
        help="Google Drive 上の ZIP ファイル名（デフォルト: financial_data.zip）",
    )
    parser.add_argument(
        "--drive-folder-id",
        type=str,
        default=None,
        help="Google Drive フォルダ ID（未指定時は環境変数 GOOGLE_DRIVE_FOLDER_ID を参照）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="--restore 時に既存のローカル財務 JSON があっても強制再取得・上書きする",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.pack:
            out = pack_financial_archive(
                financial_dir=args.financial_dir,
                archive_path=args.archive_path,
            )
            print(f"財務データ ZIP を出力しました: {out}", flush=True)
            return 0

        delivery = GoogleDriveBriefDelivery.from_env(folder_id=args.drive_folder_id)
        if args.upload:
            file_id = upload_financial_data_to_drive(
                drive_delivery=delivery,
                financial_dir=args.financial_dir,
                archive_name=args.archive_name,
            )
            print(
                f"Google Drive へ財務データ ZIP をアップロードしました: {args.archive_name} (gdrive://{file_id})",
                flush=True,
            )
            return 0

        files = restore_financial_data_from_drive(
            drive_delivery=delivery,
            financial_dir=args.financial_dir,
            archive_name=args.archive_name,
            force=args.force,
        )
        print(
            f"財務データキャッシュ準備完了: {len(files)} ファイル ({args.financial_dir})",
            flush=True,
        )
        return 0
    except Exception as e:
        logger.error(f"財務データ同期処理に失敗しました: {e}")
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
