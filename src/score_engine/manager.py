
from typing import List, Optional

from src.model.data_models import FeatureSetModel, PatternSetModel, ScoreResultModel
from src.score_engine.registry import score_registry
from src.score_engine.interfaces import IScoreCalculator

class ScoreManager:
    def __init__(self):
        self.registry = score_registry

    def calculate_scores(
        self,
        feature_sets: List[FeatureSetModel],
        pattern_sets: List[PatternSetModel],
        score_ids: Optional[List[str]] = None
    ) -> List[ScoreResultModel]:
        """
        特徴量セットとパターンセットから評価スコアを計算し、結果のリストを返す。
        score_idsが指定された場合は、そのスコアのみを計算する。
        """
        if not feature_sets and not pattern_sets:
            print("警告: 特徴量データまたはパターンデータが不足しているため、スコアを計算できません。")
            return []

        scores_to_calculate: List[IScoreCalculator] = []
        if score_ids:
            for s_id in score_ids:
                scores_to_calculate.append(self.registry.get_score_calculator(s_id))
        else:
            # 全てのスコア計算機を取得
            # 登録されている全てのスコア計算機を取得して追加
            for score_info in self.registry.list_score_calculators():
                scores_to_calculate.append(self.registry.get_score_calculator(score_info["score_id"]))

        all_score_results: List[ScoreResultModel] = []
        for score_calculator_instance in scores_to_calculate:
            print(f"スコア {score_calculator_instance.score_name} を計算中...")
            results = score_calculator_instance.calculate(feature_sets, pattern_sets)
            all_score_results.extend(results)

        print(f"{feature_sets[0].symbol if feature_sets else pattern_sets[0].symbol} のスコア計算が完了しました。")
        return all_score_results

# モジュールレベルでインスタンス化
score_manager = ScoreManager()

def calculate_scores(
    feature_sets: List[FeatureSetModel],
    pattern_sets: List[PatternSetModel],
    score_ids: Optional[List[str]] = None
) -> List[ScoreResultModel]:
    return score_manager.calculate_scores(feature_sets, pattern_sets, score_ids)
