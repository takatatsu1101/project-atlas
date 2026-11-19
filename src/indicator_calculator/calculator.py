
import math
from typing import List, Dict, Optional
import pandas as pd

from src.model.data_models import OhlcvModel, IndicatorSetModel
from src.common.storage import StorageManager
from src.common.logger import get_logger

logger = get_logger("IndicatorCalculator")

class IndicatorCalculator:
    def __init__(self, storage: Optional[StorageManager] = None):
        self.storage = storage if storage is not None else StorageManager()

    @staticmethod
    def _compute_sma(close_series: pd.Series, period: int) -> List[float]:
        """終値 Series から単純移動平均 (SMA) をベクトル計算する。"""
        if close_series.empty:
            return []
        return close_series.rolling(window=period).mean().tolist()

    @staticmethod
    def _compute_rsi(close_series: pd.Series, period: int) -> List[float]:
        """終値 Series から相対力指数 (RSI) をベクトル計算する。"""
        if close_series.empty:
            return []
        delta = close_series.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(window=period, min_periods=1).mean()
        avg_loss = loss.rolling(window=period, min_periods=1).mean()

        rs = avg_gain / avg_loss.replace(0, 1e-9)  # 0除算対策
        rsi = 100 - (100 / (1 + rs))
        return rsi.tolist()

    @staticmethod
    def _compute_macd(
        close_series: pd.Series,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> List[Dict[str, float]]:
        """終値 Series から MACD (macd / signal / histogram) をベクトル計算する。"""
        if close_series.empty:
            return []
        ema_fast = close_series.ewm(span=fast_period, adjust=False).mean()
        ema_slow = close_series.ewm(span=slow_period, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=signal_period, adjust=False).mean()
        histogram = macd - signal

        return [
            {"macd": m, "signal": s, "histogram": h}
            for m, s, h in zip(macd.tolist(), signal.tolist(), histogram.tolist())
        ]

    @staticmethod
    def _compute_highest_high(high_series: pd.Series, period: int = 20) -> List[float]:
        """高値 Series から直近 period 営業日の最高値 (HIGHEST_HIGH) をベクトル計算する。"""
        if high_series.empty:
            return []
        return high_series.rolling(window=period, min_periods=1).max().tolist()

    @staticmethod
    def _compute_lowest_low(low_series: pd.Series, period: int = 20) -> List[float]:
        """安値 Series から直近 period 営業日の最安値 (LOWEST_LOW) をベクトル計算する。"""
        if low_series.empty:
            return []
        return low_series.rolling(window=period, min_periods=1).min().tolist()

    @staticmethod
    def _compute_atr(
        high_series: pd.Series,
        low_series: pd.Series,
        close_series: pd.Series,
        period: int = 14,
    ) -> List[float]:
        """高値・安値・終値 Series から True Range の単純移動平均 (ATR) をベクトル計算する。"""
        if close_series.empty:
            return []
        prev_close = close_series.shift(1)
        tr = pd.concat(
            [
                high_series - low_series,
                (high_series - prev_close).abs(),
                (low_series - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.rolling(window=period, min_periods=1).mean().tolist()

    @staticmethod
    def _compute_volume_ratio(
        volume_series: pd.Series, period: int = 20
    ) -> List[Optional[float]]:
        """出来高 Series から当日出来高 ÷ 直近 period 日平均出来高をベクトル計算する。"""
        if volume_series.empty:
            return []
        avg_volume = volume_series.rolling(window=period, min_periods=1).mean()
        ratios: List[Optional[float]] = []
        for vol, avg_vol in zip(volume_series.tolist(), avg_volume.tolist()):
            if math.isnan(vol) or math.isnan(avg_vol) or avg_vol == 0:
                ratios.append(None)
            else:
                ratios.append(float(vol / avg_vol))
        return ratios

    def calculate_sma(self, ohlcv_data: List[OhlcvModel], period: int) -> List[float]:
        """
        単純移動平均 (SMA) を計算する。
        """
        if not ohlcv_data:
            return []
        close_series = pd.Series([o.close for o in ohlcv_data], dtype="float64")
        return self._compute_sma(close_series, period)

    def calculate_rsi(self, ohlcv_data: List[OhlcvModel], period: int) -> List[float]:
        """
        相対力指数 (RSI) を計算する。
        """
        if not ohlcv_data:
            return []
        close_series = pd.Series([o.close for o in ohlcv_data], dtype="float64")
        return self._compute_rsi(close_series, period)

    def calculate_macd(
        self,
        ohlcv_data: List[OhlcvModel],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> List[Dict[str, float]]:
        """
        MACD (Moving Average Convergence Divergence) を計算する。
        """
        if not ohlcv_data:
            return []
        close_series = pd.Series([o.close for o in ohlcv_data], dtype="float64")
        return self._compute_macd(close_series, fast_period, slow_period, signal_period)

    def calculate_highest_high(
        self, ohlcv_data: List[OhlcvModel], period: int = 20
    ) -> List[float]:
        """
        当日を含む直近 period 営業日のレンジ最高値（HIGHEST_HIGH）を計算する。
        （※ ブレイクアウト判定用の前日以前高値は P002_BreakoutScore 側で別途算出される）
        """
        if not ohlcv_data:
            return []
        high_series = pd.Series([o.high for o in ohlcv_data], dtype="float64")
        return self._compute_highest_high(high_series, period)

    def calculate_lowest_low(
        self, ohlcv_data: List[OhlcvModel], period: int = 20
    ) -> List[float]:
        """
        当日を含む直近 period 営業日のレンジ最安値（LOWEST_LOW）を計算する。
        """
        if not ohlcv_data:
            return []
        low_series = pd.Series([o.low for o in ohlcv_data], dtype="float64")
        return self._compute_lowest_low(low_series, period)

    def calculate_atr(
        self, ohlcv_data: List[OhlcvModel], period: int = 14
    ) -> List[float]:
        """
        True Range の period 日単純移動平均（ATR）を計算する。
        """
        if not ohlcv_data:
            return []
        high_series = pd.Series([o.high for o in ohlcv_data], dtype="float64")
        low_series = pd.Series([o.low for o in ohlcv_data], dtype="float64")
        close_series = pd.Series([o.close for o in ohlcv_data], dtype="float64")
        return self._compute_atr(high_series, low_series, close_series, period)

    def calculate_volume_ratio(
        self, ohlcv_data: List[OhlcvModel], period: int = 20
    ) -> List[Optional[float]]:
        """
        当日出来高 ÷ 直近 period 日平均出来高を計算する（0除算時は None）。
        """
        if not ohlcv_data:
            return []
        volume_series = pd.Series([o.volume for o in ohlcv_data], dtype="float64")
        return self._compute_volume_ratio(volume_series, period)

    def calculate_indicators(
        self,
        ohlcv_data: List[OhlcvModel],
        use_cache: bool = True,
        cache_key_suffix: Optional[str] = None,
        write_cache: bool = True,
    ) -> List[IndicatorSetModel]:
        """
        OHLCVデータリストからテクニカル指標のセットを計算して返す（キャッシュ対応）。
        use_cache=False の場合はキャッシュの読み込み・保存をスキップする。
        write_cache=False の場合は既存キャッシュの読込のみ行い、新規キャッシュ保存を行わない。
        cache_key_suffix を指定した場合はサフィックス付きのキャッシュキーを使用する。
        """
        if not ohlcv_data:
            return []

        symbol = ohlcv_data[0].symbol
        cache_path = (
            f"cache/indicators_{symbol}_{cache_key_suffix}.json"
            if cache_key_suffix
            else f"cache/indicators_{symbol}.json"
        )
        expected_dates = [o.date.isoformat()[:10] for o in ohlcv_data]

        # キャッシュのチェック（空でないリスト・長さ一致・全日付列完全一致・最新要素に必須指標キーが含まれる場合のみ利用）
        required_cache_keys = (
            "LOWEST_LOW_20",
            "RSI5",
            "ATR5",
            "ATR20",
            "HIGHEST_HIGH_60",
            "HIGHEST_HIGH_250",
        )
        if use_cache:
            cached_data = self.storage.load_json(cache_path)
            if (
                cached_data is not None
                and isinstance(cached_data, list)
                and len(cached_data) > 0
                and len(cached_data) == len(ohlcv_data)
                and all(isinstance(item, dict) for item in cached_data)
                and [str(item.get("date", ""))[:10] for item in cached_data] == expected_dates
                and isinstance(cached_data[-1].get("indicators"), dict)
                and all(k in cached_data[-1].get("indicators", {}) for k in required_cache_keys)
            ):
                logger.debug(f"{symbol} のテクニカル指標をキャッシュからロードしました。")
                return [IndicatorSetModel(**item) for item in cached_data]

        # high, low, close, volume を1回だけ抽出し全指標を一括ベクトル計算する
        high_series = pd.Series([o.high for o in ohlcv_data], dtype="float64")
        low_series = pd.Series([o.low for o in ohlcv_data], dtype="float64")
        close_series = pd.Series([o.close for o in ohlcv_data], dtype="float64")
        volume_series = pd.Series([o.volume for o in ohlcv_data], dtype="float64")

        sma_5 = self._compute_sma(close_series, 5)
        sma_25 = self._compute_sma(close_series, 25)
        sma_75 = self._compute_sma(close_series, 75)
        sma_200 = self._compute_sma(close_series, 200)
        rsi_5 = self._compute_rsi(close_series, 5)
        rsi_14 = self._compute_rsi(close_series, 14)
        macd_data = self._compute_macd(close_series)
        highest_high_20 = self._compute_highest_high(high_series, 20)
        highest_high_60 = self._compute_highest_high(high_series, 60)
        highest_high_250 = self._compute_highest_high(high_series, 250)
        lowest_low_20 = self._compute_lowest_low(low_series, 20)
        atr_5 = self._compute_atr(high_series, low_series, close_series, 5)
        atr_14 = self._compute_atr(high_series, low_series, close_series, 14)
        atr_20 = self._compute_atr(high_series, low_series, close_series, 20)
        volume_ratio = self._compute_volume_ratio(volume_series, 20)

        indicator_sets: List[IndicatorSetModel] = []
        for (
            ohlcv,
            s5,
            s25,
            s75,
            s200,
            r5,
            r14,
            macd_item,
            hh20,
            hh60,
            hh250,
            ll20,
            a5,
            a14,
            a20,
            vr,
        ) in zip(
            ohlcv_data,
            sma_5,
            sma_25,
            sma_75,
            sma_200,
            rsi_5,
            rsi_14,
            macd_data,
            highest_high_20,
            highest_high_60,
            highest_high_250,
            lowest_low_20,
            atr_5,
            atr_14,
            atr_20,
            volume_ratio,
        ):
            indicators: Dict[str, object] = {}
            if not math.isnan(s5):
                indicators["SMA5"] = s5
            if not math.isnan(s25):
                indicators["SMA25"] = s25
            if not math.isnan(s75):
                indicators["SMA75"] = s75
            if not math.isnan(s200):
                indicators["SMA200"] = s200
            if not math.isnan(r5):
                indicators["RSI5"] = r5
            if not math.isnan(r14):
                indicators["RSI14"] = r14
            indicators["MACD"] = macd_item
            if not math.isnan(hh20):
                indicators["HIGHEST_HIGH_20"] = hh20
            if not math.isnan(hh60):
                indicators["HIGHEST_HIGH_60"] = hh60
            if not math.isnan(hh250):
                indicators["HIGHEST_HIGH_250"] = hh250
            if not math.isnan(ll20):
                indicators["LOWEST_LOW_20"] = ll20
            if not math.isnan(a5):
                indicators["ATR5"] = a5
            if not math.isnan(a14):
                indicators["ATR14"] = a14
            if not math.isnan(a20):
                indicators["ATR20"] = a20
            if vr is not None:
                indicators["VOLUME_RATIO"] = vr

            indicator_sets.append(
                IndicatorSetModel.model_construct(
                    symbol=ohlcv.symbol,
                    date=ohlcv.date,
                    indicators=indicators,
                )
            )
        
        # 結果をJSONキャッシュとして保存（write_cache=False 時は保存抑止）
        if use_cache and write_cache:
            try:
                self.storage.save_json([model.model_dump(mode="json") for model in indicator_sets], cache_path)
            except Exception as e:
                logger.warning(f"指標キャッシュの保存に失敗しました: {e}")

            logger.debug(f"{symbol} のテクニカル指標を計算・キャッシュしました。")
        else:
            logger.debug(f"{symbol} のテクニカル指標を計算しました（キャッシュ保存なし）。")
        return indicator_sets

# モジュールレベルでインスタンス化
indicator_calculator = IndicatorCalculator()

def calculate_indicators(
    ohlcv_data: List[OhlcvModel],
    use_cache: bool = True,
    cache_key_suffix: Optional[str] = None,
    write_cache: bool = True,
) -> List[IndicatorSetModel]:
    return indicator_calculator.calculate_indicators(
        ohlcv_data,
        use_cache=use_cache,
        cache_key_suffix=cache_key_suffix,
        write_cache=write_cache,
    )
