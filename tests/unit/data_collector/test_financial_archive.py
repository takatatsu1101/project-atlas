import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

import requests

from src.data_collector import financial_archive
from src.data_collector.financial_archive import (
    DEFAULT_FINANCIAL_ARCHIVE_NAME,
    extract_financial_archive,
    has_cached_financial_files,
    main as archive_main,
    pack_financial_archive,
    restore_financial_data_from_drive,
    upload_financial_data_to_drive,
)
from src.presentation.gemini_brief import GoogleDriveBriefDelivery


def _mock_resp(status_code: int = 200, json_data=None, content: bytes = b"") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.reason = "OK"
    resp.content = content
    resp.json.return_value = json_data if json_data is not None else {}
    return resp


class TestFinancialArchive(unittest.TestCase):
    def test_has_cached_financial_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fin_dir = Path(tmpdir) / "financial"
            self.assertFalse(has_cached_financial_files(fin_dir))

            fin_dir.mkdir(parents=True)
            (fin_dir / "other.json").write_text("{}", encoding="utf-8")
            self.assertFalse(has_cached_financial_files(fin_dir))

            (fin_dir / "0025-fy-balance-sheet.json").write_text(
                json.dumps({"item": {"7203": []}}), encoding="utf-8"
            )
            self.assertTrue(has_cached_financial_files(fin_dir))

    def test_pack_and_extract_roundtrip_and_macos_finder_zip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src_fin"
            src_dir.mkdir()
            bs_payload = {"item": {"7203": ["2025/03", "100"]}}
            pl_payload = {"item": {"7203": ["2025/03", "200"]}}
            (src_dir / "0025-fy-balance-sheet.json").write_text(
                json.dumps(bs_payload), encoding="utf-8"
            )
            (src_dir / "0025-fy-profit-and-loss.json").write_text(
                json.dumps(pl_payload), encoding="utf-8"
            )
            (src_dir / ".hidden.json").write_text("{}", encoding="utf-8")

            zip_path = Path(tmpdir) / "out" / DEFAULT_FINANCIAL_ARCHIVE_NAME
            packed = pack_financial_archive(src_dir, zip_path)
            self.assertEqual(packed, zip_path)
            self.assertTrue(zip_path.is_file())

            dst_dir = Path(tmpdir) / "dst_fin"
            extracted = extract_financial_archive(zip_path, dst_dir)
            self.assertEqual(len(extracted), 2)
            self.assertFalse((dst_dir / ".hidden.json").exists())
            self.assertEqual(
                json.loads(
                    (dst_dir / "0025-fy-balance-sheet.json").read_text(encoding="utf-8")
                ),
                bs_payload,
            )

            # macOS Finder 右クリック圧縮形式（サブフォルダ + __MACOSX + .DS_Store）も正常展開できること
            finder_zip = Path(tmpdir) / "finder.zip"
            with zipfile.ZipFile(finder_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("financial/.DS_Store", b"junk")
                zf.writestr("__MACOSX/financial/._0024-fy-balance-sheet.json", b"not_json")
                zf.writestr(
                    "financial/0024-fy-balance-sheet.json",
                    json.dumps({"item": {"6758": []}}).encode("utf-8"),
                )
                zf.writestr("financial/README.txt", b"ignore me")

            finder_dst = Path(tmpdir) / "finder_dst"
            finder_extracted = extract_financial_archive(finder_zip, finder_dst)
            self.assertEqual(
                [p.name for p in finder_extracted], ["0024-fy-balance-sheet.json"]
            )

    def test_extract_rejects_zip_slip_invalid_json_and_oversized_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            dest = base / "dest"

            # 1) Zip Slip (../evil.json)
            slip_zip = base / "slip.zip"
            with zipfile.ZipFile(slip_zip, "w") as zf:
                zf.writestr("../evil.json", '{"a": 1}')
            with self.assertRaises(ValueError):
                extract_financial_archive(slip_zip, dest)
            self.assertFalse((base / "evil.json").exists())

            # 2) 不正 JSON / ルート非 dict
            bad_json_zip = base / "bad_json.zip"
            with zipfile.ZipFile(bad_json_zip, "w") as zf:
                zf.writestr("0025-fy-balance-sheet.json", "[1, 2, 3]")
            with self.assertRaises(ValueError):
                extract_financial_archive(bad_json_zip, dest)

            # 3) 破損 ZIP
            corrupt_zip = base / "corrupt.zip"
            corrupt_zip.write_bytes(b"not a zip file")
            with self.assertRaises(ValueError):
                extract_financial_archive(corrupt_zip, dest)

            # 4) サイズ上限超過（ヘッダ偽装含む実読込チェック）
            big_zip = base / "big.zip"
            with zipfile.ZipFile(big_zip, "w") as zf:
                zf.writestr("0025-fy-balance-sheet.json", json.dumps({"x": "a" * 200}))
            with patch.object(financial_archive, "_MAX_SINGLE_JSON_BYTES", 50):
                with self.assertRaises(ValueError):
                    extract_financial_archive(big_zip, dest)

    def test_restore_and_upload_with_google_drive_delivery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            src_fin = base / "src_fin"
            src_fin.mkdir()
            (src_fin / "0025-fy-balance-sheet.json").write_text(
                json.dumps({"item": {"7203": []}}), encoding="utf-8"
            )

            # Upload テスト
            up_session = MagicMock(spec=requests.Session)
            up_session.request.side_effect = [
                _mock_resp(200, {"access_token": "tok_up"}),
                _mock_resp(200, {"files": []}),
                _mock_resp(200, {"id": "zip_drive_id", "name": DEFAULT_FINANCIAL_ARCHIVE_NAME}),
            ]
            up_delivery = GoogleDriveBriefDelivery(
                "cid", "csec", "rt", "fld", session=up_session
            )
            uploaded_id = upload_financial_data_to_drive(up_delivery, financial_dir=src_fin)
            self.assertEqual(uploaded_id, "zip_drive_id")

            # ZIP バイナリを用意して Restore テスト
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(
                    "0025-fy-balance-sheet.json",
                    json.dumps({"item": {"9984": ["2025/03"]}}).encode("utf-8"),
                )
            zip_bytes = zip_buf.getvalue()

            dl_session = MagicMock(spec=requests.Session)
            dl_session.request.side_effect = [
                _mock_resp(200, {"access_token": "tok_dl"}),
                _mock_resp(200, {"files": [{"id": "zip_drive_id", "name": DEFAULT_FINANCIAL_ARCHIVE_NAME}]}),
                _mock_resp(200, content=zip_bytes),
            ]
            dl_delivery = GoogleDriveBriefDelivery(
                "cid", "csec", "rt", "fld", session=dl_session
            )

            restore_dir = base / "restored_fin"
            restored_files = restore_financial_data_from_drive(
                dl_delivery, financial_dir=restore_dir, force=False
            )
            self.assertEqual(len(restored_files), 1)
            self.assertEqual(dl_session.request.call_count, 3)

            # キャッシュ既存 & force=False なら再通信ゼロ
            dl_session.reset_mock()
            skipped_files = restore_financial_data_from_drive(
                dl_delivery, financial_dir=restore_dir, force=False
            )
            self.assertEqual(len(skipped_files), 1)
            dl_session.request.assert_not_called()

            # Drive 上に ZIP が無い場合は FileNotFoundError
            missing_session = MagicMock(spec=requests.Session)
            missing_session.request.side_effect = [
                _mock_resp(200, {"access_token": "tok_missing"}),
                _mock_resp(200, {"files": []}),
            ]
            missing_delivery = GoogleDriveBriefDelivery(
                "cid", "csec", "rt", "fld", session=missing_session
            )
            with self.assertRaises(FileNotFoundError):
                restore_financial_data_from_drive(
                    missing_delivery, financial_dir=base / "empty_fin", force=False
                )

    def test_cli_main_pack_and_restore(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            fin_dir = base / "fin"
            fin_dir.mkdir()
            (fin_dir / "0025-fy-balance-sheet.json").write_text(
                json.dumps({"item": {}}), encoding="utf-8"
            )
            out_zip = base / "packed.zip"

            rc_pack = archive_main(
                [
                    "--pack",
                    "--financial-dir",
                    str(fin_dir),
                    "--archive-path",
                    str(out_zip),
                ]
            )
            self.assertEqual(rc_pack, 0)
            self.assertTrue(out_zip.is_file())

            # 存在しないディレクトリ指定時は終了コード 1
            rc_err = archive_main(
                [
                    "--pack",
                    "--financial-dir",
                    str(base / "no_such_dir"),
                ]
            )
            self.assertEqual(rc_err, 1)


if __name__ == "__main__":
    unittest.main()
