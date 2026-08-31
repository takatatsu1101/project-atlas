
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
feature_registry.register(TrendStrengthFeature)


class TrendStrengthScore(IFeature):
    feature_id: str = "T001_TrendStrengthScore"
    feature_name: str = "トレンド強度"
    feature_category: str = "Trend"

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
            close_price = ohlcv_data[i].close if i < len(ohlcv_data) else None

            # 5日前のインデックス
            prev_idx = max(0, i - 5)
            sma5_prev = indicator_data[prev_idx].indicators.get("SMA5") if prev_idx < len(indicator_data) else None
            sma25_prev = indicator_data[prev_idx].indicators.get("SMA25") if prev_idx < len(indicator_data) else None
            sma75_prev = indicator_data[prev_idx].indicators.get("SMA75") if prev_idx < len(indicator_data) else None

            low_today = ohlcv_data[i].low if i < len(ohlcv_data) else None
            high_today = ohlcv_data[i].high if i < len(ohlcv_data) else None
            low_prev = ohlcv_data[prev_idx].low if prev_idx < len(ohlcv_data) else None
            high_prev = ohlcv_data[prev_idx].high if prev_idx < len(ohlcv_data) else None

            metadata = {
                "close": close_price,
                "sma5": sma5,
                "sma25": sma25,
                "sma75": sma75,
            }

            # データ不足時は一律で中立(50.0)とする
            if sma5 is None or sma25 is None or sma75 is None or close_price is None:
                raw_score = 50.0
            else:
                score = 0.0

                # 1. 移動平均線の並び (最大40点)
                if sma5 > sma25 and sma25 > sma75:
                    score += 40.0 # 完全上昇
                elif sma5 > sma25 and sma25 <= sma75:
                    score += 30.0 # 上昇の初期（短期は中期のうえだが中長期はデッドクロス）
                elif sma5 <= sma25 and sma25 > sma75:
                    score += 20.0 # 上昇トレンド中の押し目・一時調整
                elif sma5 < sma25 and sma25 < sma75:
                    score += 0.0  # 完全下降
                else:
                    score += 10.0 # その他

                # 2. 移動平均線の傾き (最大30点)
                # 5日前の値と比較して、上向きであるかどうかを評価
                if sma5_prev is not None and sma5 > sma5_prev:
                    score += 10.0
                if sma25_prev is not None and sma25 > sma25_prev:
                    score += 10.0
                if sma75_prev is not None and sma75 > sma75_prev:
                    score += 10.0

                # 3. 株価位置 (最大20点)
                if close_price > sma25:
                    score += 10.0
                if close_price > sma75:
                    score += 10.0

                # 4. 高値・安値更新 (最大10点)
                if low_today is not None and low_prev is not None and low_today > low_prev:
                    score += 5.0  # 安値切り上げ
                if high_today is not None and high_prev is not None and high_today > high_prev:
                    score += 5.0  # 高値切り上げ

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
feature_registry.register(TrendStrengthScore)
