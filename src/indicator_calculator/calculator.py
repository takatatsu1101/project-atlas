
from typing import List, Dict
import pandas as pd

from src.model.data_models import OhlcvModel, IndicatorSetModel
from src.common.storage import StorageManager
from src.common.logger import get_logger

logger = get_logger("IndicatorCalculator")

class IndicatorCalculator:
    def __init__(self):
        self.storage = StorageManager()
    def calculate_sma(self, ohlcv_data: List[OhlcvModel], period: int) -> List[float]:
        """
        単純移動平均 (SMA) を計算する。
        """
        df = pd.DataFrame([o.model_dump() for o in ohlcv_data])
        if df.empty:
            return []
        df["close"] = pd.to_numeric(df["close"])
        sma = df["close"].rolling(window=period).mean().tolist()
        return sma

    def calculate_rsi(self, ohlcv_data: List[OhlcvModel], period: int) -> List[float]:
        """
        相対力指数 (RSI) を計算する。
        """
        df = pd.DataFrame([o.model_dump() for o in ohlcv_data])
        if df.empty:
            return []
        df["close"] = pd.to_numeric(df["close"])
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=period, min_periods=1).mean()
        avg_loss = loss.rolling(window=period, min_periods=1).mean()

        rs = avg_gain / avg_loss.replace(0, 1e-9) # 0除算対策
        rsi = 100 - (100 / (1 + rs))
        return rsi.tolist()

    def calculate_macd(self, ohlcv_data: List[OhlcvModel], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> List[Dict[str, float]]:
        """
        MACD (Moving Average Convergence Divergence) を計算する。
        """
        df = pd.DataFrame([o.model_dump() for o in ohlcv_data])
        if df.empty:
            return []
        df["close"] = pd.to_numeric(df["close"])

        ema_fast = df["close"].ewm(span=fast_period, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow_period, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=signal_period, adjust=False).mean()
        histogram = macd - signal

        result = []
        for i in range(len(macd)):
            result.append({"macd": macd.iloc[i], "signal": signal.iloc[i], "histogram": histogram.iloc[i]})
        return result

    def calculate_indicators(self, ohlcv_data: List[OhlcvModel]) -> List[IndicatorSetModel]:
        """
        OHLCVデータリストからテクニカル指標のセットを計算して返す（キャッシュ対応）。
        """
        if not ohlcv_data:
            return []

        symbol = ohlcv_data[0].symbol
        cache_path = f"cache/indicators_{symbol}.json"

        # キャッシュのチェック (同じデータ件数や最新日付が一致していればロード可能だが、シンプルにキャッシュファイルが存在すればロードする例)
        cached_data = self.storage.load_json(cache_path)
        if cached_data is not None and isinstance(cached_data, list) and len(cached_data) == len(ohlcv_data):
            logger.info(f"{symbol} のテクニカル指標をキャッシュからロードしました。")
            return [IndicatorSetModel(**item) for item in cached_data]

        # 例として、SMA(5, 25, 75)、RSI(14)、MACDを計算
        sma_5 = self.calculate_sma(ohlcv_data, 5)
        sma_25 = self.calculate_sma(ohlcv_data, 25)
        sma_75 = self.calculate_sma(ohlcv_data, 75)
        rsi_14 = self.calculate_rsi(ohlcv_data, 14)
        macd_data = self.calculate_macd(ohlcv_data)

        indicator_sets: List[IndicatorSetModel] = []
        for i, ohlcv in enumerate(ohlcv_data):
            indicators = {
                "SMA5": sma_5[i] if i < len(sma_5) and not pd.isna(sma_5[i]) else None,
                "SMA25": sma_25[i] if i < len(sma_25) and not pd.isna(sma_25[i]) else None,
                "SMA75": sma_75[i] if i < len(sma_75) and not pd.isna(sma_75[i]) else None,
                "RSI14": rsi_14[i] if i < len(rsi_14) and not pd.isna(rsi_14[i]) else None,
                "MACD": macd_data[i] if i < len(macd_data) else None,
            }
            indicator_sets.append(IndicatorSetModel(
                symbol=ohlcv.symbol,
                date=ohlcv.date,
                indicators={k: v for k, v in indicators.items() if v is not None}
            ))
        
        # 結果をJSONキャッシュとして保存
        try:
            self.storage.save_json([model.model_dump(mode="json") for model in indicator_sets], cache_path)
        except Exception as e:
            logger.warning(f"指標キャッシュの保存に失敗しました: {e}")

        logger.info(f"{symbol} のテクニカル指標を計算・キャッシュしました。")
        return indicator_sets

# モジュールレベルでインスタンス化
indicator_calculator = IndicatorCalculator()

def calculate_indicators(ohlcv_data: List[OhlcvModel]) -> List[IndicatorSetModel]:
    return indicator_calculator.calculate_indicators(ohlcv_data)
