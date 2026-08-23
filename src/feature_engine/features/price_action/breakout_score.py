from typing import List, Optional

from src.feature_engine.interfaces import IFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel
from src.feature_engine.registry import feature_registry

class BreakoutScore(IFeature):
    feature_id: str = "P002_BreakoutScore"
    feature_name: str = "ブレイクアウト評価"
    feature_category: str = "PriceAction"

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

            # 過去N日間（ここでは20日間。前日からさかのぼる）の最高値を取得
            # 最小で5日間の過去データがあれば評価対象とする
            min_past_days = 5
            max_past_days = 20

            highest_high = None
            if i >= min_past_days:
                past_start_idx = max(0, i - max_past_days)
                past_end_idx = i # 今日（インデックス i）は含めない過去の最高値
                
                # 過去のOHLCVデータから最高値(high)を計算
                past_highs = [ohlcv_data[j].high for j in range(past_start_idx, past_end_idx)]
                if past_highs:
                    highest_high = max(past_highs)

            metadata = {
                "close": close_price,
                "highest_high": highest_high,
                "past_days_calculated": i if i < max_past_days else max_past_days
            }

            # 必要なデータが揃っていない場合は中立（データ不足評価）
            if highest_high is None or close_price is None or highest_high == 0:
                raw_score = 30.0  # データ不足時は低めのスコア
            else:
                # パターンA: すでにブレイクアウト中 (今日終値が過去高値を超えている)
                if close_price > highest_high:
                    break_rate = (close_price - highest_high) / highest_high

                    # A-1. 健全な上抜け初動 (0%〜5%の範囲)
                    if break_rate <= 0.05:
                        # 5%で90点、0%に近いほど100点に近づく
                        raw_score = 100.0 - (break_rate / 0.05) * 10.0 # 90〜100
                    
                    # A-2. 強いブレイク（少し買い遅れ、5%超〜15%以下）
                    elif break_rate <= 0.15:
                        # 5%で90点、15%で70点に線形に減少
                        raw_score = 90.0 - ((break_rate - 0.05) / 0.10) * 20.0 # 70〜90
                    
                    # A-3. 急騰しすぎ、高値掴みの警戒 (15%を超える上昇)
                    else:
                        raw_score = 50.0 # 過熱感のため中立スコアに戻る
                
                # パターンB: ブレイクアウト間近、または高値の下にある
                else:
                    dist_rate = (highest_high - close_price) / highest_high

                    # B-1. ブレイク目前 (2%以内の近さ)
                    if dist_rate <= 0.02:
                        # 0%に近いほど90点、2%で70点
                        raw_score = 90.0 - (dist_rate / 0.02) * 20.0 # 70〜90
                    
                    # B-2. 射程圏内 (2%超〜5%以下)
                    elif dist_rate <= 0.05:
                        # 2%で70点、5%で50点に線形に減少
                        raw_score = 70.0 - ((dist_rate - 0.02) / 0.03) * 20.0 # 50〜70
                    
                    # B-3. まだ遠い (5%を超える距離)
                    else:
                        # 5%で50点、10%で20点まで減少、10%超は一律20点
                        if dist_rate <= 0.10:
                            raw_score = 50.0 - ((dist_rate - 0.05) / 0.05) * 30.0 # 20〜50
                        else:
                            raw_score = 20.0 # レンジ継続、または下降基調

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
            return 50.0
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))

# レジストリに特徴量クラスを登録
feature_registry.register(BreakoutScore)
