
from typing import List, Dict, Any, Tuple
import numpy as np

from src.score_engine.interfaces import IScoreCalculator
from src.model.data_models import FeatureSetModel, PatternSetModel, ScoreResultModel, FeatureResultModel, PatternResultModel
from src.score_engine.registry import score_registry

class OverallScoreCalculator(IScoreCalculator):
    score_id: str = "S001_OverallScore"
    score_name: str = "総合スコア"
    score_category: str = "Overall"

    def calculate(
        self,
        feature_sets: List[FeatureSetModel],
        pattern_sets: List[PatternSetModel]
    ) -> List[ScoreResultModel]:
        
        # 日付ごとのスコアを集約するための辞書
        daily_scores: Dict[Tuple[str, Any], List[float]] = {}
        daily_feature_results: Dict[Tuple[str, Any], List[FeatureResultModel]] = {}
        daily_pattern_results: Dict[Tuple[str, Any], List[PatternResultModel]] = {}

        # FeatureSetModelからスコアを抽出
        for fs in feature_sets:
            key = (fs.symbol, fs.date)
            if key not in daily_scores:
                daily_scores[key] = []
                daily_feature_results[key] = []
            for fr in fs.results:
                daily_scores[key].append(fr.score)
                daily_feature_results[key].append(fr)

        # PatternSetModelから信頼度をスコアとして抽出
        for ps in pattern_sets:
            key = (ps.symbol, ps.date)
            # ここでfeature_setsとpattern_setsが同じ日付のエントリを持つことを保証する必要がある
            # あるいは、どちらか一方にしか存在しない日付のエントリも初期化しておく
            if key not in daily_scores:
                daily_scores[key] = []
            if key not in daily_feature_results:
                daily_feature_results[key] = []
            if key not in daily_pattern_results:
                daily_pattern_results[key] = []

            for pr in ps.results:
                # パターン検出の信頼度をスコアとして扱う
                daily_scores[key].append(pr.confidence)
                daily_pattern_results[key].append(pr)

        score_results: List[ScoreResultModel] = []
        for (symbol, date_key), scores in daily_scores.items():
            if not scores:
                continue
            
            # ここでは単純に平均を総合スコアとする
            # 実際には重み付けや複雑なロジックを適用する
            total_raw_score = float(np.mean(scores))
            total_normalized_score = self._normalize_score(total_raw_score, 0, 100) # 既に0-100なのでそのまま

            # サブスコアはここでは仮にFeatureとPatternそれぞれの平均とする
            sub_scores = {
                "FeatureAverageScore": float(np.mean([fr.score for fr in daily_feature_results.get((symbol, date_key), [])])) if daily_feature_results.get((symbol, date_key)) else 0.0,
                "PatternAverageConfidence": float(np.mean([pr.confidence for pr in daily_pattern_results.get((symbol, date_key), [])])) if daily_pattern_results.get((symbol, date_key)) else 0.0,
            }

            score_results.append(ScoreResultModel(
                symbol=symbol,
                date=date_key,
                sub_scores=sub_scores,
                total_score=total_normalized_score,
                metadata={
                    "feature_results_count": len(daily_feature_results.get((symbol, date_key), [])),
                    "pattern_results_count": len(daily_pattern_results.get((symbol, date_key), [])),
                }
            ))
        
        print(f"総合スコア計算が完了しました。{len(score_results)} 件のスコア結果を生成しました。")
        return score_results

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        """
        0-100の範囲でスコアを正規化する。
        """
        if max_val == min_val:
            return 50.0 # ゼロ除算を避ける
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))

# レジストリにスコア計算クラスを登録
score_registry.register(OverallScoreCalculator)
