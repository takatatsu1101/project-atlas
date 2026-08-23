from typing import List, Optional

from src.feature_engine.interfaces import IFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel
from src.feature_engine.registry import feature_registry

class FinancialHealthScore(IFeature):
    feature_id: str = "F004_FinancialHealthScore"
    feature_name: str = "財務健全性スコア"
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
                eps = financial_data.eps
                bps = financial_data.bps
                operating_profit = financial_data.operating_profit
                net_profit = financial_data.net_profit

                metadata = {
                    "eps": eps,
                    "bps": bps,
                    "operating_profit": operating_profit,
                    "net_profit": net_profit
                }

                # 必要なデータが不足している場合は50.0
                if eps is None or bps is None or operating_profit is None or net_profit is None:
                    raw_score = 50.0
                else:
                    score = 0.0

                    # 1. 自己資本の蓄積評価 (最大50点)
                    # BPS（純資産）が1株利益（EPS）に対して十分に厚く蓄積されているか
                    if bps > eps:
                        score += 50.0
                    elif bps > 0:
                        score += 30.0
                    else:
                        score += 0.0 # 債務超過傾向など

                    # 2. 利益の黒字・破綻回避安定性評価 (最大50点)
                    if operating_profit > 0 and net_profit > 0:
                        score += 50.0 # 本業・最終とも黒字
                    elif operating_profit > 0 or net_profit > 0:
                        score += 25.0 # 片方のみ黒字
                    else:
                        score += 0.0  # 両方赤字

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
feature_registry.register(FinancialHealthScore)
