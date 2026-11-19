from typing import List, Optional, Sequence

from src.common.indexing import resolve_target_indices
from src.feature_engine.features.utils import linear_scale
from src.feature_engine.interfaces import IFeature
from src.feature_engine.registry import feature_registry
from src.model.data_models import FeatureResultModel, FinancialModel, IndicatorSetModel, OhlcvModel


class MAAlignmentScore(IFeature):
    feature_id: str = "M001_MAAlignmentScore"
    feature_name: str = "移動平均線の並び評価"
    feature_category: str = "Moving Average"

    def calculate(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        financial_data: Optional[FinancialModel] = None,
        target_indices: Optional[Sequence[int]] = None,
    ) -> List[FeatureResultModel]:
        if not indicator_data:
            return []

        results: List[FeatureResultModel] = []
        for i in resolve_target_indices(len(indicator_data), target_indices):
            ind_set = indicator_data[i]
            sma5 = ind_set.indicators.get("SMA5")
            sma25 = ind_set.indicators.get("SMA25")
            sma75 = ind_set.indicators.get("SMA75")
            sma200 = ind_set.indicators.get("SMA200")

            # 移動平均線の傾き（変化率）を算出
            sma25_slope_5d = self._calc_slope(indicator_data, i, 5, "SMA25", sma25)
            sma25_slope_20d = self._calc_slope(indicator_data, i, 20, "SMA25", sma25)
            sma75_slope_20d = self._calc_slope(indicator_data, i, 20, "SMA75", sma75)

            metadata = {
                "sma5": sma5,
                "sma25": sma25,
                "sma75": sma75,
                "sma200": sma200,
                "sma25_slope_5d": sma25_slope_5d,
                "sma25_slope_20d": sma25_slope_20d,
                "sma75_slope_20d": sma75_slope_20d,
            }

            if sma5 is None or sma25 is None or sma75 is None:
                raw_score = 50.0  # データ不足の場合は中立
            else:
                # 1. 配列基礎点 (0〜40点)
                alignment_score = self._calc_alignment_score(sma5, sma25, sma75, sma200)

                # 2. 移動平均線の傾き連続スコア (0〜40点)
                slope_5d_score = (
                    linear_scale(sma25_slope_5d, -0.02, 0.03, 0.0, 15.0)
                    if sma25_slope_5d is not None
                    else 7.5
                )
                slope_20d_score = (
                    linear_scale(sma25_slope_20d, -0.04, 0.08, 0.0, 15.0)
                    if sma25_slope_20d is not None
                    else 7.5
                )
                slope_75_score = (
                    linear_scale(sma75_slope_20d, -0.03, 0.06, 0.0, 10.0)
                    if sma75_slope_20d is not None
                    else 5.0
                )
                slope_score = slope_5d_score + slope_20d_score + slope_75_score

                # 3. MA間スプレッド健全性 (0〜20点)
                spread_score = self._calc_spread_score(sma25, sma75)

                raw_score = max(0.0, min(100.0, alignment_score + slope_score + spread_score))

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

    def _calc_slope(
        self,
        indicator_data: List[IndicatorSetModel],
        idx: int,
        lookback: int,
        key: str,
        current_val: Optional[float],
    ) -> Optional[float]:
        """lookback 日前に対する移動平均線の変化率を算出する。"""
        if current_val is None or idx < lookback:
            return None
        prev_val = indicator_data[idx - lookback].indicators.get(key)
        if prev_val is None or prev_val == 0:
            return None
        return (current_val - prev_val) / prev_val

    def _calc_alignment_score(
        self,
        sma5: float,
        sma25: float,
        sma75: float,
        sma200: Optional[float],
    ) -> float:
        """移動平均線の並び順を段階評価する（0〜40点）。"""
        if sma200 is not None:
            if sma5 > sma25 > sma75 > sma200:
                return 40.0  # 完全パーフェクトオーダー
            if sma5 > sma25 > sma75:
                return 32.0  # 中期上昇配列（200日線未超え）
            if sma25 > sma75 and sma75 > sma200:
                return 28.0  # 長期上昇トレンド中の押し目調整
            if sma25 > sma75:
                return 22.0  # 押し目調整
            if sma5 > sma25:
                return 20.0  # 上昇初動
            if sma5 < sma25 < sma75 < sma200:
                return 0.0   # 完全下降配列
            if sma5 < sma25 < sma75:
                return 5.0   # 下降配列
            return 12.0      # 交錯・レンジ

        # SMA200 欠損時は 5/25/75 の3本で評価
        if sma5 > sma25 > sma75:
            return 38.0
        if sma25 > sma75:
            return 25.0
        if sma5 > sma25:
            return 20.0
        if sma5 < sma25 < sma75:
            return 0.0
        return 12.0

    def _calc_spread_score(self, sma25: float, sma75: float) -> float:
        """(SMA25 - SMA75) / SMA75 のスプレッド健全性を評価する（0〜20点）。"""
        if sma75 <= 0:
            return 10.0
        spread = (sma25 - sma75) / sma75
        if 0.0 <= spread <= 0.08:
            return 15.0 + (spread / 0.08) * 5.0
        if 0.08 < spread <= 0.12:
            return 20.0 - ((spread - 0.08) / 0.04) * 3.0
        if 0.12 < spread <= 0.25:
            return 17.0 - ((spread - 0.12) / 0.13) * 12.0
        if spread > 0.25:
            return max(0.0, 5.0 - ((spread - 0.25) / 0.10) * 5.0)
        if -0.05 <= spread < 0.0:
            return 15.0 * (1.0 - abs(spread) / 0.05)
        return 0.0

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        """
        0-100の範囲でスコアを正規化する。
        """
        if max_val == min_val:
            return 50.0  # ゼロ除算を避ける
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))


# レジストリに特徴量クラスを登録
feature_registry.register(MAAlignmentScore)
