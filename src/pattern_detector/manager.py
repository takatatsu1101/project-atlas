
from typing import List, Optional, Dict
from datetime import date

from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternSetModel, PatternResultModel
from src.pattern_detector.registry import pattern_registry
from src.pattern_detector.interfaces import IPattern

class PatternManager:
    def __init__(self):
        self.registry = pattern_registry

    def detect_patterns(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        pattern_ids: Optional[List[str]] = None
    ) -> List[PatternSetModel]:
        """
        指定された入力データに基づいてチャートパターンを検出し、結果のリストを返す。
        pattern_idsが指定された場合は、そのパターンのみを検出する。
        """
        if not ohlcv_data:
            print("警告: OHLCVデータが不足しているため、パターンを検出できません。")
            return []

        all_pattern_sets: Dict[date, List[PatternResultModel]] = {}

        patterns_to_detect: List[IPattern] = []
        if pattern_ids:
            for p_id in pattern_ids:
                patterns_to_detect.append(self.registry.get_pattern(p_id))
        else:
            # 全てのパターンを取得 (registry.pyのlist_patternsをIPatternインスタンスで返すように修正が必要かも)
            # 登録されている全てのパターンを取得して追加
            for pattern_info in self.registry.list_patterns():
                patterns_to_detect.append(self.registry.get_pattern(pattern_info["pattern_id"]))

        for pattern_instance in patterns_to_detect:
            print(f"パターン {pattern_instance.pattern_name} を検出中...")
            pattern_results = pattern_instance.detect(ohlcv_data, indicator_data)
            for result in pattern_results:
                if result.metadata and "date" in result.metadata:
                    result_date = result.metadata["date"]
                    if result_date not in all_pattern_sets:
                        all_pattern_sets[result_date] = []
                    all_pattern_sets[result_date].append(result)
                else:
                    print(f"警告: パターン検出結果 {pattern_instance.pattern_id} に日付情報がありません。スキップします。")
        
        final_pattern_sets: List[PatternSetModel] = []
        if ohlcv_data:
            symbol = ohlcv_data[0].symbol
            for date_key in sorted(all_pattern_sets.keys()):
                final_pattern_sets.append(PatternSetModel(
                    symbol=symbol,
                    date=date_key,
                    results=all_pattern_sets[date_key]
                ))

        print(f"{ohlcv_data[0].symbol} のパターン検出が完了しました。")
        return final_pattern_sets

# モジュールレベルでインスタンス化
pattern_manager = PatternManager()

def detect_patterns(
    ohlcv_data: List[OhlcvModel],
    indicator_data: List[IndicatorSetModel],
    pattern_ids: Optional[List[str]] = None
) -> List[PatternSetModel]:
    return pattern_manager.detect_patterns(ohlcv_data, indicator_data, pattern_ids)
