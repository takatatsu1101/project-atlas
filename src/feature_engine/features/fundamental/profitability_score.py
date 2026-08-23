from typing import List, Optional

from src.feature_engine.interfaces import IFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel
from src.feature_engine.registry import feature_registry

class ProfitabilityScore(IFeature):
    feature_id: str = "F001_ProfitabilityScore"
    feature_name: str = "収益性スコア"
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
                # 財務データがない場合は一律50.0（中立）
                raw_score = 50.0
            else:
                roe = financial_data.roe
                roa = financial_data.roa
                revenue = financial_data.revenue
                operating_profit = financial_data.operating_profit

                metadata = {
                    "roe": roe,
                    "roa": roa,
                    "revenue": revenue,
                    "operating_profit": operating_profit
                }

                # 必要なデータが不足している場合は50.0
                if roe is None or roa is None or revenue is None or operating_profit is None or revenue == 0:
                    raw_score = 50.0
                else:
                    score = 0.0

                    # 1. ROEの評価 (最大40点)
                    # ROE >= 15% (40点), 10%以上 (30点), 5%以上 (20点), 0%以上 (10点)
                    if roe >= 15.0:
                        score += 40.0
                    elif roe >= 10.0:
                        score += 30.0
                    elif roe >= 5.0:
                        score += 20.0
                    elif roe >= 0.0:
                        score += 10.0
                    else:
                        score += 0.0

                    # 2. ROAの評価 (最大30点)
                    # ROA >= 10% (30点), 5%以上 (20点), 0%以上 (10点)
                    if roa >= 10.0:
                        score += 30.0
                    elif roa >= 5.0:
                        score += 20.0
                    elif roa >= 0.0:
                        score += 10.0
                    else:
                        score += 0.0

                    # 3. 営業利益率の評価 (最大30点)
                    op_margin = (operating_profit / revenue) * 100.0
                    metadata["operating_profit_margin"] = op_margin

                    # 営業利益率 >= 15% (30点), 10%以上 (20点), 5%以上 (10点)
                    if op_margin >= 15.0:
                        score += 30.0
                    elif op_margin >= 10.0:
                        score += 20.0
                    elif op_margin >= 5.0:
                        score += 10.0
                    else:
                        score += 0.0

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
feature_registry.register(ProfitabilityScore)
