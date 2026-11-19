from datetime import date, datetime
import math
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from src.common.logger import get_logger
from src.model.data_models import MarketContextModel, ScoreResultModel

logger = get_logger(__name__)


class ScreeningCriteria(BaseModel):
    """スクリーニング抽出条件モデル"""

    min_total_score: float = 60.0
    min_trend_env_score: Optional[float] = 50.0
    require_gate1_passed: bool = True
    exclude_watch: bool = True
    allowed_strategies: Optional[List[str]] = Field(
        default_factory=lambda: ["pullback", "breakout"]
    )
    min_pullback_strategy_score: Optional[float] = None
    min_breakout_strategy_score: Optional[float] = None
    min_fundamental_score: Optional[float] = None
    max_double_top_confidence: Optional[float] = 70.0
    score_id: Optional[str] = "S002_StrategyScore"
    latest_only_per_symbol: bool = True
    apply_market_regime_adjustment: bool = True


class Screener:
    """スコア結果をスクリーニング条件でフィルタリングするクラス"""

    @staticmethod
    def _normalize_date(value: Any) -> date:
        if isinstance(value, datetime):
            return value.date()
        return value

    def _select_latest_per_symbol(
        self, score_results: List[ScoreResultModel]
    ) -> List[ScoreResultModel]:
        """各銘柄について最新日付のレコードのみを抽出する"""
        latest_date_by_symbol: Dict[str, date] = {}
        for result in score_results:
            norm_date = self._normalize_date(result.date)
            prev_date = latest_date_by_symbol.get(result.symbol)
            if prev_date is None or norm_date > prev_date:
                latest_date_by_symbol[result.symbol] = norm_date

        selected: List[ScoreResultModel] = []
        seen_symbols: set[str] = set()
        for result in score_results:
            norm_date = self._normalize_date(result.date)
            if (
                result.symbol not in seen_symbols
                and norm_date == latest_date_by_symbol[result.symbol]
            ):
                selected.append(result)
                seen_symbols.add(result.symbol)
        return selected

    def _resolve_breakout_threshold_delta(
        self,
        result: ScoreResultModel,
        metadata: Dict[str, Any],
        market_context: Optional[MarketContextModel],
    ) -> float:
        """
        ブレイクアウト戦略用の地合い悪化レジーム閾値引き上げ幅（単一ソース・非負）を解決する。
        二重加算を防ぐため、market_context（アクティブかつ日付整合）がある場合はそちらのみを参照し、
        未指定時のみ metadata["breakout_threshold_delta"] を参照する。
        """
        if result.strategy_type != "breakout":
            return 0.0

        if market_context is not None:
            if not market_context.is_active:
                return 0.0
            res_date = self._normalize_date(result.date)
            ctx_as_of = self._normalize_date(market_context.as_of_date)
            sym_ctx = market_context.symbol_metrics.get(result.symbol)
            if sym_ctx is not None:
                sym_bar_dt = self._normalize_date(sym_ctx.bar_date)
                if sym_bar_dt is not None:
                    if sym_bar_dt != res_date:
                        return 0.0
                elif ctx_as_of != res_date:
                    return 0.0
            elif ctx_as_of != res_date:
                return 0.0
            raw_delta = market_context.breakout_threshold_delta
        else:
            raw_delta = metadata.get("breakout_threshold_delta", 0.0)

        if raw_delta is None or isinstance(raw_delta, bool):
            return 0.0
        try:
            delta = float(raw_delta)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(delta):
            return 0.0
        return max(0.0, delta)

    def apply_screener(
        self,
        score_results: List[ScoreResultModel],
        criteria: Union[ScreeningCriteria, Dict[str, Any], None] = None,
        market_context: Optional[MarketContextModel] = None,
    ) -> List[ScoreResultModel]:
        """
        指定された条件でスコア結果をフィルタリングし、合致する銘柄のリストを返す。
        criteria が dict の場合は明示指定されたキーのみを評価し、後方互換性を維持する。
        criteria が None または ScreeningCriteria の場合は全条件を厳格に評価する。
        """
        if not score_results:
            return []

        if isinstance(criteria, dict):
            rule_map: Dict[str, Any] = criteria
            if "apply_market_regime_adjustment" in rule_map:
                apply_market_regime = bool(rule_map.get("apply_market_regime_adjustment"))
            else:
                apply_market_regime = market_context is not None
        else:
            cond = criteria or ScreeningCriteria()
            rule_map = cond.model_dump()
            apply_market_regime = bool(rule_map.get("apply_market_regime_adjustment", True))

        # 1. score_id 指定時の一致チェック
        target_score_id = rule_map.get("score_id")
        candidates = (
            [r for r in score_results if r.score_id == target_score_id]
            if target_score_id is not None
            else list(score_results)
        )

        # 2. 銘柄ごとの最新日付レコード抽出
        if rule_map.get("latest_only_per_symbol"):
            candidates = self._select_latest_per_symbol(candidates)

        min_total_score = rule_map.get("min_total_score")
        min_trend_env_score = rule_map.get("min_trend_env_score")
        require_gate1_passed = bool(rule_map.get("require_gate1_passed", False))
        exclude_watch = bool(rule_map.get("exclude_watch", False))
        allowed_strategies = rule_map.get("allowed_strategies")
        min_pullback_score = rule_map.get("min_pullback_strategy_score")
        min_breakout_score = rule_map.get("min_breakout_strategy_score")
        min_fundamental_score = rule_map.get("min_fundamental_score")
        max_double_top_confidence = rule_map.get("max_double_top_confidence")

        filtered_results: List[ScoreResultModel] = []
        for result in candidates:
            metadata = result.metadata or {}
            sub_scores = result.sub_scores or {}

            # 3. 第1関門通過チェック（未設定時は min_trend_env_score で代替判定）
            if require_gate1_passed:
                if "gate1_passed" in metadata:
                    if metadata.get("gate1_passed") is False:
                        continue
                else:
                    fallback_threshold = (
                        min_trend_env_score
                        if min_trend_env_score is not None
                        else 50.0
                    )
                    trend_val = sub_scores.get("trend_env_score")
                    if trend_val is None or trend_val < fallback_threshold:
                        continue

            # 4. トレンド環境スコア下限チェック
            if min_trend_env_score is not None:
                trend_val = sub_scores.get("trend_env_score")
                if trend_val is None or trend_val < min_trend_env_score:
                    continue

            # 5. watch（見送り）除外チェック
            if exclude_watch and result.strategy_type == "watch":
                continue

            # 6. 許可戦略リストチェック
            if allowed_strategies is not None:
                if result.strategy_type not in allowed_strategies:
                    continue

            breakout_delta = (
                self._resolve_breakout_threshold_delta(result, metadata, market_context)
                if apply_market_regime
                else 0.0
            )

            # 7. 総合スコア下限チェック（ブレイクアウトかつ地合い悪化時は閾値を動的に引き上げ）
            if min_total_score is not None:
                effective_min_total = float(min_total_score) + breakout_delta
                if result.total_score < effective_min_total:
                    continue

            # 8. 戦略別・ファンダメンタルサブスコア下限チェック
            if min_pullback_score is not None and result.strategy_type == "pullback":
                pb_val = sub_scores.get("pullback_strategy_score")
                if pb_val is None or pb_val < min_pullback_score:
                    continue

            if min_breakout_score is not None and result.strategy_type == "breakout":
                bo_val = sub_scores.get("breakout_strategy_score")
                effective_min_breakout = float(min_breakout_score) + breakout_delta
                if bo_val is None or bo_val < effective_min_breakout:
                    continue

            if min_fundamental_score is not None:
                fund_val = sub_scores.get("fundamental_score")
                if fund_val is None or fund_val < min_fundamental_score:
                    continue

            # 9. ダブルトップ信頼度上限チェック
            if max_double_top_confidence is not None:
                dt_conf = metadata.get("double_top_confidence")
                if dt_conf is not None and dt_conf >= max_double_top_confidence:
                    continue

            filtered_results.append(result)

        logger.debug(
            f"スクリーニングが完了しました。{len(filtered_results)} 件の銘柄が抽出されました。"
        )
        return filtered_results


# モジュールレベルでインスタンス化
screener = Screener()


def apply_screener(
    score_results: List[ScoreResultModel],
    criteria: Union[ScreeningCriteria, Dict[str, Any], None] = None,
    market_context: Optional[MarketContextModel] = None,
) -> List[ScoreResultModel]:
    return screener.apply_screener(
        score_results, criteria, market_context=market_context
    )
