import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.common.exceptions import DataCollectionError
from src.common.storage import StorageManager
from src.data_collector.master import MasterManager, normalize_market_name
from src.model.data_models import StockMasterModel


def _build_minimal_jpx_xlsx() -> bytes:
    """テスト用の最小限な JPX 形式 .xlsx バイナリを標準ライブラリのみで生成する"""
    shared_strings_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="11" uniqueCount="11">
  <si><t>コード</t></si>
  <si><t>銘柄名</t></si>
  <si><t>市場・商品区分</t></si>
  <si><t>33業種区分</t></si>
  <si><t>17業種区分</t></si>
  <si><t>規模区分</t></si>
  <si><t>トヨタ自動車</t></si>
  <si><t>プライム（内国株式）</t></si>
  <si><t>輸送用機器</t></si>
  <si><t>自動車・輸送機</t></si>
  <si><t>TOPIX Core30</t></si>
</sst>"""

    # 2行目(row 2): 7203, すべて共有文字列 + 数値
    # 3行目(row 3): 130A, inlineStr を使用し、D3・E3（33業種・17業種）は空セルとしてスキップ、F3 のみ記載
    sheet1_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
      <c r="C1" t="s"><v>2</v></c>
      <c r="D1" t="s"><v>3</v></c>
      <c r="E1" t="s"><v>4</v></c>
      <c r="F1" t="s"><v>5</v></c>
    </row>
    <row r="2">
      <c r="A2"><v>7203</v></c>
      <c r="B2" t="s"><v>6</v></c>
      <c r="C2" t="s"><v>7</v></c>
      <c r="D2" t="s"><v>8</v></c>
      <c r="E2" t="s"><v>9</v></c>
      <c r="F2" t="s"><v>10</v></c>
    </row>
    <row r="3">
      <c r="A3" t="inlineStr"><is><t>130A</t></is></c>
      <c r="B3" t="inlineStr"><is><t>テストグロース</t></is></c>
      <c r="C3" t="inlineStr"><is><t>グロース（内国株式）</t></is></c>
      <c r="F3" t="inlineStr"><is><t>Small</t></is></c>
    </row>
  </sheetData>
</worksheet>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/sharedStrings.xml", shared_strings_xml.encode("utf-8"))
        zf.writestr("xl/worksheets/sheet1.xml", sheet1_xml.encode("utf-8"))
    return buf.getvalue()


class TestMasterManager(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.storage = StorageManager(base_dir=Path(self.tmpdir.name))
        self.manager = MasterManager(storage=self.storage)
        self.sample_stocks = [
            StockMasterModel(
                code="7203",
                symbol="7203.T",
                name="トヨタ自動車",
                market="プライム",
                sector_33="輸送用機器",
                sector_17="自動車・輸送機",
                scale="TOPIX Core30",
            ),
            StockMasterModel(
                code="130A",
                symbol="130A.T",
                name="テストグロース",
                market="グロース",
                sector_33="情報・通信業",
                sector_17="情報通信・サービスその他",
                scale=None,
            ),
        ]

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_normalize_market_name(self):
        self.assertEqual(normalize_market_name("プライム（内国株式）"), "プライム")
        self.assertEqual(normalize_market_name("スタンダード（内国株式）"), "スタンダード")
        self.assertEqual(normalize_market_name("グロース（外国株式）"), "グロース")
        self.assertEqual(normalize_market_name("プライム"), "プライム")
        self.assertEqual(normalize_market_name("スタンダード(内国株式)"), "スタンダード")
        self.assertEqual(normalize_market_name(""), "")

    def test_save_and_load_csv_english_headers(self):
        self.manager.save_master(self.sample_stocks, "master/tse_listed_stocks.csv")
        loaded = self.manager.load_master("master/tse_listed_stocks.csv")
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].code, "7203")
        self.assertEqual(loaded[0].symbol, "7203.T")
        self.assertEqual(loaded[1].code, "130A")
        self.assertIsNone(loaded[1].scale)

    def test_save_and_load_json(self):
        self.manager.save_master(self.sample_stocks, "master/tse_listed_stocks.json")
        loaded = self.manager.load_master("master/tse_listed_stocks.json")
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].name, "トヨタ自動車")
        self.assertEqual(loaded[1].market, "グロース")

    def test_save_and_load_parquet(self):
        self.manager.save_master(self.sample_stocks, "master/tse_listed_stocks.parquet")
        loaded = self.manager.load_master("master/tse_listed_stocks.parquet")
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].sector_33, "輸送用機器")
        self.assertEqual(loaded[1].symbol, "130A.T")

    def test_load_jpx_japanese_csv_cp932_and_utf8(self):
        csv_content = (
            "コード,銘柄名,市場・商品区分,33業種区分,17業種区分,規模区分\n"
            "7203,トヨタ自動車,プライム（内国株式）,輸送用機器,自動車・輸送機,TOPIX Core30\n"
            "130A,テスト銘柄,グロース（内国株式）,情報・通信業,情報通信・サービスその他,-\n"
        )
        for idx, encoding in enumerate(("utf-8", "utf-8-sig", "cp932")):
            csv_path = self.storage.master_dir / f"jpx_{idx}.csv"
            csv_path.write_bytes(csv_content.encode(encoding))
            loaded = self.manager.load_master(csv_path)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].symbol, "7203.T")
            self.assertEqual(loaded[0].market, "プライム")
            self.assertEqual(loaded[1].symbol, "130A.T")
            self.assertEqual(loaded[1].market, "グロース")
            self.assertIsNone(loaded[1].scale)

    def test_load_master_default_resolution_and_missing(self):
        # 未存在時は空リスト
        self.assertEqual(self.manager.load_master(), [])

        # parquet -> json -> csv の優先順位確認
        self.manager.save_master([self.sample_stocks[0]], "master/tse_listed_stocks.csv")
        self.assertEqual(len(self.manager.load_master()), 1)

        self.manager.save_master(self.sample_stocks, "master/tse_listed_stocks.parquet")
        self.assertEqual(len(self.manager.load_master()), 2)

    @patch("src.data_collector.master.requests.get")
    def test_fetch_jpx_master_url_success_and_error(self, mock_get):
        # 相対パスリンクを絶対URLへ解決できること
        mock_resp = MagicMock()
        mock_resp.text = '<html><body><a href="/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xlsx">Excel</a></body></html>'
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        url = self.manager.fetch_jpx_master_url()
        self.assertEqual(
            url,
            "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xlsx",
        )

        # リンクが見つからない場合は DataCollectionError
        mock_resp.text = "<html><body><p>no link</p></body></html>"
        with self.assertRaises(DataCollectionError):
            self.manager.fetch_jpx_master_url()

        # .xls のみが見つかった場合は未対応の明確な DataCollectionError
        mock_resp.text = '<html><body><a href="/files/data_j.xls">Old Excel</a></body></html>'
        with self.assertRaises(DataCollectionError) as ctx:
            self.manager.fetch_jpx_master_url()
        self.assertIn(".xls", str(ctx.exception))
        self.assertIn("未対応", str(ctx.exception))

    def test_parse_jpx_xlsx_success_with_sparse_cells(self):
        xlsx_bytes = _build_minimal_jpx_xlsx()
        models = self.manager.parse_jpx_xlsx(xlsx_bytes)
        self.assertEqual(len(models), 2)

        self.assertEqual(models[0].code, "7203")
        self.assertEqual(models[0].symbol, "7203.T")
        self.assertEqual(models[0].name, "トヨタ自動車")
        self.assertEqual(models[0].market, "プライム")
        self.assertEqual(models[0].sector_33, "輸送用機器")
        self.assertEqual(models[0].sector_17, "自動車・輸送機")
        self.assertEqual(models[0].scale, "TOPIX Core30")

        # 空セル D3/E3 がスキップされても F3 が scale に入り、sector_33/17 は None になること
        self.assertEqual(models[1].code, "130A")
        self.assertEqual(models[1].symbol, "130A.T")
        self.assertEqual(models[1].name, "テストグロース")
        self.assertEqual(models[1].market, "グロース")
        self.assertIsNone(models[1].sector_33)
        self.assertIsNone(models[1].sector_17)
        self.assertEqual(models[1].scale, "Small")

    def test_parse_jpx_xlsx_invalid_bytes(self):
        with self.assertRaises(DataCollectionError):
            self.manager.parse_jpx_xlsx(b"")
        with self.assertRaises(DataCollectionError):
            self.manager.parse_jpx_xlsx(b"not a zip file")

    @patch("src.data_collector.master.requests.get")
    def test_update_from_jpx(self, mock_get):
        html_resp = MagicMock()
        html_resp.text = '<a href="/files/data_j.xlsx">data_j.xlsx</a>'
        html_resp.raise_for_status.return_value = None

        xlsx_resp = MagicMock()
        xlsx_resp.content = _build_minimal_jpx_xlsx()
        xlsx_resp.raise_for_status.return_value = None

        mock_get.side_effect = [html_resp, xlsx_resp]

        models = self.manager.update_from_jpx("master/tse_listed_stocks.csv")
        self.assertEqual(len(models), 2)
        saved_path = self.storage.base_dir / "master/tse_listed_stocks.csv"
        self.assertTrue(saved_path.exists())
        reloaded = self.manager.load_master("master/tse_listed_stocks.csv")
        self.assertEqual(len(reloaded), 2)
        self.assertEqual(reloaded[0].code, "7203")
        self.assertEqual(reloaded[1].scale, "Small")

    def test_load_master_prefers_latest_mtime_among_defaults(self):
        # 古い parquet と新しい csv が混在する場合、更新日時が新しい csv が優先されること
        self.manager.save_master(self.sample_stocks, "master/tse_listed_stocks.parquet")
        self.manager.save_master([self.sample_stocks[0]], "master/tse_listed_stocks.csv")

        parquet_path = self.storage.master_dir / "tse_listed_stocks.parquet"
        csv_path = self.storage.master_dir / "tse_listed_stocks.csv"
        os.utime(parquet_path, (1_700_000_000, 1_700_000_000))
        os.utime(csv_path, (1_700_000_100, 1_700_000_100))

        loaded = self.manager.load_master()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].code, "7203")

    @patch("src.data_collector.master.requests.get")
    def test_update_from_jpx_preserves_existing_default_format(self, mock_get):
        # 既に parquet が存在する場合、引数なし update_from_jpx() は parquet を上書き更新する
        self.manager.save_master([self.sample_stocks[0]], "master/tse_listed_stocks.parquet")

        html_resp = MagicMock()
        html_resp.text = '<a href="/files/data_j.xlsx">data_j.xlsx</a>'
        html_resp.raise_for_status.return_value = None

        xlsx_resp = MagicMock()
        xlsx_resp.content = _build_minimal_jpx_xlsx()
        xlsx_resp.raise_for_status.return_value = None
        mock_get.side_effect = [html_resp, xlsx_resp]

        models = self.manager.update_from_jpx()
        self.assertEqual(len(models), 2)
        reloaded = self.manager.load_master()
        self.assertEqual(len(reloaded), 2)
        self.assertFalse((self.storage.master_dir / "tse_listed_stocks.csv").exists())

    def test_parse_jpx_xlsx_with_title_row_and_second_sheet(self):
        # sheet1 は説明のみ、sheet2 の先頭2行にタイトル・空行があり、3行目にヘッダーがあるケース
        sheet1_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>説明シート</t></is></c></row>
  </sheetData>
</worksheet>"""
        sheet2_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>東証上場銘柄一覧（2026年11月）</t></is></c></row>
    <row r="3">
      <c r="A3" t="inlineStr"><is><t>コード</t></is></c>
      <c r="B3" t="inlineStr"><is><t>銘柄名</t></is></c>
      <c r="C3" t="inlineStr"><is><t>市場・商品区分</t></is></c>
    </row>
    <row r="4">
      <c r="A4"><v>7203</v></c>
      <c r="B4" t="inlineStr"><is><t>トヨタ自動車</t></is></c>
      <c r="C4" t="inlineStr"><is><t>プライム（内国株式）</t></is></c>
    </row>
  </sheetData>
