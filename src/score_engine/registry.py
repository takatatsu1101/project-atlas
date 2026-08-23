
from typing import Dict, Type, List
from src.score_engine.interfaces import IScoreCalculator

class ScoreRegistry:
    def __init__(self):
        self._scores: Dict[str, Type[IScoreCalculator]] = {}

    def register(self, score_class: Type[IScoreCalculator]):
        """
        IScoreCalculatorを実装するスコア計算クラスを登録する。
        """
        if not issubclass(score_class, IScoreCalculator):
            raise ValueError("登録できるのはIScoreCalculatorを実装したクラスのみです。")
        self._scores[score_class.score_id] = score_class
        print(f"Score \'{score_class.score_name}\' ({score_class.score_id}) を登録しました。")

    def get_score_calculator(self, score_id: str) -> IScoreCalculator:
        """
        指定されたIDのスコア計算インスタンスを返す。
        """
        score_class = self._scores.get(score_id)
        if not score_class:
            raise ValueError(f"Score ID \'{score_id}\' が見つかりません。")
        return score_class() # インスタンスを生成して返す

    def list_score_calculators(self) -> List[Dict[str, str]]:
        """
        登録されている全てのスコア計算機のリストを返す。
        """
        return [{
            "score_id": s_id,
            "score_name": s_class.score_name,
            "score_category": s_class.score_category
        } for s_id, s_class in self._scores.items()]

# シングルトンインスタンス
score_registry = ScoreRegistry()
