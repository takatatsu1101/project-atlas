import math
from typing import Any, Optional


def linear_scale(
    value: float,
    in_min: float,
    in_max: float,
    out_min: float,
    out_max: float,
) -> float:
    """値を [in_min, in_max] から [out_min, out_max] へ線形マッピングしクリップする。"""
    if not math.isfinite(value) or in_max == in_min:
        return (out_min + out_max) / 2.0
    ratio = max(0.0, min(1.0, (value - in_min) / (in_max - in_min)))
    return out_min + ratio * (out_max - out_min)


def to_finite_float(value: Any) -> Optional[float]:
    """None・bool・非数値・NaN/inf を除外し、有限な float のみ返す。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def to_finite_int(value: Any) -> Optional[int]:
    """None・bool・非数値・NaN/inf を除外し、有限な int のみ返す。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    num = to_finite_float(value)
    if num is None:
        return None
    return int(num)


def normalize_score_range(raw_value: float, min_val: float, max_val: float) -> float:
    """生スコアを [0.0, 100.0] に正規化し、非有限値には中立 50.0 を返す。"""
    if not math.isfinite(raw_value) or max_val == min_val:
        return 50.0
    return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))
