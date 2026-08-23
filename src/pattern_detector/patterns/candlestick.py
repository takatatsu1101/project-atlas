
from typing import List, Dict, Any
import pandas as pd

from src.pattern_detector.interfaces import IPattern
from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternResultModel
from src.pattern_detector.registry import pattern_registry

class HammerPattern(IPattern):
    pattern_id: str = "P001_Hammer"
    pattern_name: str = "ハンマー"
    pattern_category: str = "Candlestick"

    def detect(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel]
    ) -> List[PatternResultModel]:
        
        results: List[PatternResultModel] = []
        if len(ohlcv_data) < 1:
            return results
        
        for i in range(len(ohlcv_data)):
            current_ohlcv = ohlcv_data[i]

            # ハンマーの検出ロジック
            # 1. 小さな実体（openとcloseが近い）
            # 2. 長い下ヒゲ（実体の2倍以上）
            # 3. 上ヒゲがほとんどない、または非常に短い
            
            body = abs(current_ohlcv.close - current_ohlcv.open)
            lower_shadow = min(current_ohlcv.open, current_ohlcv.close) - current_ohlcv.low
            upper_shadow = current_ohlcv.high - max(current_ohlcv.open, current_ohlcv.close)

            # 実体が非常に小さいこと（例：ローソク足全体の高さの20%未満）
            candle_range = current_ohlcv.high - current_ohlcv.low
            is_small_body = body < candle_range * 0.2 if candle_range > 0 else False

            # 長い下ヒゲ（実体の2倍以上）
            is_long_lower_shadow = lower_shadow >= body * 2 if body > 0 else lower_shadow > 0.05 * current_ohlcv.open # 実体がない場合の考慮

            # 上ヒゲがほとんどない、または非常に短い（実体以下）
            is_small_upper_shadow = upper_shadow < body if body > 0 else upper_shadow < 0.01 * current_ohlcv.open # upper_shadow < body * 0.5 などで調整可能

            # 終値が安値に近い (下ヒゲが長いことを補強する条件)
            is_close_to_high = (max(current_ohlcv.open, current_ohlcv.close) - current_ohlcv.high) / (candle_range + 1e-9) < 0.1

            if is_small_body and is_long_lower_shadow and is_small_upper_shadow and is_close_to_high: # 条件を強化
                confidence = self._calculate_confidence({
                    "body": body, 
                    "lower_shadow": lower_shadow, 
                    "upper_shadow": upper_shadow,
                    "open": current_ohlcv.open,
                    "close": current_ohlcv.close,
                    "high": current_ohlcv.high,
                    "low": current_ohlcv.low
                })
                results.append(PatternResultModel(
                    pattern_id=self.pattern_id,
                    pattern_name=self.pattern_name,
                    confidence=confidence,
                    metadata={
                        "date": current_ohlcv.date,
                        "open": current_ohlcv.open,
                        "high": current_ohlcv.high,
                        "low": current_ohlcv.low,
                        "close": current_ohlcv.close,
                    }
                ))
        return results

    def _calculate_confidence(self, detected_pattern_properties: Dict[str, Any]) -> float:
        """
        ハンマーパターンの信頼度を計算する（0-100）。
        下ヒゲが長いほど、上ヒゲが短いほど信頼度が高い。
        """
        body = detected_pattern_properties["body"]
        lower_shadow = detected_pattern_properties["lower_shadow"]
        upper_shadow = detected_pattern_properties["upper_shadow"]

        # 下ヒゲの長さが実体に対してどれくらい大きいか
        lower_ratio = lower_shadow / (body + 1e-9) # ゼロ除算対策
        # 上ヒゲの長さが実体に対してどれくらい小さいか
        upper_ratio = upper_shadow / (body + 1e-9) if body > 0 else 0.0 # bodyが0の場合も考慮

        # 理想的なハンマー (lower_ratioが高い、upper_ratioが低い) に近づくほど高スコア
        # シンプルな例: lower_ratioを直接信頼度に、upper_ratioはペナルティ
        confidence = min(100.0, max(0.0, (lower_ratio * 30.0) - (upper_ratio * 50.0) + 50.0))
        
        # 実体が非常に小さいほど加点
        if body < 0.05 * detected_pattern_properties["open"]: # 例: 始値の5%以下
            confidence += 10

        return min(100.0, max(0.0, confidence))

# レジストリにパターンクラスを登録
pattern_registry.register(HammerPattern)
