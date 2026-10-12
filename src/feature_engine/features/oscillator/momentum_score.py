from typing import List, Optional

from src.feature_engine.interfaces import IFeature
from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel
from src.feature_engine.registry import feature_registry

class MomentumScore(IFeature):
    feature_id: str = "O001_MomentumScore"
    feature_name: str = "モメンタムスコア"
    feature_category: str = "Oscillator"

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
            rsi14 = ind_set.indicators.get("RSI14")
            macd_data = ind_set.indicators.get("MACD")

            # MACDの前日比を計算するために前日のデータも取得
            macd_prev_data = indicator_data[i - 1].indicators.get("MACD") if i > 0 else None

            metadata = {
                "rsi14": rsi14,
                "macd": macd_data
            }

            # データ不足時は一律で中立(50.0)とする
            if rsi14 is None:
                raw_score = 50.0
            else:
                score = 0.0

                # 1. RSI14 の評価 (最大50点)
                # RSI値をそのまま半分にして0〜50点のスコアとする
                score += rsi14 / 2.0

                # 2. MACD の評価 (最大50点)
                # MACDの値は辞書 {"macd": X, "signal": Y, "histogram": Z} となっていることを想定
                if isinstance(macd_data, dict):
                    macd_val = macd_data.get("macd")
                    signal_val = macd_data.get("signal")
                    hist_val = macd_data.get("histogram")

                    if macd_val is not None and signal_val is not None:
                        # ゴールデンクロス / 上昇の勢い
                        if macd_val > signal_val:
                            score += 30.0
                            # ヒストグラムの推移で加速・減速を判定
                            if hist_val is not None and isinstance(macd_prev_data, dict):
                                hist_prev = macd_prev_data.get("histogram")
                                if hist_prev is not None and hist_val > hist_prev:
                                    score += 20.0 # 加速
                                else:
                                    score += 10.0 # 減速
                            else:
                                score += 15.0 # 推移が不明な場合は中程度
                        # デッドクロス / 下降の勢い
                        else:
                            score += 10.0
                            if hist_val is not None and isinstance(macd_prev_data, dict):
                                hist_prev = macd_prev_data.get("histogram")
                                if hist_prev is not None and hist_val > hist_prev:
                                    score += 10.0 # 下降が和らいでいる（減速）
                                else:
                                    score += 0.0  # 下降が加速
                            else:
                                score += 5.0
                    else:
                        score += 25.0 # MACD詳細値が足りない場合は中立
                else:
                    score += 25.0 # MACDデータ自体がない場合は中立

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
feature_registry.register(MomentumScore)
