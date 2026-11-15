import tempfile
import unittest
from pathlib import Path

from src.common.storage import StorageManager
from src.data_collector.master import MasterManager, normalize_market_name
from src.model.data_models import StockMasterModel


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


if __name__ == "__main__":
    unittest.main()
