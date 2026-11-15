
from typing import List, Dict, Optional
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

    def calculate_highest_high(self, ohlcv_data: List[OhlcvModel], period: int = 20) -> List[float]:
        """
        当日を含む直近 period 営業日のレンジ最高値（HIGHEST_HIGH）を計算する。
        （※ ブレイクアウト判定用の前日以前高値は P002_BreakoutScore 側で別途算出される）
        """
        df = pd.DataFrame([o.model_dump() for o in ohlcv_data])
        if df.empty:
            return []
        df["high"] = pd.to_numeric(df["high"])
        return [float(v) for v in df["high"].rolling(window=period, min_periods=1).max().tolist()]

    def calculate_lowest_low(self, ohlcv_data: List[OhlcvModel], period: int = 20) -> List[float]:
        """
        当日を含む直近 period 営業日のレンジ最安値（LOWEST_LOW）を計算する。
        """
        df = pd.DataFrame([o.model_dump() for o in ohlcv_data])
        if df.empty:
            return []
        df["low"] = pd.to_numeric(df["low"])
        return [float(v) for v in df["low"].rolling(window=period, min_periods=1).min().tolist()]

    def calculate_atr(self, ohlcv_data: List[OhlcvModel], period: int = 14) -> List[float]:
        """
        True Range の period 日単純移動平均（ATR）を計算する。
        """
        df = pd.DataFrame([o.model_dump() for o in ohlcv_data])
        if df.empty:
            return []
        high = pd.to_numeric(df["high"])
        low = pd.to_numeric(df["low"])
        close = pd.to_numeric(df["close"])
        prev_close = close.shift(1)

        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        return [float(v) for v in atr.tolist()]

    def calculate_volume_ratio(self, ohlcv_data: List[OhlcvModel], period: int = 20) -> List[Optional[float]]:
        """
        当日出来高 ÷ 直近 period 日平均出来高を計算する（0除算時は None）。
        """
        df = pd.DataFrame([o.model_dump() for o in ohlcv_data])
        if df.empty:
            return []
        volume = pd.to_numeric(df["volume"])
        avg_volume = volume.rolling(window=period, min_periods=1).mean()

        ratios: List[Optional[float]] = []
        for vol, avg_vol in zip(volume.tolist(), avg_volume.tolist()):
            if pd.isna(vol) or pd.isna(avg_vol) or avg_vol == 0:
                ratios.append(None)
            else:
                ratios.append(float(vol / avg_vol))
        return ratios

    def calculate_indicators(self, ohlcv_data: List[OhlcvModel]) -> List[IndicatorSetModel]:
        """
        OHLCVデータリストからテクニカル指標のセットを計算して返す（キャッシュ対応）。
        """
        if not ohlcv_data:
            return []

        symbol = ohlcv_data[0].symbol
        cache_path = f"cache/indicators_{symbol}.json"

        # キャッシュのチェック（件数・最終日付一致かつ最新要素に LOWEST_LOW_20 が含まれている場合のみ利用）
        cached_data = self.storage.load_json(cache_path)
        if (
            cached_data is not None
            and isinstance(cached_data, list)
            and len(cached_data) == len(ohlcv_data)
            and len(cached_data) > 0
            and isinstance(cached_data[-1], dict)
            and str(cached_data[-1].get("date", ""))[:10] == ohlcv_data[-1].date.isoformat()[:10]
            and "LOWEST_LOW_20" in cached_data[-1].get("indicators", {})
        ):
            logger.info(f"{symbol} のテクニカル指標をキャッシュからロードしました。")
            return [IndicatorSetModel(**item) for item in cached_data]

        # SMA(5, 25, 75)、RSI(14)、MACD、および高値/安値・ATR14・出来高倍率を計算
        sma_5 = self.calculate_sma(ohlcv_data, 5)
        sma_25 = self.calculate_sma(ohlcv_data, 25)
        sma_75 = self.calculate_sma(ohlcv_data, 75)
        rsi_14 = self.calculate_rsi(ohlcv_data, 14)
        macd_data = self.calculate_macd(ohlcv_data)
        highest_high_20 = self.calculate_highest_high(ohlcv_data, 20)
        lowest_low_20 = self.calculate_lowest_low(ohlcv_data, 20)
        atr_14 = self.calculate_atr(ohlcv_data, 14)
        volume_ratio = self.calculate_volume_ratio(ohlcv_data, 20)

        indicator_sets: List[IndicatorSetModel] = []
        for i, ohlcv in enumerate(ohlcv_data):
            indicators = {
                "SMA5": sma_5[i] if i < len(sma_5) and not pd.isna(sma_5[i]) else None,
                "SMA25": sma_25[i] if i < len(sma_25) and not pd.isna(sma_25[i]) else None,
                "SMA75": sma_75[i] if i < len(sma_75) and not pd.isna(sma_75[i]) else None,
                "RSI14": rsi_14[i] if i < len(rsi_14) and not pd.isna(rsi_14[i]) else None,
                "MACD": macd_data[i] if i < len(macd_data) else None,
                "HIGHEST_HIGH_20": highest_high_20[i] if i < len(highest_high_20) and not pd.isna(highest_high_20[i]) else None,
                "LOWEST_LOW_20": lowest_low_20[i] if i < len(lowest_low_20) and not pd.isna(lowest_low_20[i]) else None,
                "ATR14": atr_14[i] if i < len(atr_14) and not pd.isna(atr_14[i]) else None,
                "VOLUME_RATIO": volume_ratio[i] if i < len(volume_ratio) else None,
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
