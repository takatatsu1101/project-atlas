
from typing import List, Optional
import numpy as np

from src.feature_engine.interfaces import IFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel
from src.feature_engine.registry import feature_registry

class TrendStrengthFeature(IFeature):
    feature_id: str = "F001_TrendStrength"
    feature_name: str = "トレンド強度スコア"
    feature_category: str = "Trend"

    def calculate(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        financial_data: Optional[FinancialModel] = None
    ) -> List[FeatureResultModel]:
        
        if not indicator_data:
            return []

        results: List[FeatureResultModel] = []
        for i, ind_set in enumerate(indicator_data):
            sma5 = ind_set.indicators.get("SMA5")
            sma25 = ind_set.indicators.get("SMA25")
            sma75 = ind_set.indicators.get("SMA75")
            close_price = ohlcv_data[i].close if i < len(ohlcv_data) else None

            raw_score = 0.0
            metadata = {"sma5": sma5, "sma25": sma25, "sma75": sma75, "close": close_price}

            if sma5 is not None and sma25 is not None and sma75 is not None and close_price is not None:
                # ゴールデンクロス/デッドクロスに基づいた単純なトレンド強度
                if close_price > sma5 > sma25 > sma75: # 強い上昇トレンド
                    raw_score = 100.0
                elif close_price < sma5 < sma25 < sma75: # 強い下降トレンド
                    raw_score = 0.0
                elif sma5 > sma25 and sma25 > sma75: # 上昇トレンド
                    raw_score = 75.0
                elif sma5 < sma25 and sma25 < sma75: # 下降トレンド
                    raw_score = 25.0
                else:
                    # SMAの並び順が複雑な場合はレンジと判断
                    raw_score = 50.0 
            else:
                raw_score = 50.0 # データ不足の場合は中間値
            
            # ここでは簡単のため、raw_scoreをそのままscoreとして利用。本来は別途正規化ロジックを適用。
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
        """
        0-100の範囲でスコアを正規化する。
        """
        if max_val == min_val:
            return 50.0 # ゼロ除算を避ける
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))

# レジストリに特徴量クラスを登録
feature_registry.register(TrendStrengthFeature)
