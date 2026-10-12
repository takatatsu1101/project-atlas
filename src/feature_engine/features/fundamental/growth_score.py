from typing import List, Optional

from src.feature_engine.interfaces import IFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel
from src.feature_engine.registry import feature_registry

class GrowthScore(IFeature):
    feature_id: str = "F002_GrowthScore"
    feature_name: str = "成長性スコア"
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
                # 3年平均、5年平均、単年成長率の順に取得可能なデータを選択
                rev_growth_5y = financial_data.revenue_growth_5y_avg
                rev_growth_3y = financial_data.revenue_growth_3y_avg
                rev_growth_1y = financial_data.revenue_growth

                net_growth_5y = financial_data.net_profit_growth_5y_avg
                net_growth_3y = financial_data.net_profit_growth_3y_avg
                net_growth_1y = financial_data.net_profit_growth

                # 評価に用いる値の選定
                rev_growth_to_use = rev_growth_5y if rev_growth_5y is not None else (rev_growth_3y if rev_growth_3y is not None else rev_growth_1y)
                net_growth_to_use = net_growth_5y if net_growth_5y is not None else (net_growth_3y if net_growth_3y is not None else net_growth_1y)

                metadata = {
                    "revenue_growth_5y_avg": rev_growth_5y,
                    "revenue_growth_3y_avg": rev_growth_3y,
                    "revenue_growth": rev_growth_1y,
                    "net_profit_growth_5y_avg": net_growth_5y,
                    "net_profit_growth_3y_avg": net_growth_3y,
                    "net_profit_growth": net_growth_1y,
                    "rev_growth_evaluated": rev_growth_to_use,
                    "net_growth_evaluated": net_growth_to_use
                }

                # 評価用データがどちらも全くない場合は中立
                if rev_growth_to_use is None and net_growth_to_use is None:
                    raw_score = 50.0
                else:
                    score = 0.0

                    # 1. 売上高成長率評価 (最大50点)
                    if rev_growth_to_use is not None:
                        if rev_growth_to_use >= 15.0:
                            score += 50.0
                        elif rev_growth_to_use >= 10.0:
                            score += 40.0
                        elif rev_growth_to_use >= 5.0:
                            score += 30.0
                        elif rev_growth_to_use >= 0.0:
                            score += 15.0
                        else:
                            score += 0.0
                    else:
                        score += 25.0 # 売上高データがなければ中立点

                    # 2. 純利益成長率評価 (最大50点)
                    if net_growth_to_use is not None:
                        if net_growth_to_use >= 20.0:
                            score += 50.0
                        elif net_growth_to_use >= 10.0:
                            score += 40.0
                        elif net_growth_to_use >= 0.0:
                            score += 25.0
                        else:
                            score += 0.0
                    else:
                        score += 25.0 # 純利益データがなければ中立点

                    raw_score = score

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
        if max_val == min_val:
            return 50.0
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))

# レジストリに特徴量クラスを登録
feature_registry.register(GrowthScore)
