from typing import List, Optional

from src.feature_engine.interfaces import IFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel
from src.feature_engine.registry import feature_registry

class VolatilityScore(IFeature):
    feature_id: str = "R001_VolatilityScore"
    feature_name: str = "ボラティリティスコア"
    feature_category: str = "Risk"

    def calculate(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        financial_data: Optional[FinancialModel] = None
    ) -> List[FeatureResultModel]:
        
        if not ohlcv_data:
            return []

        results: List[FeatureResultModel] = []
        for i, ind_set in enumerate(indicator_data):
            close_price = ohlcv_data[i].close if i < len(ohlcv_data) else None

            # ATRの簡易計算
            # 最小で5日間の過去データが必要
            min_past_days = 5
            max_past_days = 20

            avg_atr = None
            tr_today = None

            if i >= min_past_days:
                # 過去の各日のTrue Rangeを計算
                true_ranges: List[float] = []
                for j in range(max(0, i - max_past_days), i + 1):
                    high = ohlcv_data[j].high
                    low = ohlcv_data[j].low
                    close_prev = ohlcv_data[j - 1].close if j > 0 else low
                    
                    if high is not None and low is not None:
                        tr = max(high - low, abs(high - close_prev), abs(low - close_prev))
                        true_ranges.append(tr)

                if true_ranges:
                    tr_today = true_ranges[-1] # 今日のTrue Range
                    avg_atr = sum(true_ranges) / len(true_ranges) # 過去平均ATR

            metadata = {
                "close": close_price,
                "tr_today": tr_today,
                "avg_atr": avg_atr
            }

            # データ不足時は一律で中立(50.0)
            if tr_today is None or avg_atr is None or avg_atr == 0:
                raw_score = 50.0
            else:
                volatility_ratio = tr_today / avg_atr

                # ボラティリティ急増 (2倍以上)
                if volatility_ratio >= 2.0:
                    raw_score = 100.0
                # 平均以上 (1.0倍〜2.0倍未満)
                elif volatility_ratio >= 1.0:
                    raw_score = 50.0 + (volatility_ratio - 1.0) * 50.0
                # 平均以下 (0.5倍〜1.0倍未満)
                elif volatility_ratio >= 0.5:
                    raw_score = 20.0 + ((volatility_ratio - 0.5) / 0.5) * 30.0
                # 閑散相場 (0.5倍未満)
                else:
                    raw_score = 20.0

            normalized_score = self._normalize_score(raw_score, 0, 100)

            results.append(FeatureResultModel(
                feature_id=self.feature_id,
                feature_name=self.feature_name,
                score=normalized_score,
                raw_value=raw_score,
                metadata=metadata
            ))
        return results

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        if max_val == min_val:
            return 50.0
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))

# レジストリに特徴量クラスを登録
feature_registry.register(VolatilityScore)
