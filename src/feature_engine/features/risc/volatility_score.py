from typing import List, Optional, Sequence

from src.common.indexing import resolve_target_indices
from src.feature_engine.features.utils import linear_scale
from src.feature_engine.interfaces import IFeature
from src.feature_engine.registry import feature_registry
from src.model.data_models import FeatureResultModel, FinancialModel, IndicatorSetModel, OhlcvModel


class VolatilityScore(IFeature):
    feature_id: str = "R001_VolatilityScore"
    feature_name: str = "ボラティリティスコア"
    feature_category: str = "Risk"

    def calculate(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        financial_data: Optional[FinancialModel] = None,
        target_indices: Optional[Sequence[int]] = None,
    ) -> List[FeatureResultModel]:
        if not ohlcv_data:
            return []

        results: List[FeatureResultModel] = []
        for i in resolve_target_indices(len(indicator_data), target_indices):
            ind_set = indicator_data[i]
            close_price = ohlcv_data[i].close if i < len(ohlcv_data) else None

            # 既存互換のための当日TRと過去平均ATRの算出
            tr_today, avg_atr = self._calc_legacy_tr_and_avg_atr(ohlcv_data, i)
            volatility_ratio = (
                tr_today / avg_atr
                if (tr_today is not None and avg_atr is not None and avg_atr > 0)
                else None
            )

            atr5 = ind_set.indicators.get("ATR5")
            atr14 = ind_set.indicators.get("ATR14")
            atr20 = ind_set.indicators.get("ATR20")
            hh20 = ind_set.indicators.get("HIGHEST_HIGH_20")

            atr_contraction = (
                atr5 / atr20
                if (atr5 is not None and atr20 is not None and atr20 > 0)
                else None
            )
            effective_atr14 = atr14 if atr14 is not None else avg_atr
            atr_pct = (
                effective_atr14 / close_price
                if (effective_atr14 is not None and close_price is not None and close_price > 0)
                else None
            )
            reward_risk_ratio = (
                (hh20 - close_price) / max(effective_atr14, 1e-9)
                if (hh20 is not None and close_price is not None and effective_atr14 is not None)
                else None
            )

            metadata = {
                "close": close_price,
                "tr_today": tr_today,
                "avg_atr": avg_atr,
                "volatility_ratio": volatility_ratio,
                "atr5": atr5,
                "atr20": atr20,
                "atr14": atr14,
                "atr_contraction": atr_contraction,
                "atr_pct": atr_pct,
                "reward_risk_ratio": reward_risk_ratio,
            }

            # 最小限のデータが揃っていない初期バー等は中立(50.0)
            if (tr_today is None or avg_atr is None or avg_atr == 0) and atr_contraction is None and atr_pct is None:
                raw_score = 50.0
            else:
                contraction_score = self._calc_contraction_score(atr_contraction)
                atr_pct_score = self._calc_atr_pct_score(atr_pct)
                rr_score = self._calc_reward_risk_score(reward_risk_ratio)
                raw_score = max(0.0, min(100.0, contraction_score + atr_pct_score + rr_score))

            normalized_score = self._normalize_score(raw_score, 0, 100)

            results.append(
                FeatureResultModel(
                    feature_id=self.feature_id,
                    feature_name=self.feature_name,
                    score=normalized_score,
                    raw_value=raw_score,
                    metadata=metadata,
                    date=ind_set.date,
                )
            )
        return results

    def _calc_legacy_tr_and_avg_atr(
        self,
        ohlcv_data: List[OhlcvModel],
        idx: int,
        min_past_days: int = 5,
        max_past_days: int = 20,
    ) -> tuple[Optional[float], Optional[float]]:
        """既存互換の当日True Rangeと過去平均ATRを算出する。"""
        if idx < min_past_days or idx >= len(ohlcv_data):
            return None, None
        start_j = max(0, idx - max_past_days)
        end_j = min(idx + 1, len(ohlcv_data))
        if start_j >= end_j:
            return None, None

        true_ranges: List[float] = []
        for j in range(start_j, end_j):
            high = ohlcv_data[j].high
            low = ohlcv_data[j].low
            close_prev = ohlcv_data[j - 1].close if j > 0 else low
            if high is not None and low is not None:
                tr = max(high - low, abs(high - close_prev), abs(low - close_prev))
                true_ranges.append(tr)

        if not true_ranges:
            return None, None
        return true_ranges[-1], sum(true_ranges) / len(true_ranges)

    def _calc_contraction_score(self, atr_contraction: Optional[float]) -> float:
        """VCP収縮度 ATR5 / ATR20 を連続評価する（0〜40点）。"""
        if atr_contraction is None:
            return 20.0
        if atr_contraction <= 0.65:
            return 40.0
        if atr_contraction <= 1.0:
            return linear_scale(atr_contraction, 0.65, 1.0, 40.0, 20.0)
        if atr_contraction <= 1.4:
            return linear_scale(atr_contraction, 1.0, 1.4, 20.0, 5.0)
        return linear_scale(atr_contraction, 1.4, 2.0, 5.0, 0.0)

    def _calc_atr_pct_score(self, atr_pct: Optional[float]) -> float:
        """定常 ATR% (ATR14 / close) の適正帯を評価する（0〜30点）。"""
        if atr_pct is None:
            return 15.0
        if 0.01 <= atr_pct <= 0.035:
            return 30.0
        if atr_pct < 0.01:
            return linear_scale(atr_pct, 0.0, 0.01, 20.0, 30.0)
        if atr_pct <= 0.05:
            return linear_scale(atr_pct, 0.035, 0.05, 30.0, 15.0)
        if atr_pct <= 0.08:
            return linear_scale(atr_pct, 0.05, 0.08, 15.0, 0.0)
        return 0.0

    def _calc_reward_risk_score(self, reward_risk_ratio: Optional[float]) -> float:
        """リスクリワード余地比 (HIGHEST_HIGH_20 - close) / ATR14 を連続評価する（0〜30点）。"""
        if reward_risk_ratio is None:
            return 15.0
        if reward_risk_ratio <= 0.0:
            return 0.0
        return linear_scale(reward_risk_ratio, 0.0, 2.5, 0.0, 30.0)

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        if max_val == min_val:
            return 50.0
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))


# レジストリに特徴量クラスを登録
feature_registry.register(VolatilityScore)
