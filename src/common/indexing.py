"""
インデックス解決共通ユーティリティ
"""

import inspect
from typing import Any, List, Optional, Sequence, Set, Tuple


def supports_target_indices(func: Any) -> bool:
    """対象関数がキーワード引数 target_indices または **kwargs を受け取れるか判定する。"""
    try:
        params = inspect.signature(func).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        (p.name == "target_indices" and p.kind != inspect.Parameter.POSITIONAL_ONLY)
        or p.kind == inspect.Parameter.VAR_KEYWORD
        for p in params
    )


def resolve_target_indices(
    length: int,
    target_indices: Optional[Sequence[int]] = None,
) -> List[int]:
    """
    系列長 length に対する評価対象インデックス列を解決する。

    - target_indices が None の場合は全範囲 [0, ..., length - 1] を返す。
    - 負インデックスは length を加算して正規化する。
    - 範囲外（0 未満または length 以上）および bool 値は除外する。
    - 重複は元の出現順序を保持したまま排除する。
    """
    if length <= 0:
        return []
    if target_indices is None:
        return list(range(length))

    resolved: List[int] = []
    seen = set()
    for raw_idx in target_indices:
        if isinstance(raw_idx, bool):
            continue
        idx = int(raw_idx)
        if idx < 0:
            idx += length
        if 0 <= idx < length and idx not in seen:
            seen.add(idx)
            resolved.append(idx)
    return resolved


def resolve_evaluation_targets(
    items: Sequence[Any],
    latest_only: bool = False,
    target_indices: Optional[Sequence[int]] = None,
) -> Tuple[Optional[List[int]], Optional[Set[Any]]]:
    """
    latest_only / target_indices 指定から評価対象インデックス列と日付集合を解決する。

    - 全件評価時（latest_only=False かつ target_indices is None）は (None, None) を返す。
    - 部分評価時は (対象インデックスのリスト, 対象要素の .date 集合) を返す。
    """
    if target_indices is not None:
        resolved_targets = resolve_target_indices(len(items), target_indices)
    elif latest_only:
        resolved_targets = [len(items) - 1] if len(items) > 0 else []
    else:
        return None, None

    target_dates = {items[idx].date for idx in resolved_targets}
    return resolved_targets, target_dates
