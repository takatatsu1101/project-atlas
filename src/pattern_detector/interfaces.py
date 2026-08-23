
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import date

from src.model.data_models import OhlcvModel, IndicatorSetModel, PatternResultModel

class IPattern(ABC):
    """
    チャートパターン検出インターフェース
    """
    @property
    @abstractmethod
    def pattern_id(self) -> str:
        pass

    @property
    @abstractmethod
    def pattern_name(self) -> str:
        pass

    @property
    @abstractmethod
    def pattern_category(self) -> str:
        pass

    @abstractmethod
    def detect(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel]
    ) -> List[PatternResultModel]:
        """
        チャートパターンを検出し、PatternResultModelのリストを返す。
        """
        pass

    @abstractmethod
    def _calculate_confidence(self, detected_pattern_properties: Dict[str, Any]) -> float:
        """
        検出されたパターンの信頼度を計算する（0-100）。
        """
        pass
