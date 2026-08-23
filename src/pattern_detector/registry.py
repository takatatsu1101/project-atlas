
from typing import Dict, Type, List
from src.pattern_detector.interfaces import IPattern

class PatternRegistry:
    def __init__(self):
        self._patterns: Dict[str, Type[IPattern]] = {}

    def register(self, pattern_class: Type[IPattern]):
        """
        IPatternを実装するパターンクラスを登録する。
        """
        if not issubclass(pattern_class, IPattern):
            raise ValueError("登録できるのはIPatternを実装したクラスのみです。")
        self._patterns[pattern_class.pattern_id] = pattern_class
        print(f"Pattern \'{pattern_class.pattern_name}\' ({pattern_class.pattern_id}) を登録しました。")

    def get_pattern(self, pattern_id: str) -> IPattern:
        """
        指定されたIDのパターンインスタンスを返す。
        """
        pattern_class = self._patterns.get(pattern_id)
        if not pattern_class:
            raise ValueError(f"Pattern ID \'{pattern_id}\' が見つかりません。")
        return pattern_class() # インスタンスを生成して返す

    def list_patterns(self) -> List[Dict[str, str]]:
        """
        登録されている全てのパターンのリストを返す。
        """
        return [{
            "pattern_id": p_id,
            "pattern_name": p_class.pattern_name,
            "pattern_category": p_class.pattern_category
        } for p_id, p_class in self._patterns.items()]

# シングルトンインスタンス
pattern_registry = PatternRegistry()
