from typing import List, Optional

from src.feature_engine.interfaces import IFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel
from src.feature_engine.registry import feature_registry

class VolumeScore(IFeature):
    feature_id: str = "V001_VolumeScore"
    feature_name: str = "出来高評価"
    feature_category: str = "Volume"

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
            open_price = ohlcv_data[i].open if i < len(ohlcv_data) else None
            volume_today = ohlcv_data[i].volume if i < len(ohlcv_data) else None

            # 過去の平均出来高や出来高移動平均の算出
            # 最小で5日間のデータがあれば計算可能とする
            min_past_days = 5
            max_past_days = 25

            avg_volume_25 = None
            vma5 = None
            vma25 = None

            if i >= min_past_days:
                # 過去25日間（今日を含む）の平均出来高
                start_idx = max(0, i - max_past_days + 1)
                end_idx = i + 1
                volumes_25 = [ohlcv_data[j].volume for j in range(start_idx, end_idx) if ohlcv_data[j].volume is not None]
                if volumes_25:
                    avg_volume_25 = sum(volumes_25) / len(volumes_25)
                    vma25 = avg_volume_25

                # 過去5日間の平均出来高
                start_idx_5 = max(0, i - 5 + 1)
                volumes_5 = [ohlcv_data[j].volume for j in range(start_idx_5, end_idx) if ohlcv_data[j].volume is not None]
                if volumes_5:
                    vma5 = sum(volumes_5) / len(volumes_5)

            metadata = {
                "volume": volume_today,
                "avg_volume_25": avg_volume_25,
                "vma5": vma5,
                "vma25": vma25
            }

            # データ不足時は一律で中立(50.0)
            if volume_today is None or avg_volume_25 is None or avg_volume_25 == 0 or vma5 is None or vma25 is None or vma25 == 0:
                raw_score = 50.0
            else:
                score = 0.0

                # 1. 出来高の急増水準 (最大40点)
                volume_ratio = volume_today / avg_volume_25
                if volume_ratio >= 2.0:
                    score += 40.0
                elif volume_ratio >= 1.5:
                    score += 30.0
                elif volume_ratio >= 1.0:
                    score += 20.0
                elif volume_ratio >= 0.5:
                    score += 10.0
                else:
                    score += 0.0

                # 2. 出来高の短期的な変化トレンド (最大35点)
                if vma5 >= vma25 * 1.3:
                    score += 35.0
                elif vma5 >= vma25:
                    score += 25.0
                elif vma5 >= vma25 * 0.7:
                    score += 15.0
                else:
                    score += 5.0

                # 3. 株価の方向性と出来高の整合性 (最大25点)
                if open_price is not None and close_price is not None:
                    # 陽線の場合
                    if close_price > open_price:
                        if volume_today > avg_volume_25:
                            score += 25.0  # 買いの信頼性高
                        else:
                            score += 15.0  # 薄商いの上昇
                    # 陰線の場合
                    elif close_price < open_price:
                        if volume_today < avg_volume_25:
                            score += 15.0  # 健全な小幅調整
                        else:
                            score += 0.0   # 大口の売り抜け警戒
                    # 同値の場合
                    else:
                        score += 10.0
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
feature_registry.register(VolumeScore)
