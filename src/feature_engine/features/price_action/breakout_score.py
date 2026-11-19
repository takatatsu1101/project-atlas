from typing import List, Optional, Sequence

from src.common.indexing import resolve_target_indices
from src.feature_engine.features.price_action.candle_utils import (
    compute_candle_metrics,
    compute_past_highest_high,
)
from src.feature_engine.interfaces import IFeature
from src.feature_engine.registry import feature_registry
from src.model.data_models import FeatureResultModel, FinancialModel, IndicatorSetModel, OhlcvModel


class BreakoutScore(IFeature):
    feature_id: str = "P002_BreakoutScore"
    feature_name: str = "ブレイクアウト評価"
    feature_category: str = "PriceAction"

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

            # 当日 i を除外した過去20日間・60日間の最高値を取得
            highest_high, past_days_calculated = compute_past_highest_high(
                ohlcv_data, i, max_past_days=20, min_past_days=5
            )
            highest_high_60, _ = compute_past_highest_high(
                ohlcv_data, i, max_past_days=60, min_past_days=20
            )

            candle = compute_candle_metrics(ohlcv_data, i)
            clv = candle["clv"]
            upper_wick_ratio = candle["upper_wick_ratio"]
            gap_pct = candle["gap_pct"]

            metadata = {
                "close": close_price,
                "highest_high": highest_high,
                "highest_high_60": highest_high_60,
                "past_days_calculated": past_days_calculated,
                "clv": clv,
                "upper_wick_ratio": upper_wick_ratio,
                "gap_pct": gap_pct,
            }

            if highest_high is None or close_price is None or highest_high <= 0:
                raw_score = 30.0  # データ不足時は低めのスコア
            else:
                base_score = self._calc_20d_breakout_base(close_price, highest_high)
                adjustment = self._calc_breakout_quality_adjustment(
                    close_price=close_price,
                    highest_high=highest_high,
                    highest_high_60=highest_high_60,
                    clv=clv,
                    upper_wick_ratio=upper_wick_ratio,
                    gap_pct=gap_pct,
                )
                raw_score = max(0.0, min(100.0, base_score + adjustment))

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

    def _calc_20d_breakout_base(self, close_price: float, highest_high: float) -> float:
        """当日除外20日高値に対するブレイク・接近ベーススコア（20〜100）を算出する。"""
        if close_price > highest_high:
            break_rate = (close_price - highest_high) / highest_high
            if break_rate <= 0.05:
                return 100.0 - (break_rate / 0.05) * 10.0  # 90〜100
            if break_rate <= 0.15:
                return 90.0 - ((break_rate - 0.05) / 0.10) * 20.0  # 70〜90
            return 50.0

        dist_rate = (highest_high - close_price) / highest_high
        if dist_rate <= 0.02:
            return 90.0 - (dist_rate / 0.02) * 20.0  # 70〜90
        if dist_rate <= 0.05:
            return 70.0 - ((dist_rate - 0.02) / 0.03) * 20.0  # 50〜70
        if dist_rate <= 0.10:
            return 50.0 - ((dist_rate - 0.05) / 0.05) * 30.0  # 20〜50
        return 20.0

    def _calc_breakout_quality_adjustment(
        self,
        close_price: float,
        highest_high: float,
        highest_high_60: Optional[float],
        clv: Optional[float],
        upper_wick_ratio: Optional[float],
        gap_pct: Optional[float],
    ) -> float:
        """60日高値ブレイク加点、CLV・上ヒゲの質評価、大幅ギャップアップ過熱減点を算出する。"""
        adj = 0.0

        # 60日高値（当日除外）ブレイク加点
        if highest_high_60 is not None and highest_high_60 > 0:
            if close_price > highest_high_60:
                adj += 8.0
            elif (highest_high_60 - close_price) / highest_high_60 <= 0.02:
                adj += 3.0

        # ブレイク時・高値圏でのローソク足の質評価
        is_breakout_or_near = close_price >= highest_high * 0.98
        if clv is not None:
            if clv >= 0.6 and is_breakout_or_near:
                adj += 5.0
            elif clv < 0.4 and is_breakout_or_near:
                adj -= 12.0
        if upper_wick_ratio is not None and upper_wick_ratio >= 0.4 and is_breakout_or_near:
            adj -= 12.0

        # 大幅ギャップアップ過熱減点 (gap_pct > 7%)
        if gap_pct is not None and gap_pct > 0.07:
            excess = min(0.10, gap_pct - 0.07)
            adj -= 10.0 + (excess / 0.10) * 10.0  # -10〜-20点

        return adj

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        """
        0-100の範囲でスコアを正規化する。
        """
        if max_val == min_val:
            return 50.0
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))


# レジストリに特徴量クラスを登録
feature_registry.register(BreakoutScore)
