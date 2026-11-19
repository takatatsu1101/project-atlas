import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.common.indexing import resolve_target_indices
from src.feature_engine.features.utils import (
    linear_scale,
    normalize_score_range,
    to_finite_float,
    to_finite_int,
)
from src.feature_engine.interfaces import IFeature
from src.feature_engine.registry import feature_registry
from src.model.data_models import (
    FeatureResultModel,
    FinancialModel,
    IndicatorSetModel,
    OhlcvModel,
)


class ShareholderReturnScore(IFeature):
    """株主還元スコア（連続増配・還元性向バランス・自社株買い継続性・DOE）"""

    feature_id: str = "F006_ShareholderReturnScore"
    feature_name: str = "株主還元スコア"
    feature_category: str = "Fundamental"

    def calculate(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        financial_data: Optional[FinancialModel] = None,
        target_indices: Optional[Sequence[int]] = None,
    ) -> List[FeatureResultModel]:
        """対象インデックスに対して株主還元スコアを算出する。"""
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
        """株主還元データから生スコア（0〜100）とメタデータを算出する。"""
        if financial_data is None:
            return 50.0, {}

        dps = to_finite_float(financial_data.dividend_per_share)
        total_div = to_finite_float(financial_data.total_dividends)
        share_buyback = to_finite_float(financial_data.share_buyback)
        payout_ratio = to_finite_float(financial_data.payout_ratio)
        total_payout_ratio = to_finite_float(financial_data.total_payout_ratio)
        doe = to_finite_float(financial_data.doe)
        inc_years = to_finite_int(financial_data.consecutive_dividend_increase_years)
        non_dec_years = to_finite_int(financial_data.consecutive_non_decrease_years)
        buyback_count_3y = to_finite_int(financial_data.buyback_count_3y)
        net_profit = to_finite_float(financial_data.net_profit)

        has_return_fields = any(
            v is not None
            for v in (
                dps,
                total_div,
                share_buyback,
                payout_ratio,
                total_payout_ratio,
                doe,
                inc_years,
                non_dec_years,
                buyback_count_3y,
            )
        )

        if not has_return_fields:
            return 50.0, self._build_metadata(
                dps=dps,
                share_buyback=share_buyback,
                payout_ratio=payout_ratio,
                total_payout_ratio=total_payout_ratio,
                doe=doe,
                inc_years=inc_years,
                non_dec_years=non_dec_years,
                buyback_count_3y=buyback_count_3y,
                available_weight=0.0,
            )

        weighted_sum = 0.0
        weight_sum = 0.0

        # 1. 連続増配・非減配モメンタム（ウェイト 35.0）
        momentum_score = self._calc_dividend_momentum_score(
            inc_years, non_dec_years, dps, total_div
        )
        if momentum_score is not None:
            weighted_sum += momentum_score
            weight_sum += 35.0

        # 2. 総還元性向・配当性向バランス（ウェイト 30.0）
        ratio = total_payout_ratio if total_payout_ratio is not None else payout_ratio
        payout_score = self._calc_payout_balance_score(ratio)
        if payout_score is not None:
            weighted_sum += payout_score
            weight_sum += 30.0

        # 3. 自社株買い実績・継続性（ウェイト 20.0）
        weighted_sum += self._calc_buyback_score(
            share_buyback, net_profit, buyback_count_3y
        )
        weight_sum += 20.0

        # 4. 純資産配当率 DOE（ウェイト 15.0）
        doe_score = self._calc_doe_score(doe)
        if doe_score is not None:
            weighted_sum += doe_score
            weight_sum += 15.0

        raw_score = 50.0 if weight_sum == 0.0 else (weighted_sum / weight_sum) * 100.0

        return raw_score, self._build_metadata(
            dps=dps,
            share_buyback=share_buyback,
            payout_ratio=payout_ratio,
            total_payout_ratio=total_payout_ratio,
            doe=doe,
            inc_years=inc_years,
            non_dec_years=non_dec_years,
            buyback_count_3y=buyback_count_3y,
            available_weight=weight_sum,
        )

    @staticmethod
    def _build_metadata(
        *,
        dps: Optional[float],
        share_buyback: Optional[float],
        payout_ratio: Optional[float],
        total_payout_ratio: Optional[float],
        doe: Optional[float],
        inc_years: Optional[int],
        non_dec_years: Optional[int],
        buyback_count_3y: Optional[int],
        available_weight: float,
    ) -> Dict[str, Any]:
        return {
            "dividend_per_share": dps,
            "share_buyback": share_buyback,
            "payout_ratio": payout_ratio,
            "total_payout_ratio": total_payout_ratio,
            "doe": doe,
            "consecutive_dividend_increase_years": inc_years,
            "consecutive_non_decrease_years": non_dec_years,
            "buyback_count_3y": buyback_count_3y,
            "available_weight": available_weight,
        }

    @staticmethod
    def _calc_dividend_momentum_score(
        inc_years: Optional[int],
        non_dec_years: Optional[int],
        dps: Optional[float],
        total_div: Optional[float],
    ) -> Optional[float]:
        """連続増配・非減配モメンタム（最大 35.0 点）を評価する。"""
        if inc_years is not None or non_dec_years is not None:
            if inc_years is not None and inc_years >= 1:
                return linear_scale(float(inc_years), 0.0, 5.0, 15.0, 35.0)
            if non_dec_years is not None:
                return linear_scale(float(non_dec_years), 0.0, 5.0, 5.0, 18.0)
            return 5.0

        if dps is not None or total_div is not None:
            has_dividend = (dps is not None and dps > 0.0) or (
                total_div is not None and total_div > 0.0
            )
            return 17.5 if has_dividend else 3.0

        return None

    @staticmethod
    def _calc_payout_balance_score(ratio: Optional[float]) -> Optional[float]:
        """総還元性向・配当性向バランス（%・最大 30.0 点）を評価する。"""
        if ratio is None:
            return None
        if ratio < 0.0:
            return 0.0
        if ratio < 30.0:
            return linear_scale(ratio, 0.0, 30.0, 3.0, 30.0)
        if ratio <= 60.0:
            return 30.0
        if ratio <= 75.0:
            return linear_scale(ratio, 75.0, 60.0, 25.0, 30.0)
        if ratio <= 100.0:
            return linear_scale(ratio, 100.0, 75.0, 15.0, 25.0)
        return linear_scale(ratio, 150.0, 100.0, 0.0, 15.0)

    @staticmethod
    def _calc_buyback_score(
        share_buyback: Optional[float],
        net_profit: Optional[float],
        buyback_count_3y: Optional[int],
    ) -> float:
        """自社株買い実績・継続性（最大 20.0 点）を評価する。"""
        if share_buyback is not None and share_buyback > 0.0:
            score = 10.0
            if net_profit is not None and net_profit > 0.0:
                buyback_ratio = share_buyback / net_profit
                if math.isfinite(buyback_ratio):
                    score += linear_scale(buyback_ratio, 0.0, 0.30, 0.0, 5.0)
                else:
                    score += 2.5
            else:
                score += 2.5

            if buyback_count_3y is not None:
                score += linear_scale(float(buyback_count_3y), 1.0, 3.0, 1.5, 5.0)
            else:
                score += 2.0
            return min(20.0, score)

        if buyback_count_3y is not None and buyback_count_3y >= 1:
            return linear_scale(float(buyback_count_3y), 0.0, 3.0, 4.0, 12.0)

        return 4.0

    @staticmethod
    def _calc_doe_score(doe: Optional[float]) -> Optional[float]:
        """純資産配当率 DOE（%・最大 15.0 点）を評価する。"""
        if doe is None:
            return None
        if doe < 0.0:
            return 0.0
        if doe < 5.0:
            return linear_scale(doe, 0.0, 5.0, 0.0, 15.0)
        if doe <= 8.0:
            return 15.0
        return linear_scale(doe, 15.0, 8.0, 8.0, 15.0)

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        return normalize_score_range(raw_value, min_val, max_val)


# レジストリに特徴量クラスを登録
feature_registry.register(ShareholderReturnScore)
