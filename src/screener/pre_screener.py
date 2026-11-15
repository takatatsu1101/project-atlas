"""
事前スクリーニング（ユニバース・財務・流動性フィルタ）モジュール
"""

from datetime import date
from typing import Dict, List, Optional
from pydantic import BaseModel

from src.common.logger import get_logger
from src.data_collector.master import normalize_market_name
from src.model.data_models import FinancialModel, OhlcvModel, StockMasterModel

logger = get_logger(__name__)


class PreScreeningCriteria(BaseModel):
    """事前スクリーニング条件"""
    target_markets: List[str] = ["プライム", "スタンダード"]
    min_revenue: Optional[float] = 10_000_000_000.0  # 最低売上高（100億円）
    min_total_assets: Optional[float] = None  # 最低総資産
    require_positive_operating_profit: bool = True  # 営業黒字必須
    require_positive_net_profit: bool = True  # 最終黒字必須
    min_roe: Optional[float] = 5.0  # 最低ROE（%）
    min_equity_ratio: Optional[float] = 20.0  # 最低自己資本比率（%）
    liquidity_lookback_days: int = 20  # 流動性判定の直近営業日数
    min_avg_trading_value: Optional[float] = 100_000_000.0  # 最低平均売買代金（1億円）
    min_avg_volume: Optional[int] = None  # 最低平均出来高


class PreScreener:
    """通信前のユニバース絞り込みおよび流動性スクリーニングを行うクラス"""

    def filter_universe(
        self,
        master_stocks: List[StockMasterModel],
        financial_snapshot: Dict[str, FinancialModel],
        criteria: Optional[PreScreeningCriteria] = None,
    ) -> List[StockMasterModel]:
        """
        市場区分（正規化して比較）と財務・規模条件で対象銘柄を高速フィルタリングする。
        財務データが欠損している銘柄は除外する。
        """
        if not master_stocks:
            return []

        cond = criteria or PreScreeningCriteria()
        target_markets_set = {normalize_market_name(m) for m in cond.target_markets}

        filtered: List[StockMasterModel] = []
        for stock in master_stocks:
            if target_markets_set and normalize_market_name(stock.market) not in target_markets_set:
                continue

            fin = financial_snapshot.get(stock.code) or financial_snapshot.get(stock.symbol)
            if fin is None:
                continue

            if cond.min_revenue is not None:
                if fin.revenue is None or fin.revenue < cond.min_revenue:
                    continue

            if cond.min_total_assets is not None:
                if fin.total_assets is None or fin.total_assets < cond.min_total_assets:
                    continue

            if cond.require_positive_operating_profit:
                if fin.operating_profit is None or fin.operating_profit <= 0:
                    continue

            if cond.require_positive_net_profit:
                if fin.net_profit is None or fin.net_profit <= 0:
                    continue

            if cond.min_roe is not None:
                if fin.roe is None or fin.roe < cond.min_roe:
                    continue

            if cond.min_equity_ratio is not None:
                if fin.equity_ratio is None or fin.equity_ratio < cond.min_equity_ratio:
                    continue

            filtered.append(stock)

        logger.info(f"ユニバース事前スクリーニング完了: {len(master_stocks)}件 -> {len(filtered)}件")
        return filtered

    def check_liquidity(
        self,
        ohlcv_list: List[OhlcvModel],
        as_of_date: Optional[date] = None,
        criteria: Optional[PreScreeningCriteria] = None,
    ) -> bool:
        """
        as_of_date 以前の直近 liquidity_lookback_days 営業日分の平均売買代金・平均出来高を判定する。
        """
        cond = criteria or PreScreeningCriteria()
        if not ohlcv_list or cond.liquidity_lookback_days <= 0:
            return False

        if as_of_date is not None:
            eligible = [bar for bar in ohlcv_list if bar.date <= as_of_date]
        else:
            eligible = list(ohlcv_list)

        if not eligible:
            return False

        eligible.sort(key=lambda bar: bar.date)
        recent = eligible[-cond.liquidity_lookback_days:]
        count = len(recent)
        if count < cond.liquidity_lookback_days:
            return False

        if cond.min_avg_trading_value is not None:
            avg_trading_value = sum(bar.close * bar.volume for bar in recent) / count
            if avg_trading_value < cond.min_avg_trading_value:
                return False

        if cond.min_avg_volume is not None:
            avg_volume = sum(bar.volume for bar in recent) / count
            if avg_volume < cond.min_avg_volume:
                return False

        return True

    def filter_by_liquidity(
        self,
        ohlcv_map: Dict[str, List[OhlcvModel]],
        as_of_date: Optional[date] = None,
        criteria: Optional[PreScreeningCriteria] = None,
    ) -> List[str]:
        """
        ohlcv_map から流動性条件を満たすシンボル（またはコード）のリストを抽出する。
        """
        cond = criteria or PreScreeningCriteria()
        return [
            key
            for key, ohlcv_list in ohlcv_map.items()
            if self.check_liquidity(ohlcv_list, as_of_date=as_of_date, criteria=cond)
        ]
