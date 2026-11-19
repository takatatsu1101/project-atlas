from typing import List, Optional, Sequence

from src.common.indexing import resolve_target_indices
from src.feature_engine.features.utils import linear_scale
from src.feature_engine.interfaces import IFeature
from src.feature_engine.registry import feature_registry
from src.model.data_models import FeatureResultModel, FinancialModel, IndicatorSetModel, OhlcvModel


class VolumeScore(IFeature):
    feature_id: str = "V001_VolumeScore"
    feature_name: str = "出来高評価"
    feature_category: str = "Volume"

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
            open_price = ohlcv_data[i].open if i < len(ohlcv_data) else None
            volume_today = ohlcv_data[i].volume if i < len(ohlcv_data) else None

            min_past_days = 5
            max_past_days = 25

            avg_volume_25 = None
            vma5 = None
            vma25 = None
            up_down_volume_ratio = None
            pullback_dryup_rebound = False

            if i >= min_past_days and i < len(ohlcv_data):
                # 当日 i を除外した過去最大25営業日（t-25 〜 t-1）の平均出来高
                avg_volume_25 = self._calc_window_avg_volume(ohlcv_data, max(0, i - max_past_days), i)
                vma25 = avg_volume_25

                # 短期トレンド比較用の直近5営業日（当日を含む t-4 〜 t）の平均出来高
                vma5 = self._calc_window_avg_volume(ohlcv_data, max(0, i - 4), i + 1)

                # Up/Down Volume Ratio（直近 min(60, i+1) 日間）
                up_down_volume_ratio = self._calc_up_down_volume_ratio(ohlcv_data, i)

                # 押し目売り枯れ→反発出来高増の判定
                pullback_dryup_rebound = self._is_pullback_dryup_rebound(
                    ohlcv_data=ohlcv_data,
                    idx=i,
                    avg_volume_25=avg_volume_25,
                    volume_today=volume_today,
                    open_price=open_price,
                    close_price=close_price,
                )

            metadata = {
                "volume": volume_today,
                "avg_volume_25": avg_volume_25,
                "vma5": vma5,
                "vma25": vma25,
                "up_down_volume_ratio": up_down_volume_ratio,
                "pullback_dryup_rebound": pullback_dryup_rebound,
            }

            if (
                volume_today is None
                or avg_volume_25 is None
                or avg_volume_25 == 0
                or vma5 is None
                or vma25 is None
                or vma25 == 0
            ):
                raw_score = 50.0
            else:
                # 1. 出来高急増・短期トレンド (最大35点)
                spike_trend_score = self._calc_spike_and_trend_score(
                    volume_today, avg_volume_25, vma5, vma25
                )

                # 2. Up/Down Volume Ratio (最大35点)
                up_down_score = self._calc_up_down_score(up_down_volume_ratio)

                # 3. 押し目売り枯れ→反発出来高増 & 方向性整合性 (最大30点)
                direction_score = self._calc_direction_and_dryup_score(
                    open_price=open_price,
                    close_price=close_price,
                    volume_today=volume_today,
                    avg_volume_25=avg_volume_25,
                    pullback_dryup_rebound=pullback_dryup_rebound,
                )

                raw_score = max(
                    0.0,
                    min(100.0, spike_trend_score + up_down_score + direction_score),
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

    @staticmethod
    def _calc_window_avg_volume(
        ohlcv_data: List[OhlcvModel],
        start_idx: int,
        end_idx: int,
    ) -> Optional[float]:
        """指定範囲 [start_idx, end_idx) の有効出来高の平均を返す。"""
        s = max(0, start_idx)
        e = min(end_idx, len(ohlcv_data))
        if s >= e:
            return None
        vols = [
            ohlcv_data[j].volume
            for j in range(s, e)
            if ohlcv_data[j].volume is not None
        ]
        if not vols:
            return None
        return sum(vols) / len(vols)

    @staticmethod
    def _is_pullback_dryup_rebound(
        ohlcv_data: List[OhlcvModel],
        idx: int,
        avg_volume_25: Optional[float],
        volume_today: Optional[float],
        open_price: Optional[float],
        close_price: Optional[float],
    ) -> bool:
        """押し目売り枯れ(t-4〜t-1細り)→当日陽線+出来高増かどうかを判定する。"""
        if avg_volume_25 is None or avg_volume_25 <= 0 or volume_today is None:
            return False
        if open_price is None or close_price is None or close_price <= open_price:
            return False
        prev_start = max(0, idx - 4)
        prev_end = min(idx, len(ohlcv_data))
        prev_vols = [
            ohlcv_data[j].volume
            for j in range(prev_start, prev_end)
            if ohlcv_data[j].volume is not None
        ]
        if len(prev_vols) < 2:
            return False
        recent_prev_vol = sum(prev_vols) / len(prev_vols)
        return (
            recent_prev_vol <= avg_volume_25 * 0.8
            and volume_today > recent_prev_vol * 1.2
        )

    def _calc_up_down_volume_ratio(
        self,
        ohlcv_data: List[OhlcvModel],
        idx: int,
        lookback: int = 60,
    ) -> Optional[float]:
        """直近 min(60, idx+1) 日間の Up/Down Volume Ratio を算出する。"""
        start_j = max(1, idx - lookback + 1)
        end_j = min(idx + 1, len(ohlcv_data))
        if start_j >= end_j:
            return None

        up_vol = 0.0
        down_vol = 0.0
        for j in range(start_j, end_j):
            vol = ohlcv_data[j].volume
            if vol is None:
                continue
            prev_close = ohlcv_data[j - 1].close
            curr_close = ohlcv_data[j].close
            if curr_close > prev_close:
                up_vol += vol
            elif curr_close < prev_close:
                down_vol += vol

        if down_vol > 0:
            return up_vol / down_vol
        if up_vol > 0:
            return 3.0
        return 1.0

    def _calc_spike_and_trend_score(
        self,
        volume_today: float,
        avg_volume_25: float,
        vma5: float,
        vma25: float,
    ) -> float:
        """出来高急増水準（最大20点）と短期トレンド（最大15点）を評価する（計最大35点）。"""
        volume_ratio = volume_today / avg_volume_25
        spike_score = linear_scale(volume_ratio, 0.4, 2.0, 0.0, 20.0)

        vma_ratio = vma5 / vma25
        trend_score = linear_scale(vma_ratio, 0.6, 1.35, 2.0, 15.0)
        return spike_score + trend_score

    def _calc_up_down_score(self, up_down_volume_ratio: Optional[float]) -> float:
        """Up/Down Volume Ratio を評価する（最大35点）。"""
        if up_down_volume_ratio is None:
            return 17.5
        if up_down_volume_ratio >= 1.5:
            return linear_scale(up_down_volume_ratio, 1.5, 2.5, 28.0, 35.0)
        if up_down_volume_ratio >= 0.8:
            return linear_scale(up_down_volume_ratio, 0.8, 1.5, 10.0, 28.0)
        return linear_scale(up_down_volume_ratio, 0.3, 0.8, 0.0, 10.0)

    def _calc_direction_and_dryup_score(
        self,
        open_price: Optional[float],
        close_price: Optional[float],
        volume_today: float,
        avg_volume_25: float,
        pullback_dryup_rebound: bool,
    ) -> float:
        """押し目売り枯れ→反発出来高増 & 株価方向性整合性を評価する（最大30点）。"""
        if pullback_dryup_rebound:
            return 30.0
        if open_price is None or close_price is None:
            return 12.0
        if close_price > open_price:
            if volume_today > avg_volume_25:
                return 22.0  # 陽線＋出来高増
            return 15.0      # 薄商いの上昇
        if close_price < open_price:
            if volume_today < avg_volume_25:
                return 14.0  # 健全な小幅調整
            if volume_today >= avg_volume_25 * 1.3:
                return 0.0   # 陰線出来高急増（売り抜け警戒）
            return 5.0
        return 12.0

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        if max_val == min_val:
            return 50.0
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))


# レジストリに特徴量クラスを登録
feature_registry.register(VolumeScore)
