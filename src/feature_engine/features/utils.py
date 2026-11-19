import math


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
