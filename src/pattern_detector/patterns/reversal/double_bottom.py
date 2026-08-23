from typing import List, Dict, Any

from src.pattern_detector.interfaces import IPattern
from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternResultModel
from src.pattern_detector.registry import pattern_registry

class DoubleBottomPattern(IPattern):
    pattern_id: str = "R001_DoubleBottom"
    pattern_name: str = "ダブルボトム"
    pattern_category: str = "Reversal"

    def detect(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel]
    ) -> List[PatternResultModel]:
        
        results: List[PatternResultModel] = []
        if len(ohlcv_data) < 15: # 最低限の期間が必要
            return results

        # 各日 i においてダブルボトムが成立・形成されているかを検知
        for i in range(10, len(ohlcv_data)):
            current_close = ohlcv_data[i].close

            # 過去の安値極小点（谷）を走査して見つける
            # 谷の判定: 前後2日間で最も安値が低い点
            troughs = []
            for j in range(2, i - 2):
                low_j = ohlcv_data[j].low
                if (low_j < ohlcv_data[j-1].low and 
                    low_j < ohlcv_data[j-2].low and 
                    low_j < ohlcv_data[j+1].low and 
                    low_j < ohlcv_data[j+2].low):
                    troughs.append(j)

            # 直近の2つの谷があるか確認
            if len(troughs) < 2:
                continue

            v1_idx = troughs[-2] # 1つ目の谷
            v2_idx = troughs[-1] # 2つ目の谷（直近）

            v1_low = ohlcv_data[v1_idx].low
            v2_low = ohlcv_data[v2_idx].low

            # 2つの谷の価格差が2.5%以内であること（底値の整合性）
            price_diff_rate = abs(v1_low - v2_low) / v1_low
            if price_diff_rate > 0.025:
                continue

            # 2つの谷の間にある最高値（ネックライン）を検出
            neck_idx = v1_idx + 1
            for j in range(v1_idx + 1, v2_idx):
                if ohlcv_data[j].high > ohlcv_data[neck_idx].high:
                    neck_idx = j

            neck_high = ohlcv_data[neck_idx].high

            # パターン判定
            # 今日の終値が、直近の谷の安値を下回っている場合はサポート割れで不成立
            if current_close < min(v1_low, v2_low):
                continue

            # 信頼度の計算
            confidence = self._calculate_confidence({
                "close": current_close,
                "v2_low": v2_low,
                "neck_high": neck_high
            })

            if confidence >= 40.0:
                results.append(PatternResultModel(
                    pattern_id=self.pattern_id,
                    pattern_name=self.pattern_name,
                    confidence=confidence,
                    metadata={
                        "date": ohlcv_data[i].date,
                        "v1_date": ohlcv_data[v1_idx].date,
                        "v2_date": ohlcv_data[v2_idx].date,
                        "neck_date": ohlcv_data[neck_idx].date,
                        "v1_low": v1_low,
                        "v2_low": v2_low,
                        "neck_high": neck_high,
                        "close": current_close
                    }
                ))

        return results

    def _calculate_confidence(self, detected_pattern_properties: Dict[str, Any]) -> float:
        """
        ダブルボトムの信頼度を計算する (40〜100)。
        """
        current_close = detected_pattern_properties["close"]
        v2_low = detected_pattern_properties["v2_low"]
        neck_high = detected_pattern_properties["neck_high"]

        confidence = 0.0

        # ネックラインを上抜けている（ダブルボトム完成）
        if current_close > neck_high:
            break_rate = (current_close - neck_high) / neck_high
            if break_rate <= 0.05:
                confidence = 100.0 - (break_rate / 0.05) * 15.0 # 85〜100点
            else:
                confidence = 85.0 - (min(0.15, break_rate - 0.05) / 0.10) * 15.0 # 70〜85点
        # ネックラインの下にあるが、2つ目の谷から反発して上昇している状態
        elif current_close > v2_low:
            recovery_rate = (current_close - v2_low) / (neck_high - v2_low) if neck_high > v2_low else 0.5
            confidence = 40.0 + recovery_rate * 35.0 # 40〜75点

        return min(100.0, max(0.0, confidence))

# レジストリにパターンクラスを登録
pattern_registry.register(DoubleBottomPattern)
