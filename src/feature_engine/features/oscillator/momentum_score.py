from typing import Any, Dict, List, Optional, Sequence

from src.common.indexing import resolve_target_indices
from src.feature_engine.features.utils import linear_scale
from src.feature_engine.interfaces import IFeature
from src.feature_engine.registry import feature_registry
from src.model.data_models import FeatureResultModel, FinancialModel, IndicatorSetModel, OhlcvModel


class MomentumScore(IFeature):
    feature_id: str = "O001_MomentumScore"
    feature_name: str = "モメンタムスコア"
    feature_category: str = "Oscillator"

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
            rsi14 = ind_set.indicators.get("RSI14")
            short_rsi = ind_set.indicators.get("RSI5")
            prev_short_rsi = indicator_data[i - 1].indicators.get("RSI5") if i > 0 else None
            macd_data = ind_set.indicators.get("MACD")
            macd_prev_data = indicator_data[i - 1].indicators.get("MACD") if i > 0 else None

            metadata = {
                "rsi14": rsi14,
                "short_rsi": short_rsi,
                "prev_short_rsi": prev_short_rsi,
                "macd": macd_data,
            }

            if rsi14 is None:
                raw_score = 50.0
            else:
                # 1. RSI14 ベル型評価 (最大50点: 45〜70適正帯、>80過熱減点、<30低評価)
                rsi14_score = self._calc_rsi14_bell_score(rsi14)

                # 2. MACD の評価 (最大40点)
                macd_score = self._calc_macd_score(macd_data, macd_prev_data)

                # 3. 短期反転トリガー RSI5 の評価 (最大10点)
                rsi5_score = self._calc_rsi5_trigger_score(short_rsi, prev_short_rsi)

                raw_score = max(0.0, min(100.0, rsi14_score + macd_score + rsi5_score))

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

    def _calc_rsi14_bell_score(self, rsi14: float) -> float:
        """RSI14 を中立的なベル型カーブで評価する（0〜50点）。"""
        if 50.0 <= rsi14 <= 65.0:
            return 50.0
        if 45.0 <= rsi14 < 50.0:
            return linear_scale(rsi14, 45.0, 50.0, 46.0, 50.0)
        if 65.0 < rsi14 <= 70.0:
            return linear_scale(rsi14, 65.0, 70.0, 50.0, 46.0)
        if 30.0 <= rsi14 < 45.0:
            return linear_scale(rsi14, 30.0, 45.0, 20.0, 46.0)
        if rsi14 < 30.0:
            return linear_scale(rsi14, 0.0, 30.0, 5.0, 20.0)
        if 70.0 < rsi14 <= 80.0:
            return linear_scale(rsi14, 70.0, 80.0, 46.0, 30.0)
        # > 80 は過熱減点
        return linear_scale(rsi14, 80.0, 100.0, 30.0, 10.0)

    def _calc_macd_score(
        self,
        macd_data: Optional[Dict[str, Any]],
        macd_prev_data: Optional[Dict[str, Any]],
    ) -> float:
        """MACD ゴールデンクロス・ヒストグラム推移を評価する（0〜40点）。"""
        if not isinstance(macd_data, dict):
            return 20.0
        macd_val = macd_data.get("macd")
        signal_val = macd_data.get("signal")
        hist_val = macd_data.get("histogram")
        if macd_val is None or signal_val is None:
            return 20.0

        hist_prev = macd_prev_data.get("histogram") if isinstance(macd_prev_data, dict) else None

        if macd_val > signal_val:
            if hist_val is not None and hist_prev is not None:
                return 40.0 if hist_val > hist_prev else 32.0
            return 36.0

        if hist_val is not None and hist_prev is not None:
            return 16.0 if hist_val > hist_prev else 8.0
        return 12.0

    def _calc_rsi5_trigger_score(
        self,
        short_rsi: Optional[float],
        prev_short_rsi: Optional[float],
    ) -> float:
        """短期反転トリガー RSI5 を評価する（0〜10点）。"""
        if short_rsi is None or prev_short_rsi is None:
            return 5.0
        if short_rsi > prev_short_rsi:
            if 30.0 <= short_rsi <= 70.0:
                return 10.0
            return 6.0
        if 45.0 <= short_rsi <= 70.0:
            return 4.0
        if short_rsi > 80.0:
            return 0.0
        return 1.0

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        if max_val == min_val:
            return 50.0
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))


# レジストリに特徴量クラスを登録
feature_registry.register(MomentumScore)
