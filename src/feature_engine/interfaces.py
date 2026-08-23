
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import date

from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureResultModel

class IFeature(ABC):
    """
    特徴量計算インターフェース
    """
    @property
    @abstractmethod
    def feature_id(self) -> str:
        pass

    @property
    @abstractmethod
    def feature_name(self) -> str:
        pass

    @property
    @abstractmethod
    def feature_category(self) -> str:
        pass

    @abstractmethod
    def calculate(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        financial_data: Optional[FinancialModel] = None
    ) -> List[FeatureResultModel]:
        """
        特徴量を計算し、FeatureResultModelのリストを返す。
        """
        pass

    @abstractmethod
    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        """
        計算された特徴量を生スコアから0-100の範囲に正規化する。
        """
        pass

