import inspect
from typing import Any, Dict, List, Optional

from src.common.logger import get_logger
from src.model.data_models import (
    FeatureSetModel,
    IndicatorSetModel,
    MarketContextModel,
    OhlcvModel,
    PatternSetModel,
    ScoreResultModel,
)
from src.score_engine.registry import score_registry
from src.score_engine.interfaces import IScoreCalculator

logger = get_logger(__name__)


class ScoreManager:
    def __init__(self):
        self.registry = score_registry

    def calculate_scores(
        self,
        feature_sets: List[FeatureSetModel],
        pattern_sets: List[PatternSetModel],
        score_ids: Optional[List[str]] = None,
        ohlcv_data: Optional[List[OhlcvModel]] = None,
        indicator_sets: Optional[List[IndicatorSetModel]] = None,
        score_configs: Optional[Dict[str, Any]] = None,
        market_context: Optional[MarketContextModel] = None,
    ) -> List[ScoreResultModel]:
        """
        特徴量セットとパターンセットから評価スコアを計算し、結果のリストを返す。
        score_idsが指定された場合は、そのスコアのみを計算する。
        ohlcv_data / indicator_sets / market_context は計算機が受け取れる場合のみ渡す。
        score_configs が指定された場合は score_id ごとの設定オブジェクトを注入する。
        """
        if not feature_sets and not pattern_sets:
            logger.warning("特徴量データまたはパターンデータが不足しているため、スコアを計算できません。")
            return []

        config_map = score_configs or {}
        scores_to_calculate: List[IScoreCalculator] = []
        if score_ids:
            for s_id in score_ids:
                scores_to_calculate.append(
                    self.registry.get_score_calculator(s_id, config=config_map.get(s_id))
                )
        else:
            # 登録されている全てのスコア計算機を取得して追加
            for score_info in self.registry.list_score_calculators():
                s_id = score_info["score_id"]
                scores_to_calculate.append(
                    self.registry.get_score_calculator(s_id, config=config_map.get(s_id))
                )

        all_score_results: List[ScoreResultModel] = []
        for score_calculator_instance in scores_to_calculate:
            logger.debug(f"スコア {score_calculator_instance.score_name} を計算中...")
            results = self._invoke_calculator(
                score_calculator_instance,
                feature_sets,
                pattern_sets,
                ohlcv_data=ohlcv_data,
                indicator_sets=indicator_sets,
                market_context=market_context,
            )
            all_score_results.extend(results)

        logger.debug(f"{feature_sets[0].symbol if feature_sets else pattern_sets[0].symbol} のスコア計算が完了しました。")
        return all_score_results

    @staticmethod
    def _invoke_calculator(
        calculator: IScoreCalculator,
        feature_sets: List[FeatureSetModel],
        pattern_sets: List[PatternSetModel],
        ohlcv_data: Optional[List[OhlcvModel]] = None,
        indicator_sets: Optional[List[IndicatorSetModel]] = None,
        market_context: Optional[MarketContextModel] = None,
    ) -> List[ScoreResultModel]:
        """計算機の calculate シグネチャを確認し、対応する引数のみを渡して呼び出す。"""
        sig = inspect.signature(calculator.calculate)
        params = sig.parameters
        accepts_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
        kwargs: Dict[str, Any] = {}
        if accepts_kwargs or "ohlcv_data" in params:
            kwargs["ohlcv_data"] = ohlcv_data
        if accepts_kwargs or "indicator_sets" in params:
            kwargs["indicator_sets"] = indicator_sets
        if accepts_kwargs or "market_context" in params:
            kwargs["market_context"] = market_context
        return calculator.calculate(feature_sets, pattern_sets, **kwargs)


# モジュールレベルでインスタンス化
score_manager = ScoreManager()


def calculate_scores(
    feature_sets: List[FeatureSetModel],
    pattern_sets: List[PatternSetModel],
    score_ids: Optional[List[str]] = None,
    ohlcv_data: Optional[List[OhlcvModel]] = None,
    indicator_sets: Optional[List[IndicatorSetModel]] = None,
    score_configs: Optional[Dict[str, Any]] = None,
    market_context: Optional[MarketContextModel] = None,
) -> List[ScoreResultModel]:
    return score_manager.calculate_scores(
        feature_sets,
        pattern_sets,
        score_ids,
        ohlcv_data=ohlcv_data,
        indicator_sets=indicator_sets,
        score_configs=score_configs,
        market_context=market_context,
    )
