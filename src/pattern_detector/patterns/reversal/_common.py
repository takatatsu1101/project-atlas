"""
リバーサルパターン（ダブルボトム／ダブルトップ）共通の O(N) 走査ヘルパー
"""

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Sequence, Tuple

from src.common.indexing import resolve_target_indices
from src.model.data_models import OhlcvModel


@dataclass(frozen=True)
class DoubleReversalCandidate:
    """単一日 i におけるダブルボトム／ダブルトップの候補情報"""

    index: int
    e1_idx: int
    e2_idx: int
    neck_idx: int
    e1_val: float
    e2_val: float
    neck_val: float
    close: float


def find_double_reversal_candidates(
    ohlcv_data: List[OhlcvModel],
    mode: Literal["bottom", "top"],
    target_indices: Optional[Sequence[int]] = None,
    min_length: int = 15,
    start_index: int = 10,
    max_price_diff_rate: float = 0.025,
) -> List[DoubleReversalCandidate]:
    """
    1パス増分極値更新とペア変化時のみのネックライン探索キャッシュにより、
    全体 O(N) でダブルボトム（mode='bottom'）またはダブルトップ（mode='top'）の候補を抽出する。

    先読みバイアスを防ぐため、各日 i では従来どおり j in range(2, i - 2) の極値のみを参照する。
    """
    n = len(ohlcv_data)
    if n < min_length:
        return []

    resolved_targets = resolve_target_indices(n, target_indices)
    eval_targets = [idx for idx in resolved_targets if idx >= start_index]
    if not eval_targets:
        return []

    target_set = set(eval_targets)
    max_target = max(eval_targets)

    lows = [b.low for b in ohlcv_data]
    highs = [b.high for b in ohlcv_data]
    closes = [b.close for b in ohlcv_data]

    is_bottom = mode == "bottom"
    extrema_src = lows if is_bottom else highs
    neck_src = highs if is_bottom else lows

    extrema: List[int] = []
    next_j = 2
    cached_pair: Optional[Tuple[int, int]] = None
    cached_neck: Tuple[int, float] = (-1, 0.0)
    candidates_by_idx: Dict[int, DoubleReversalCandidate] = {}

    for i in range(start_index, max_target + 1):
        # 日 i で新たに極値候補に加わる j (< i - 2) を増分判定する
        limit_j = i - 2
        while next_j < limit_j:
            val = extrema_src[next_j]
            if is_bottom:
                is_extremum = (
                    val < extrema_src[next_j - 1]
                    and val < extrema_src[next_j - 2]
                    and val < extrema_src[next_j + 1]
                    and val < extrema_src[next_j + 2]
                )
            else:
                is_extremum = (
                    val > extrema_src[next_j - 1]
                    and val > extrema_src[next_j - 2]
                    and val > extrema_src[next_j + 1]
                    and val > extrema_src[next_j + 2]
                )
            if is_extremum:
                extrema.append(next_j)
            next_j += 1

        if i not in target_set or len(extrema) < 2:
            continue

        e1_idx = extrema[-2]
        e2_idx = extrema[-1]
        e1_val = extrema_src[e1_idx]
        e2_val = extrema_src[e2_idx]

        if e1_val == 0:
            continue
        price_diff_rate = abs(e1_val - e2_val) / e1_val
        if price_diff_rate > max_price_diff_rate:
            continue

        pair = (e1_idx, e2_idx)
        if cached_pair != pair:
            neck_idx = e1_idx + 1
            neck_val = neck_src[neck_idx]
            for k in range(e1_idx + 1, e2_idx):
                v = neck_src[k]
                if (is_bottom and v > neck_val) or (not is_bottom and v < neck_val):
                    neck_idx = k
                    neck_val = v
            cached_pair = pair
            cached_neck = (neck_idx, neck_val)
        else:
            neck_idx, neck_val = cached_neck

        current_close = closes[i]
        if is_bottom and current_close < min(e1_val, e2_val):
            continue
        if not is_bottom and current_close > max(e1_val, e2_val):
            continue

        candidates_by_idx[i] = DoubleReversalCandidate(
            index=i,
            e1_idx=e1_idx,
            e2_idx=e2_idx,
            neck_idx=neck_idx,
            e1_val=e1_val,
            e2_val=e2_val,
            neck_val=neck_val,
            close=current_close,
        )

    return [candidates_by_idx[i] for i in eval_targets if i in candidates_by_idx]
