
from abc import ABC, abstractmethod
from typing import List, Dict, Any

from src.model.data_models import FeatureSetModel, PatternSetModel, ScoreResultModel

class IScoreCalculator(ABC):
    """
    スコア計算インターフェース
    """
    @property
    @abstractmethod
    def score_id(self) -> str:
        pass

    @property
    @abstractmethod
    def score_name(self) -> str:
        pass

    @property
    @abstractmethod
    def score_category(self) -> str:
        pass

    @abstractmethod
    def calculate(
        self,
        feature_sets: List[FeatureSetModel],
        pattern_sets: List[PatternSetModel]
    ) -> List[ScoreResultModel]:
        """
        特徴量セットとパターンセットから評価スコアを計算し、結果のリストを返す。
        """
        pass

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        """
        計算されたスコアを生スコアから0-100の範囲に正規化する。
        """
        if max_val == min_val:
            return 50.0 # ゼロ除算を避ける
        return max(0.0, min(100.0, ((raw_value - min_val) / (max_val - min_val)) * 100.0))
