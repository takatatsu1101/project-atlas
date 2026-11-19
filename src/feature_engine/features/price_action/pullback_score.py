from typing import List, Optional, Sequence

from src.common.indexing import resolve_target_indices
from src.feature_engine.features.price_action.candle_utils import compute_candle_metrics
from src.feature_engine.interfaces import IFeature
from src.feature_engine.registry import feature_registry
from src.model.data_models import FeatureResultModel, FinancialModel, IndicatorSetModel, OhlcvModel


class PullbackScore(IFeature):
    feature_id: str = "P001_PullbackScore"
    feature_name: str = "押し目評価"
    feature_category: str = "PriceAction"

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

            # 対応するインデックスのOHLCVデータとローソク足指標を取得
            close_price = ohlcv_data[i].close if i < len(ohlcv_data) else None
            candle = compute_candle_metrics(ohlcv_data, i)
            clv = candle["clv"]
            lower_wick_ratio = candle["lower_wick_ratio"]
            is_bullish = candle["is_bullish"]
            is_bearish = candle["is_bearish"]
            above_sma5 = (
                bool(close_price > sma5)
                if (close_price is not None and sma5 is not None)
                else None
            )

            metadata = {
                "sma5": sma5,
                "sma25": sma25,
                "sma75": sma75,
                "close": close_price,
                "clv": clv,
                "lower_wick_ratio": lower_wick_ratio,
                "is_bullish": is_bullish,
                "above_sma5": above_sma5,
            }

            # 必要なデータが揃っていない場合は低めのスコア
            if sma25 is None or sma75 is None or close_price is None or sma25 <= 0 or sma75 <= 0:
                raw_score = 30.0
            else:
                # 1. 前提条件: 中長期が上昇トレンドであること (SMA25 > SMA75) かつ 価格が長期線の上にあること
                is_uptrend = (sma25 > sma75) and (close_price > sma75)

                if not is_uptrend:
                    raw_score = 10.0  # トレンドが崩れているため押し目評価は低い
                else:
                    # 2. SMA25 / SMA75 乖離ベース (最大70点相当へスケーリング)
                    dist_base = self._calc_ma_distance_base(close_price, sma25, sma75)
                    scaled_base = dist_base * 0.70

                    # 3. 反発確認プライスアクション加点・減点 (最大+30点 / 大陰線安値引け減点)
                    pa_bonus = self._calc_rebound_price_action(
                        is_bullish=is_bullish,
                        is_bearish=is_bearish,
                        above_sma5=above_sma5,
                        clv=clv,
                        lower_wick_ratio=lower_wick_ratio,
                    )

                    raw_score = max(0.0, min(100.0, scaled_base + pa_bonus))

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

    def _calc_ma_distance_base(self, close_price: float, sma25: float, sma75: float) -> float:
        """SMA25/SMA75 乖離に基づく従来ベーススコア（0〜100）を算出する。"""
        dist_to_sma25 = (close_price - sma25) / sma25

        if 0.0 <= dist_to_sma25 <= 0.03:
            return 100.0 - (dist_to_sma25 / 0.03) * 20.0  # 80〜100
        if -0.02 <= dist_to_sma25 < 0.0:
            return 80.0 - (abs(dist_to_sma25) / 0.02) * 20.0  # 60〜80
        if dist_to_sma25 > 0.03:
            if dist_to_sma25 <= 0.10:
                return 80.0 - ((dist_to_sma25 - 0.03) / 0.07) * 40.0  # 40〜80
            return 40.0

        dist_to_sma75 = (close_price - sma75) / sma75
        if 0.0 <= dist_to_sma75 <= 0.02:
            return 70.0 - (dist_to_sma75 / 0.02) * 20.0  # 50〜70
        return 20.0

    def _calc_rebound_price_action(
        self,
        is_bullish: Optional[bool],
        is_bearish: Optional[bool],
        above_sma5: Optional[bool],
        clv: Optional[float],
        lower_wick_ratio: Optional[float],
    ) -> float:
        """反発確認プライスアクションによる加点（最大+30点）および弱気陰線減点を算出する。"""
        bonus = 0.0
        if is_bullish is True:
            bonus += 10.0
        if above_sma5 is True:
            bonus += 8.0
        if lower_wick_ratio is not None and clv is not None and lower_wick_ratio >= 0.35 and clv >= 0.5:
            bonus += 7.0
        if clv is not None and clv >= 0.6:
            bonus += 5.0

        # 陰線かつ安値引け（続落シグナル）の場合は減点
        if is_bearish is True and clv is not None and clv <= 0.25:
            bonus -= 15.0

        return bonus

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        """
        0-100の範囲でスコアを正規化する。
        """
        if max_val == min_val:
            return 50.0
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))


# レジストリに特徴量クラスを登録
feature_registry.register(PullbackScore)
