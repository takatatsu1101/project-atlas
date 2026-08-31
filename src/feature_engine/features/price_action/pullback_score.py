from typing import List, Optional

from src.feature_engine.interfaces import IFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel
from src.feature_engine.registry import feature_registry

class PullbackScore(IFeature):
    feature_id: str = "P001_PullbackScore"
    feature_name: str = "押し目評価"
    feature_category: str = "PriceAction"

    def calculate(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        financial_data: Optional[FinancialModel] = None
    ) -> List[FeatureResultModel]:
        
        if not indicator_data or not ohlcv_data:
            return []

        results: List[FeatureResultModel] = []
        for i, ind_set in enumerate(indicator_data):
            sma5 = ind_set.indicators.get("SMA5")
            sma25 = ind_set.indicators.get("SMA25")
            sma75 = ind_set.indicators.get("SMA75")
            
            # 対応するインデックスのOHLCVデータを取得
            close_price = ohlcv_data[i].close if i < len(ohlcv_data) else None

            metadata = {
                "sma5": sma5,
                "sma25": sma25,
                "sma75": sma75,
                "close": close_price
            }

            # 必要なデータが揃っていない場合は中立（データ不足評価）
            if sma25 is None or sma75 is None or close_price is None:
                raw_score = 30.0  # データ不足時は押し目とは評価しづらいため低めのスコア
            else:
                # 1. 前提条件: 中長期が上昇トレンドであること (SMA25 > SMA75) かつ 価格が長期線の上にあること
                is_uptrend = (sma25 > sma75) and (close_price > sma75)

                if not is_uptrend:
                    raw_score = 10.0 # トレンドが崩れているか下降トレンドなので押し目評価は非常に低い
                else:
                    # 2. SMA25に対する乖離率を算出
                    dist_to_sma25 = (close_price - sma25) / sma25

                    # パターンA: SMA25の直上 (0%〜3%の範囲。最も理想的な押し目)
                    if 0.0 <= dist_to_sma25 <= 0.03:
                        # 0%に近いほど100点に近づく
                        raw_score = 100.0 - (dist_to_sma25 / 0.03) * 20.0 # 80〜100
                    
                    # パターンB: SMA25をわずかに割り込んでいる (-2%〜0%未満。深めの押し目)
                    elif -0.02 <= dist_to_sma25 < 0.0:
                        # 0%に近いほど80点に近づき、-2%に近いほど60点になる
                        raw_score = 80.0 - (abs(dist_to_sma25) / 0.02) * 20.0 # 60〜80
                    
                    # パターンC: まだ押し目が浅い (3%を超える上昇継続中)
                    elif dist_to_sma25 > 0.03:
                        if dist_to_sma25 <= 0.10:
                            # 3%で80点、10%で40点へ線形に減少
                            raw_score = 80.0 - ((dist_to_sma25 - 0.03) / 0.07) * 40.0 # 40〜80
                        else:
                            raw_score = 40.0 # かなり上に乖離している
                    
                    # パターンD: SMA25を大きく割り込んでいるが、SMA75の上にある場合
                    else:
                        # SMA75に対する距離を確認
                        dist_to_sma75 = (close_price - sma75) / sma75
                        # SMA75の直上 (0%〜2%の範囲。長期線サポート期待の押し目)
                        if 0.0 <= dist_to_sma75 <= 0.02:
                            # 0%に近いほど70点、2%に近いほど50点
                            raw_score = 70.0 - (dist_to_sma75 / 0.02) * 20.0 # 50〜70
                        else:
                            raw_score = 20.0 # 長期線サポートからも外れそう、または割り込んでいる

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
            return 50.0
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))

# レジストリに特徴量クラスを登録
feature_registry.register(PullbackScore)
