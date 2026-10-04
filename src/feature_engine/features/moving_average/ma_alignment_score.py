
from typing import List, Optional
import numpy as np

from src.feature_engine.interfaces import IFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel
from src.feature_engine.registry import feature_registry

class MAAlignmentScore(IFeature):
    feature_id: str = "M001_MAAlignmentScore"
    feature_name: str = "移動平均線の並び評価"
    feature_category: str = "Moving Average"

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

            if sma5 is None or sma25 is None or sma75 is None:
                raw_score = 50.0  # データ不足の場合は中立
            # 強い上昇トレンド: 短期 > 中期 > 長期
            elif sma5 > sma25 and sma25 > sma75:
                raw_score = 100.0
            # 強い下降トレンド: 短期 < 中期 < 長期
            elif sma5 < sma25 and sma25 < sma75:
                raw_score = 0.0
            # 上昇基調 (強い上昇トレンドではないが、短期が中期・長期より上)
            elif sma5 > sma25 and sma5 > sma75:
                raw_score = 75.0
            # 下降基調 (強い下降トレンドではないが、短期が中期・長期より下)
            elif sma5 < sma25 and sma5 < sma75:
                raw_score = 25.0
            # その他の並びは中立
            else:
                raw_score = 50.0

            metadata = {"sma5": sma5, "sma25": sma25, "sma75": sma75}

            
            
            normalized_score = self._normalize_score(raw_score, 0, 100) 

            results.append(FeatureResultModel(
                feature_id=self.feature_id,
                feature_name=self.feature_name,
                score=normalized_score,
                raw_value=raw_score,
                metadata=metadata,
                date=ind_set.date
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
feature_registry.register(MAAlignmentScore)
