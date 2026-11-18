from contextlib import contextmanager
import logging
import sys
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

_PROJECT_LOGGER_PREFIXES: Tuple[str, ...] = ("src.",)
_LEGACY_PROJECT_LOGGER_NAMES: Tuple[str, ...] = (
    "DataCollector",
    "IndicatorCalculator",
    "FeatureManager",
)
_REGISTERED_LOGGER_NAMES: Set[str] = set(_LEGACY_PROJECT_LOGGER_NAMES)
_ACTIVE_LOG_LEVEL: Optional[int] = None


def get_logger(name: str) -> logging.Logger:
    """
    プロジェクト共通のロガーを取得する。
    """
    _REGISTERED_LOGGER_NAMES.add(name)
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(_ACTIVE_LOG_LEVEL if _ACTIVE_LOG_LEVEL is not None else logging.INFO)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    elif _ACTIVE_LOG_LEVEL is not None:
        logger.setLevel(_ACTIVE_LOG_LEVEL)
    return logger


def _iter_project_loggers() -> List[logging.Logger]:
    """プロジェクト配下および登録済みの全ロガーインスタンスを収集する。"""
    target_names = set(_REGISTERED_LOGGER_NAMES)
    for name, obj in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(obj, logging.Logger) and name.startswith(_PROJECT_LOGGER_PREFIXES):
            target_names.add(name)
    return [logging.getLogger(name) for name in sorted(target_names)]


def set_project_log_level(level: int) -> Dict[str, Any]:
    """
    プロジェクト系ロガーおよび配下ハンドラのログレベルを一括変更し、
    復元用のスナップショットを返す。
    """
    global _ACTIVE_LOG_LEVEL
    prev_active = _ACTIVE_LOG_LEVEL
    _ACTIVE_LOG_LEVEL = level

    logger_states: Dict[str, Tuple[int, List[Tuple[logging.Handler, int]]]] = {}
    for proj_logger in _iter_project_loggers():
        handler_levels = [(h, h.level) for h in proj_logger.handlers]
        logger_states[proj_logger.name] = (proj_logger.level, handler_levels)
        proj_logger.setLevel(level)
        for handler, orig_h_level in handler_levels:
            if orig_h_level != logging.NOTSET and orig_h_level > level:
                handler.setLevel(level)

    return {"active_level": prev_active, "logger_states": logger_states}


def restore_project_log_levels(snapshot: Dict[str, Any]) -> None:
    """set_project_log_level で保存したスナップショットからログレベルを復元する。"""
    global _ACTIVE_LOG_LEVEL
    _ACTIVE_LOG_LEVEL = snapshot.get("active_level")

    logger_states: Dict[str, Tuple[int, List[Tuple[logging.Handler, int]]]] = snapshot.get(
        "logger_states", {}
    )
    for name, (orig_level, handler_levels) in logger_states.items():
        proj_logger = logging.getLogger(name)
        proj_logger.setLevel(orig_level)
        for handler, orig_h_level in handler_levels:
            handler.setLevel(orig_h_level)

    # ブロック内で新規生成・昇格されたプロジェクトロガーも復元先レベルへ戻す
    fallback_level = _ACTIVE_LOG_LEVEL if _ACTIVE_LOG_LEVEL is not None else logging.INFO
    for proj_logger in _iter_project_loggers():
        if proj_logger.name not in logger_states:
            proj_logger.setLevel(fallback_level)


@contextmanager
def project_log_level(level: int) -> Iterator[None]:
    """with ブロック中のみプロジェクト系ロガーのレベルを切り替え、終了時に必ず復元する。"""
    snapshot = set_project_log_level(level)
    try:
        yield
    finally:
        restore_project_log_levels(snapshot)
