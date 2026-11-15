import time
import unittest
from datetime import date, timedelta

from src.model.data_models import FinancialModel, OhlcvModel, StockMasterModel
from src.screener.pre_screener import PreScreener, PreScreeningCriteria


class TestPreScreener(unittest.TestCase):

    def setUp(self):
        self.screener = PreScreener()
        self.master_stocks = [
            StockMasterModel(code="7203", symbol="7203.T", name="プライム優良", market="プライム（内国株式）"),
            StockMasterModel(code="2001", symbol="2001.T", name="スタンダード優良", market="スタンダード"),
            StockMasterModel(code="3001", symbol="3001.T", name="グロース除外", market="グロース（内国株式）"),
            StockMasterModel(code="4001", symbol="4001.T", name="赤字企業", market="プライム"),
            StockMasterModel(code="5001", symbol="5001.T", name="小規模企業", market="プライム"),
            StockMasterModel(code="6001", symbol="6001.T", name="財務欠損", market="プライム"),
        ]
        self.financial_snapshot = {
            "7203": FinancialModel(
                symbol="7203.T",
                fiscal_date=date(2025, 3, 31),
                revenue=50_000_000_000.0,
                total_assets=80_000_000_000.0,
                operating_profit=5_000_000_000.0,
                net_profit=3_500_000_000.0,
                roe=12.0,
                equity_ratio=45.0,
            ),
            "2001": FinancialModel(
                symbol="2001.T",
                fiscal_date=date(2025, 3, 31),
                revenue=15_000_000_000.0,
                total_assets=20_000_000_000.0,
                operating_profit=1_000_000_000.0,
                net_profit=600_000_000.0,
                roe=6.0,
                equity_ratio=25.0,
            ),
            "3001": FinancialModel(
                symbol="3001.T",
                fiscal_date=date(2025, 3, 31),
                revenue=20_000_000_000.0,
                operating_profit=2_000_000_000.0,
                net_profit=1_000_000_000.0,
                roe=15.0,
                equity_ratio=50.0,
            ),
            "4001": FinancialModel(
                symbol="4001.T",
                fiscal_date=date(2025, 3, 31),
                revenue=30_000_000_000.0,
                operating_profit=-100_000_000.0,
                net_profit=-200_000_000.0,
                roe=-5.0,
                equity_ratio=30.0,
            ),
            "5001": FinancialModel(
                symbol="5001.T",
                fiscal_date=date(2025, 3, 31),
                revenue=2_000_000_000.0,
                operating_profit=200_000_000.0,
                net_profit=100_000_000.0,
                roe=8.0,
                equity_ratio=40.0,
            ),
        }

    def test_filter_universe_market_and_financials(self):
        filtered = self.screener.filter_universe(self.master_stocks, self.financial_snapshot)
        codes = [s.code for s in filtered]
        self.assertEqual(codes, ["7203", "2001"])

    def test_filter_universe_with_total_assets(self):
        criteria = PreScreeningCriteria(min_total_assets=50_000_000_000.0)
        filtered = self.screener.filter_universe(self.master_stocks, self.financial_snapshot, criteria=criteria)
        self.assertEqual([s.code for s in filtered], ["7203"])

    def test_filter_universe_performance_4000_stocks(self):
        """4,000銘柄規模のフィルタリングが高速（1秒未満）に完了すること"""
        stocks = [
            StockMasterModel(
                code=f"{1000 + i}",
                symbol=f"{1000 + i}.T",
                name=f"銘柄{i}",
                market="プライム" if i % 2 == 0 else "グロース",
            )
            for i in range(4000)
        ]
        snapshot = {
            f"{1000 + i}": FinancialModel(
                symbol=f"{1000 + i}.T",
                fiscal_date=date(2025, 3, 31),
                revenue=20_000_000_000.0,
                operating_profit=1_000_000_000.0,
                net_profit=600_000_000.0,
                roe=10.0,
                equity_ratio=35.0,
            )
            for i in range(4000)
        }

        start = time.perf_counter()
        filtered = self.screener.filter_universe(stocks, snapshot)
        elapsed = time.perf_counter() - start

        self.assertEqual(len(filtered), 2000)
        self.assertLess(elapsed, 1.0)

    def test_check_liquidity_and_as_of_date(self):
        base_date = date(2025, 1, 1)
        # 2025-01-01 ~ 01-20 は売買代金 5,000万円（基準1億円未満）
        # 2025-01-21 ~ 01-25 は売買代金 5億円（未来データ）
        bars = []
        for i in range(20):
            bars.append(
                OhlcvModel(
                    symbol="7203.T",
                    date=base_date + timedelta(days=i),
                    open=1000.0,
                    high=1010.0,
                    low=990.0,
                    close=1000.0,
                    volume=50_000,  # 売買代金 5,000万円
                )
            )
        for i in range(20, 25):
            bars.append(
                OhlcvModel(
                    symbol="7203.T",
                    date=base_date + timedelta(days=i),
                    open=1000.0,
                    high=1010.0,
                    low=990.0,
                    close=1000.0,
                    volume=500_000,  # 売買代金 5億円
                )
            )

        criteria = PreScreeningCriteria(liquidity_lookback_days=20, min_avg_trading_value=100_000_000.0)
        # as_of_date=2025-01-20 時点では不合格
        self.assertFalse(self.screener.check_liquidity(bars, as_of_date=date(2025, 1, 20), criteria=criteria))
        # as_of_date=2025-01-25 時点では直近20日の平均売買代金が基準超で合格
        self.assertTrue(self.screener.check_liquidity(bars, as_of_date=date(2025, 1, 25), criteria=criteria))

    def test_check_liquidity_insufficient_days_returns_false(self):
        """営業日数が liquidity_lookback_days 未満の場合は False を返す"""
        bars = [
            OhlcvModel(
                symbol="7203.T",
                date=date(2025, 1, 1) + timedelta(days=i),
                open=1000.0,
                high=1010.0,
                low=990.0,
                close=1000.0,
                volume=500_000,  # 売買代金 5億円
            )
            for i in range(5)
        ]
        criteria = PreScreeningCriteria(liquidity_lookback_days=20, min_avg_trading_value=100_000_000.0)
        self.assertFalse(self.screener.check_liquidity(bars, as_of_date=date(2025, 1, 10), criteria=criteria))

    def test_filter_by_liquidity(self):
        ohlcv_map = {
            "7203.T": [
                OhlcvModel(symbol="7203.T", date=date(2025, 1, 10), open=2000, high=2050, low=1980, close=2000.0, volume=100_000),
            ],
            "9999.T": [
                OhlcvModel(symbol="9999.T", date=date(2025, 1, 10), open=500, high=510, low=490, close=500.0, volume=1_000),
            ],
        }
        criteria = PreScreeningCriteria(liquidity_lookback_days=1, min_avg_trading_value=100_000_000.0, min_avg_volume=50_000)
        passed = self.screener.filter_by_liquidity(ohlcv_map, as_of_date=date(2025, 1, 10), criteria=criteria)
        self.assertEqual(passed, ["7203.T"])


if __name__ == "__main__":
    unittest.main()
