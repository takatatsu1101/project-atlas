from typing import List, Optional

from src.feature_engine.interfaces import IFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel
from src.feature_engine.registry import feature_registry

class ValuationScore(IFeature):
    feature_id: str = "F003_ValuationScore"
    feature_name: str = "割安性スコア"
    feature_category: str = "Fundamental"

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
            metadata = {}
            
            if financial_data is None:
                raw_score = 50.0 # 財務データなし
            else:
                per = financial_data.per
                pbr = financial_data.pbr

                metadata = {
                    "per": per,
                    "pbr": pbr
                }

                # 必要なデータが不足している場合は50.0
                if per is None or pbr is None:
                    raw_score = 50.0
                else:
                    score = 0.0

                    # 1. PERの評価 (最大50点。低いほど割安)
                    if 0.0 < per <= 10.0:
                        score += 50.0 # 非常に割安
                    elif 10.0 < per <= 15.0:
                        score += 40.0 # 標準的割安
                    elif 15.0 < per <= 25.0:
                        score += 30.0 # 適正範囲
                    elif 25.0 < per <= 40.0:
                        score += 15.0 # やや割高
                    else:
                        score += 5.0  # 超割高、または赤字 (per <= 0)

                    # 2. PBRの評価 (最大50点。低いほど割安)
                    if 0.0 < pbr <= 0.8:
                        score += 50.0 # 非常に割安
                    elif 0.8 < pbr <= 1.2:
                        score += 40.0 # 適正割安
                    elif 1.2 < pbr <= 2.0:
                        score += 30.0 # 適正
                    elif 2.0 < pbr <= 4.0:
                        score += 15.0 # やや割高
                    else:
                        score += 5.0  # 超割高、または債務超過 (pbr <= 0)

                    raw_score = score

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
feature_registry.register(ValuationScore)
