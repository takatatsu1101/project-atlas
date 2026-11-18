
from typing import List, Optional, Dict, Sequence
from datetime import date

from src.common.indexing import resolve_evaluation_targets, supports_target_indices
from src.common.logger import get_logger
from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternSetModel, PatternResultModel
from src.pattern_detector.registry import pattern_registry
from src.pattern_detector.interfaces import IPattern

logger = get_logger(__name__)


class PatternManager:
    def __init__(self):
        self.registry = pattern_registry

    def detect_patterns(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        pattern_ids: Optional[List[str]] = None,
        latest_only: bool = False,
        target_indices: Optional[Sequence[int]] = None,
    ) -> List[PatternSetModel]:
        """
        指定された入力データに基づいてチャートパターンを検出し、結果のリストを返す。
        pattern_idsが指定された場合は、そのパターンのみを検出する。
        latest_only=True または target_indices 指定時は全履歴を参照しつつ対象日のみ評価する。
        """
        eval_len = min(len(ohlcv_data), len(indicator_data)) if indicator_data else len(ohlcv_data)
        if eval_len == 0:
            logger.warning("OHLCVデータが不足しているため、パターンを検出できません。")
            return []

        ohlcv_eval = ohlcv_data[:eval_len]
        ind_eval = indicator_data[:eval_len] if indicator_data else []

        resolved_targets, target_dates = resolve_evaluation_targets(
            ohlcv_eval, latest_only=latest_only, target_indices=target_indices
        )
        if resolved_targets is not None and not resolved_targets:
            return []

        all_pattern_sets: Dict[date, List[PatternResultModel]] = {}

        patterns_to_detect: List[IPattern] = []
        if pattern_ids:
            for p_id in pattern_ids:
                patterns_to_detect.append(self.registry.get_pattern(p_id))
        else:
            # 登録されている全てのパターンを取得して追加
            for pattern_info in self.registry.list_patterns():
                patterns_to_detect.append(self.registry.get_pattern(pattern_info["pattern_id"]))

        for pattern_instance in patterns_to_detect:
            logger.debug(f"パターン {pattern_instance.pattern_name} を検出中...")
            if resolved_targets is not None and supports_target_indices(pattern_instance.detect):
                pattern_results = pattern_instance.detect(
                    ohlcv_eval, ind_eval, target_indices=resolved_targets
                )
            else:
                pattern_results = pattern_instance.detect(ohlcv_eval, ind_eval)
            for result in pattern_results:
                if result.metadata and "date" in result.metadata:
                    result_date = result.metadata["date"]
                    if target_dates is not None and result_date not in target_dates:
                        continue
                    if result_date not in all_pattern_sets:
                        all_pattern_sets[result_date] = []
                    all_pattern_sets[result_date].append(result)
                else:
                    logger.warning(f"パターン検出結果 {pattern_instance.pattern_id} に日付情報がありません。スキップします。")
        
        final_pattern_sets: List[PatternSetModel] = []
        if ohlcv_data:
            symbol = ohlcv_data[0].symbol
            for date_key in sorted(all_pattern_sets.keys()):
                final_pattern_sets.append(PatternSetModel(
                    symbol=symbol,
                    date=date_key,
                    results=all_pattern_sets[date_key]
                ))

        logger.debug(f"{ohlcv_data[0].symbol} のパターン検出が完了しました。")
        return final_pattern_sets

# モジュールレベルでインスタンス化
pattern_manager = PatternManager()

def detect_patterns(
    ohlcv_data: List[OhlcvModel],
    indicator_data: List[IndicatorSetModel],
    pattern_ids: Optional[List[str]] = None,
    latest_only: bool = False,
    target_indices: Optional[Sequence[int]] = None,
) -> List[PatternSetModel]:
    return pattern_manager.detect_patterns(
        ohlcv_data,
        indicator_data,
        pattern_ids,
        latest_only=latest_only,
        target_indices=target_indices,
    )
