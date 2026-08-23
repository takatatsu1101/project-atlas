from typing import List, Optional

from src.feature_engine.interfaces import IFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel
from src.feature_engine.registry import feature_registry

class EarningsQualityScore(IFeature):
    feature_id: str = "F005_EarningsQualityScore"
    feature_name: str = "利益の質スコア"
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
                roe = financial_data.roe
                roa = financial_data.roa
                operating_profit = financial_data.operating_profit
                net_profit = financial_data.net_profit

                metadata = {
                    "roe": roe,
                    "roa": roa,
                    "operating_profit": operating_profit,
                    "net_profit": net_profit
                }

                # 必要なデータが不足している場合は50.0
                if roe is None or roa is None or operating_profit is None or net_profit is None:
                    raw_score = 50.0
                else:
                    score = 0.0

                    # 1. 本業と最終利益の整合性評価 (最大50点。本業利益と純利益の乖離が少ないか)
                    # 営業利益が0の場合はゼロ除算を避ける
                    if operating_profit != 0:
                        profit_ratio = net_profit / operating_profit
                        metadata["net_profit_to_operating_profit_ratio"] = profit_ratio

                        # 0.8〜1.2 は一時的要因に頼らず、かつ健全な本業利益が上がっている状態 (整合性高)
                        if 0.8 <= profit_ratio <= 1.2:
                            score += 50.0
                        elif 0.5 <= profit_ratio < 0.8 or 1.2 < profit_ratio <= 1.5:
                            score += 30.0
                        else:
                            score += 10.0 # 乖離が極めて大きい
                    else:
                        score += 10.0

                    # 2. レバレッジの健全性・安全性の評価 (最大50点。過度なレバレッジに頼っていないか)
                    # ROAが0の場合はゼロ除算を避ける
                    if roa != 0:
                        leverage_ratio = roe / roa
                        metadata["roe_to_roa_ratio"] = leverage_ratio

                        # 1.0〜2.5 は自己資本に対して健全な範囲での借入・レバレッジ効果
                        if 1.0 <= leverage_ratio <= 2.5:
                            score += 50.0
                        elif 2.5 < leverage_ratio <= 4.0:
                            score += 30.0
                        else:
                            score += 10.0 # レバレッジが高すぎる（リスク高）またはROE/ROAがマイナス
                    else:
                        score += 10.0

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
feature_registry.register(EarningsQualityScore)
