from typing import List, Dict, Any, Optional, Sequence

from src.pattern_detector.interfaces import IPattern
from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternResultModel
from src.pattern_detector.patterns.reversal._common import find_double_reversal_candidates
from src.pattern_detector.registry import pattern_registry

class DoubleTopPattern(IPattern):
    pattern_id: str = "R002_DoubleTop"
    pattern_name: str = "ダブルトップ"
    pattern_category: str = "Reversal"

    def detect(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        target_indices: Optional[Sequence[int]] = None,
    ) -> List[PatternResultModel]:
        candidates = find_double_reversal_candidates(
            ohlcv_data,
            mode="top",
            target_indices=target_indices,
        )
        results: List[PatternResultModel] = []
        for cand in candidates:
            confidence = self._calculate_confidence({
                "close": cand.close,
                "t2_high": cand.e2_val,
                "neck_low": cand.neck_val,
            })

            if confidence >= 40.0:
                results.append(PatternResultModel(
                    pattern_id=self.pattern_id,
                    pattern_name=self.pattern_name,
                    confidence=confidence,
                    metadata={
                        "date": ohlcv_data[cand.index].date,
                        "t1_date": ohlcv_data[cand.e1_idx].date,
                        "t2_date": ohlcv_data[cand.e2_idx].date,
                        "neck_date": ohlcv_data[cand.neck_idx].date,
                        "t1_high": cand.e1_val,
                        "t2_high": cand.e2_val,
                        "neck_low": cand.neck_val,
                        "close": cand.close,
                    },
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
