from typing import Dict, List, Optional, Tuple

from src.model.data_models import OhlcvModel


def compute_candle_metrics(
    ohlcv_data: List[OhlcvModel],
    idx: int,
) -> Dict[str, Optional[float]]:
    """
    指定インデックス日のローソク足プライスアクション指標を算出する。
    ohlcv_data の範囲外の場合は None を返す。
    """
    if idx < 0 or idx >= len(ohlcv_data):
        return {
            "clv": None,
            "upper_wick_ratio": None,
            "lower_wick_ratio": None,
            "gap_pct": None,
            "is_bullish": None,
            "is_bearish": None,
        }

    bar = ohlcv_data[idx]
    high = bar.high
    low = bar.low
    open_p = bar.open
    close_p = bar.close
    price_range = high - low

    if price_range <= 0:
        clv = 0.5
        upper_wick_ratio = 0.0
        lower_wick_ratio = 0.0
    else:
        clv = max(0.0, min(1.0, (close_p - low) / price_range))
        upper_wick_ratio = max(0.0, min(1.0, (high - max(open_p, close_p)) / price_range))
        lower_wick_ratio = max(0.0, min(1.0, (min(open_p, close_p) - low) / price_range))

    gap_pct: Optional[float] = None
    if idx >= 1 and idx - 1 < len(ohlcv_data):
        prev_close = ohlcv_data[idx - 1].close
        if prev_close is not None and prev_close > 0:
            gap_pct = (open_p - prev_close) / prev_close

    return {
        "clv": clv,
        "upper_wick_ratio": upper_wick_ratio,
        "lower_wick_ratio": lower_wick_ratio,
        "gap_pct": gap_pct,
        "is_bullish": bool(close_p > open_p),
        "is_bearish": bool(close_p < open_p),
    }


def compute_past_highest_high(
    ohlcv_data: List[OhlcvModel],
    idx: int,
    max_past_days: int,
    min_past_days: int = 5,
) -> Tuple[Optional[float], int]:
    """
    当日 idx を除外した過去 max_past_days 日間の最高値と参照日数を算出する。
    """
    if idx < min_past_days:
        return None, idx
    past_start_idx = max(0, idx - max_past_days)
    past_end_idx = min(idx, len(ohlcv_data))
    past_days_calculated = max(0, past_end_idx - past_start_idx)
    if past_start_idx >= past_end_idx:
        return None, past_days_calculated
    past_highs = [ohlcv_data[j].high for j in range(past_start_idx, past_end_idx)]
    return (max(past_highs) if past_highs else None), past_days_calculated
