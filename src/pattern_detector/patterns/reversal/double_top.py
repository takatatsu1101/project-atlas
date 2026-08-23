from typing import List, Dict, Any

from src.pattern_detector.interfaces import IPattern
from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternResultModel
from src.pattern_detector.registry import pattern_registry

class DoubleTopPattern(IPattern):
    pattern_id: str = "R002_DoubleTop"
    pattern_name: str = "ダブルトップ"
    pattern_category: str = "Reversal"

    def detect(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel]
    ) -> List[PatternResultModel]:
        
        results: List[PatternResultModel] = []
        if len(ohlcv_data) < 15: # 最低限の期間が必要
            return results

        # 各日 i においてダブルトップが成立・形成されているかを検知
        for i in range(10, len(ohlcv_data)):
            current_close = ohlcv_data[i].close

            # 過去の高値極大点（山）を走査して見つける
            # 山の判定: 前後2日間で最も高値が高い点
            peaks = []
            for j in range(2, i - 2):
                high_j = ohlcv_data[j].high
                if (high_j > ohlcv_data[j-1].high and 
                    high_j > ohlcv_data[j-2].high and 
                    high_j > ohlcv_data[j+1].high and 
                    high_j > ohlcv_data[j+2].high):
                    peaks.append(j)

            # 直近の2つの山があるか確認
            if len(peaks) < 2:
                continue

            t1_idx = peaks[-2] # 1つ目の山
            t2_idx = peaks[-1] # 2つ目の山（直近）

            t1_high = ohlcv_data[t1_idx].high
            t2_high = ohlcv_data[t2_idx].high

            # 2つの山の価格差が2.5%以内であること（天井の整合性）
            price_diff_rate = abs(t1_high - t2_high) / t1_high
            if price_diff_rate > 0.025:
                continue

            # 2つの山の間にある最低安値（ネックライン）を検出
            neck_idx = t1_idx + 1
            for j in range(t1_idx + 1, t2_idx):
                if ohlcv_data[j].low < ohlcv_data[neck_idx].low:
                    neck_idx = j

            neck_low = ohlcv_data[neck_idx].low

            # パターン判定
            # 今日の終値が、直近の山の高値を上回っている場合はブレイクアウト（抵抗線上抜け）で不成立
            if current_close > max(t1_high, t2_high):
                continue

            # ネックラインと現在価格の整合性
            confidence = 0.0

            # ネックラインを下抜けている（ダブルトップ完成）
            if current_close < neck_low:
                # 下抜け直後は最も信頼度が高い。下抜け率5%以内で高スコア
                break_rate = (neck_low - current_close) / neck_low
                if break_rate <= 0.05:
                    confidence = 100.0 - (break_rate / 0.05) * 15.0 # 85〜100点
                else:
                    confidence = 85.0 - (min(0.15, break_rate - 0.05) / 0.10) * 15.0 # 70〜85点
            # ネックラインの上にあるが、2つ目の山から下落している状態
            elif current_close < t2_high:
                # 2つ目の山からの下落度合い
                fall_rate = (t2_high - current_close) / (t2_high - neck_low) if t2_high > neck_low else 0.5
                confidence = 40.0 + fall_rate * 35.0 # 40〜75点

            if confidence >= 40.0:
                results.append(PatternResultModel(
                    pattern_id=self.pattern_id,
                    pattern_name=self.pattern_name,
                    confidence=confidence,
                    metadata={
                        "date": ohlcv_data[i].date,
                        "t1_date": ohlcv_data[t1_idx].date,
                        "t2_date": ohlcv_data[t2_idx].date,
                        "neck_date": ohlcv_data[neck_idx].date,
                        "t1_high": t1_high,
                        "t2_high": t2_high,
                        "neck_low": neck_low,
                        "close": current_close
                    }
                ))

        return results

    def _calculate_confidence(self, detected_pattern_properties: Dict[str, Any]) -> float:
        """
        ダブルトップの信頼度を計算する (40〜100)。
        """
        current_close = detected_pattern_properties["close"]
        t2_high = detected_pattern_properties["t2_high"]
        neck_low = detected_pattern_properties["neck_low"]

        confidence = 0.0

        # ネックラインを下抜けている（ダブルトップ完成）
        if current_close < neck_low:
            break_rate = (neck_low - current_close) / neck_low
            if break_rate <= 0.05:
                confidence = 100.0 - (break_rate / 0.05) * 15.0 # 85〜100点
            else:
                confidence = 85.0 - (min(0.15, break_rate - 0.05) / 0.10) * 15.0 # 70〜85点
        # ネックラインの上にあるが、2つ目の山から下落している状態
        elif current_close < t2_high:
            fall_rate = (t2_high - current_close) / (t2_high - neck_low) if t2_high > neck_low else 0.5
            confidence = 40.0 + fall_rate * 35.0 # 40〜75点

        return min(100.0, max(0.0, confidence))

# レジストリにパターンクラスを登録
pattern_registry.register(DoubleTopPattern)
