import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.common.indexing import resolve_target_indices
from src.feature_engine.features.utils import (
    linear_scale,
    normalize_score_range,
    to_finite_float,
)
from src.feature_engine.interfaces import IFeature
from src.feature_engine.registry import feature_registry
from src.model.data_models import (
    FeatureResultModel,
    FinancialModel,
    IndicatorSetModel,
    OhlcvModel,
)


class FinancialHealthScore(IFeature):
    """財務健全性スコア（自己資本比率・ネットキャッシュ比率・利益剰余金/有利子負債バランス）"""

    feature_id: str = "F004_FinancialHealthScore"
    feature_name: str = "財務健全性スコア"
    feature_category: str = "Fundamental"

    def calculate(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        financial_data: Optional[FinancialModel] = None,
        target_indices: Optional[Sequence[int]] = None,
    ) -> List[FeatureResultModel]:
        """対象インデックスに対して財務健全性スコアを算出する。"""
        if not indicator_data:
            return []

        raw_score, metadata = self._evaluate_financials(financial_data)
        normalized_score = self._normalize_score(raw_score, 0.0, 100.0)

        results: List[FeatureResultModel] = []
        for i in resolve_target_indices(len(indicator_data), target_indices):
            ind_set = indicator_data[i]
            results.append(
                FeatureResultModel(
                    feature_id=self.feature_id,
                    feature_name=self.feature_name,
                    score=normalized_score,
                    raw_value=raw_score,
                    metadata=dict(metadata),
                    date=ind_set.date,
                )
            )
        return results

    def _evaluate_financials(
        self, financial_data: Optional[FinancialModel]
    ) -> Tuple[float, Dict[str, Any]]:
        """財務諸表データから生スコア（0〜100）とメタデータを算出する。"""
        if financial_data is None:
            return 50.0, {}

        equity_ratio = to_finite_float(financial_data.equity_ratio)
        total_assets = to_finite_float(financial_data.total_assets)
        cash_and_equivalents = to_finite_float(financial_data.cash_and_equivalents)
        st_debt = to_finite_float(financial_data.short_term_debt)
        lt_debt = to_finite_float(financial_data.long_term_debt)
        retained_earnings = to_finite_float(financial_data.retained_earnings)
        shareholders_equity = to_finite_float(financial_data.shareholders_equity)
        net_assets = to_finite_float(financial_data.net_assets)

        # 短期・長期借入金の両方とも None/非有限のときは有利子負債 0 と見なさず欠損扱いとする
        interest_bearing_debt: Optional[float] = None
        if st_debt is not None or lt_debt is not None:
            debt_sum = (st_debt or 0.0) + (lt_debt or 0.0)
            if math.isfinite(debt_sum):
                interest_bearing_debt = debt_sum

        weighted_sum = 0.0
        weight_sum = 0.0

        # 1. 自己資本比率（ウェイト 40.0）
        if equity_ratio is not None:
            weighted_sum += linear_scale(equity_ratio, 10.0, 75.0, 0.0, 40.0)
            weight_sum += 40.0

        # 2. ネットキャッシュ比率（ウェイト 40.0）
        net_cash_ratio: Optional[float] = None
        if (
            cash_and_equivalents is not None
            and total_assets is not None
            and total_assets > 0.0
            and interest_bearing_debt is not None
        ):
            nc_ratio = (cash_and_equivalents - interest_bearing_debt) / total_assets
            if math.isfinite(nc_ratio):
                net_cash_ratio = nc_ratio
                weighted_sum += linear_scale(net_cash_ratio, -0.40, 0.40, 0.0, 40.0)
                weight_sum += 40.0

        # 3. 有利子負債 / 利益剰余金健全性（ウェイト 20.0）
        retained_earnings_ratio, re_sub = self._calc_retained_earnings_sub(
            retained_earnings, total_assets
        )
        debt_to_equity, de_sub = self._calc_debt_to_equity_sub(
            interest_bearing_debt, shareholders_equity, net_assets
        )

        if re_sub is not None and de_sub is not None:
            weighted_sum += ((re_sub + de_sub) / 2.0) * 20.0
            weight_sum += 20.0
        elif re_sub is not None:
            weighted_sum += re_sub * 20.0
            weight_sum += 20.0
        elif de_sub is not None:
            weighted_sum += de_sub * 20.0
            weight_sum += 20.0

        if weight_sum > 0.0:
            raw_score = (weighted_sum / weight_sum) * 100.0
        else:
            raw_score = self._calc_legacy_fallback_score(financial_data)

        metadata: Dict[str, Any] = {
            "equity_ratio": equity_ratio,
            "total_assets": total_assets,
            "cash_and_equivalents": cash_and_equivalents,
            "interest_bearing_debt": interest_bearing_debt,
            "net_cash_ratio": net_cash_ratio,
            "retained_earnings_ratio": retained_earnings_ratio,
            "debt_to_equity": debt_to_equity,
            "available_weight": weight_sum,
        }
        return raw_score, metadata

    @staticmethod
    def _calc_retained_earnings_sub(
        retained_earnings: Optional[float], total_assets: Optional[float]
    ) -> Tuple[Optional[float], Optional[float]]:
        """利益剰余金比率の正規化サブスコア（0.0〜1.0）を算出する。"""
        if retained_earnings is None or total_assets is None or total_assets <= 0.0:
            return None, None
        ratio = retained_earnings / total_assets
        if not math.isfinite(ratio):
            return None, None
        return ratio, linear_scale(ratio, -0.10, 0.60, 0.0, 1.0)

    @staticmethod
    def _calc_debt_to_equity_sub(
        interest_bearing_debt: Optional[float],
        shareholders_equity: Optional[float],
        net_assets: Optional[float],
    ) -> Tuple[Optional[float], Optional[float]]:
        """D/E レシオの正規化サブスコア（0.0〜1.0）を算出する。債務超過は 0.0。"""
        equity_base = shareholders_equity if shareholders_equity is not None else net_assets
        if interest_bearing_debt is None or equity_base is None:
            return None, None
        if equity_base <= 0.0:
            return None, 0.0
        dte = interest_bearing_debt / equity_base
        if not math.isfinite(dte):
            return None, None
        return dte, linear_scale(dte, 2.0, 0.0, 0.0, 1.0)

    @staticmethod
    def _calc_legacy_fallback_score(financial_data: FinancialModel) -> float:
        """新BS軸が全て算出不能な場合、レガシー4項目が揃っていれば簡易判定へフォールバックする。"""
        eps = to_finite_float(financial_data.eps)
        bps = to_finite_float(financial_data.bps)
        operating_profit = to_finite_float(financial_data.operating_profit)
        net_profit = to_finite_float(financial_data.net_profit)
        if eps is None or bps is None or operating_profit is None or net_profit is None:
            return 50.0

        score = 0.0
        if bps > eps:
            score += 50.0
        elif bps > 0.0:
            score += 30.0

        if operating_profit > 0.0 and net_profit > 0.0:
            score += 50.0
        elif operating_profit > 0.0 or net_profit > 0.0:
            score += 25.0
        return score

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        return normalize_score_range(raw_value, min_val, max_val)


# レジストリに特徴量クラスを登録
feature_registry.register(FinancialHealthScore)
