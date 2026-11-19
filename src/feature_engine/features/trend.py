from typing import List, Optional, Sequence

from src.common.indexing import resolve_target_indices
from src.feature_engine.features.utils import linear_scale
from src.feature_engine.interfaces import IFeature
from src.feature_engine.registry import feature_registry
from src.model.data_models import FeatureResultModel, FinancialModel, IndicatorSetModel, OhlcvModel


class TrendStrengthScore(IFeature):
    feature_id: str = "T001_TrendStrengthScore"
    feature_name: str = "トレンド強度"
    feature_category: str = "Trend"

    def calculate(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        financial_data: Optional[FinancialModel] = None,
        target_indices: Optional[Sequence[int]] = None,
    ) -> List[FeatureResultModel]:
        if not indicator_data or not ohlcv_data:
            return []

        results: List[FeatureResultModel] = []
        for i in resolve_target_indices(len(indicator_data), target_indices):
            ind_set = indicator_data[i]
            sma5 = ind_set.indicators.get("SMA5")
            sma25 = ind_set.indicators.get("SMA25")
            sma75 = ind_set.indicators.get("SMA75")
            sma200 = ind_set.indicators.get("SMA200")
            hh20 = ind_set.indicators.get("HIGHEST_HIGH_20")
            hh60 = ind_set.indicators.get("HIGHEST_HIGH_60")
            hh250 = ind_set.indicators.get("HIGHEST_HIGH_250")
            close_price = ohlcv_data[i].close if i < len(ohlcv_data) else None

            sma75_dev = (
                (close_price - sma75) / sma75
                if (close_price is not None and sma75 is not None and sma75 > 0)
                else None
            )
            ref_high_for_ratio = hh250 if hh250 is not None else (hh60 if hh60 is not None else hh20)
            high_250_ratio = (
                close_price / ref_high_for_ratio
                if (close_price is not None and ref_high_for_ratio is not None and ref_high_for_ratio > 0)
                else None
            )

            metadata = {
                "close": close_price,
                "sma5": sma5,
                "sma25": sma25,
                "sma75": sma75,
                "sma200": sma200,
                "sma75_dev": sma75_dev,
                "high_250_ratio": high_250_ratio,
                "highest_high_60": hh60,
                "highest_high_250": hh250,
            }

            if sma75 is None or sma75 <= 0 or close_price is None:
                raw_score = 50.0
            else:
                # 1. (close - SMA75) / SMA75 適正帯評価 (0〜35点)
                dev_score = self._calc_sma75_dev_score(sma75_dev)

                # 2. 52週高値接近度 close / HIGHEST_HIGH_250 (0〜30点)
                high_prox_score = (
                    linear_scale(high_250_ratio, 0.75, 0.98, 0.0, 30.0)
                    if high_250_ratio is not None
                    else 15.0
                )

                # 3. マルチ期間ブレイク強度 (0〜20点)
                break_score = self._calc_multi_break_score(indicator_data, i, close_price)

                # 4. 長期トレンド基盤 (0〜15点)
                long_term_score = self._calc_long_term_base_score(
                    indicator_data, i, close_price, sma75, sma200
                )

                raw_score = max(
                    0.0,
                    min(100.0, dev_score + high_prox_score + break_score + long_term_score),
                )

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

    def _calc_sma75_dev_score(self, dev: Optional[float]) -> float:
        """(close - SMA75) / SMA75 の適正帯を連続評価する（0〜35点）。"""
        if dev is None:
            return 17.5
        if 0.03 <= dev <= 0.18:
            # +3%〜+18% を高評価帯（中心付近で満点35点）
            if dev <= 0.06:
                return linear_scale(dev, 0.03, 0.06, 32.0, 35.0)
            if dev <= 0.14:
                return 35.0
            return linear_scale(dev, 0.14, 0.18, 35.0, 32.0)
        if 0.0 <= dev < 0.03:
            return linear_scale(dev, 0.0, 0.03, 18.0, 32.0)
        if 0.18 < dev <= 0.25:
            return linear_scale(dev, 0.18, 0.25, 32.0, 20.0)
        if dev > 0.25:
            # +25%超は過熱減点
            return linear_scale(dev, 0.25, 0.45, 20.0, 5.0)
        if -0.05 <= dev < 0.0:
            return linear_scale(dev, -0.05, 0.0, 5.0, 18.0)
        return linear_scale(dev, -0.15, -0.05, 0.0, 5.0)

    def _calc_multi_break_score(
        self,
        indicator_data: List[IndicatorSetModel],
        idx: int,
        close_price: float,
    ) -> float:
        """前日までの20/60/250日高値への接近・突破度合いを連続評価する（0〜20点）。"""
        ref_ind = indicator_data[idx - 1].indicators if idx > 0 else indicator_data[idx].indicators
        hh20 = ref_ind.get("HIGHEST_HIGH_20")
        hh60 = ref_ind.get("HIGHEST_HIGH_60")
        hh250 = ref_ind.get("HIGHEST_HIGH_250")

        periods = (
            (hh20, 6.0),
            (hh60 if hh60 is not None else hh20, 7.0),
            (hh250 if hh250 is not None else (hh60 if hh60 is not None else hh20), 7.0),
        )
        total = 0.0
        for ref_high, weight in periods:
            if ref_high is not None and ref_high > 0:
                ratio = close_price / ref_high
                total += linear_scale(ratio, 0.92, 1.01, 0.0, weight)
            else:
                total += weight * 0.5
        return total

    def _calc_long_term_base_score(
        self,
        indicator_data: List[IndicatorSetModel],
        idx: int,
        close_price: float,
        sma75: float,
        sma200: Optional[float],
    ) -> float:
        """長期トレンド基盤を評価する（0〜15点）。"""
        if sma200 is not None:
            above_200 = close_price > sma200
            golden_75_200 = sma75 > sma200
            if above_200 and golden_75_200:
                return 15.0
            if above_200 or golden_75_200:
                return 8.0
            return 0.0

        # SMA200 欠損時は close > SMA75 と SMA75 上向きで代替
        prev_idx = max(0, idx - 5)
        sma75_prev = indicator_data[prev_idx].indicators.get("SMA75")
        above_75 = close_price > sma75
        sma75_up = sma75_prev is not None and sma75 > sma75_prev
        if above_75 and sma75_up:
            return 15.0
        if above_75 or sma75_up:
            return 8.0
        return 0.0

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        if max_val == min_val:
            return 50.0
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))


# レジストリに特徴量クラスを登録
feature_registry.register(TrendStrengthScore)