</worksheet>"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("xl/worksheets/sheet1.xml", sheet1_xml.encode("utf-8"))
            zf.writestr("xl/worksheets/sheet2.xml", sheet2_xml.encode("utf-8"))

        models = self.manager.parse_jpx_xlsx(buf.getvalue())
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].code, "7203")
        self.assertEqual(models[0].name, "トヨタ自動車")
        self.assertEqual(models[0].market, "プライム")

    def test_parse_jpx_xlsx_ignores_phonetic_rph(self):
        # sharedStrings と inlineStr にふりがな要素 <rPh> が含まれていても本文のみ抽出されること
        shared_strings_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>コード</t><rPh sb="0" eb="3"><t>コードフリガナ</t></rPh></si>
  <si><t>銘柄名</t><rPh sb="0" eb="3"><t>メイガラメイ</t></rPh></si>
  <si><t>市場・商品区分</t></si>
  <si><r><t>トヨタ</t></r><r><t>自動車</t></r><rPh sb="0" eb="6"><t>トヨタジドウシャ</t></rPh></si>
</sst>"""
        sheet_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
      <c r="C1" t="s"><v>2</v></c>
    </row>
    <row r="2">
      <c r="A2"><v>7203</v></c>
      <c r="B2" t="s"><v>3</v></c>
      <c r="C2" t="inlineStr"><is><t>プライム（内国株式）</t><rPh sb="0" eb="4"><t>プライム</t></rPh></is></c>
    </row>
  </sheetData>
</worksheet>"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("xl/sharedStrings.xml", shared_strings_xml.encode("utf-8"))
            zf.writestr("xl/worksheets/sheet1.xml", sheet_xml.encode("utf-8"))

        models = self.manager.parse_jpx_xlsx(buf.getvalue())
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].code, "7203")
        self.assertEqual(models[0].name, "トヨタ自動車")
        self.assertEqual(models[0].market, "プライム")


if __name__ == "__main__":
    unittest.main()
