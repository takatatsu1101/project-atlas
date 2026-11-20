import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel

from src.model.data_models import (
    FeatureResultModel,
    FeatureSetModel,
    IndicatorSetModel,
    MarketContextModel,
    OhlcvModel,
    PatternSetModel,
    ScoreResultModel,
    SymbolMarketMetricsModel,
)
from src.score_engine.interfaces import IScoreCalculator
from src.score_engine.registry import score_registry

CORE_FEATURE_IDS: Tuple[str, ...] = (
    "M001_MAAlignmentScore",
    "T001_TrendStrengthScore",
    "P001_PullbackScore",
    "P002_BreakoutScore",
)

FUNDAMENTAL_FEATURE_WEIGHT_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("F001_ProfitabilityScore", "fundamental_weight_f001"),
    ("F002_GrowthScore", "fundamental_weight_f002"),
    ("F003_ValuationScore", "fundamental_weight_f003"),
    ("F004_FinancialHealthScore", "fundamental_weight_f004"),
    ("F005_EarningsQualityScore", "fundamental_weight_f005"),
    ("F006_ShareholderReturnScore", "fundamental_weight_f006"),
)

FUNDAMENTAL_FEATURE_IDS: Tuple[str, ...] = tuple(
    fid for fid, _ in FUNDAMENTAL_FEATURE_WEIGHT_FIELDS
)


class StrategyScoreConfig(BaseModel):
    """3段階ゲート＆戦略別スコアリングの設定モデル"""

    # 第1関門（トレンド環境ゲート）
    min_trend_env_score: float = 50.0
    require_above_sma75: bool = True
    gate1_failed_cap: float = 35.0

    # 弱気・過熱ペナルティ
    double_top_penalty_threshold: float = 40.0
    double_top_high_confidence_threshold: float = 70.0
    double_top_penalty_factor: float = 0.35
    double_top_high_confidence_cap: float = 40.0
    extreme_volatility_threshold: float = 90.0
    extreme_volatility_penalty: float = 10.0
    extreme_volatility_ratio_threshold: float = 2.0
    sma75_dev_overheat_threshold: float = 0.25
    sma75_dev_overheat_penalty: float = 12.0
    gap_up_overheat_threshold: float = 0.07
    gap_up_overheat_penalty: float = 10.0

    # 戦略別 RSI ベル型評価・短期反転設定
    pullback_rsi_ideal_min: float = 40.0
    pullback_rsi_ideal_max: float = 60.0
    breakout_rsi_ideal_min: float = 55.0
    breakout_rsi_ideal_max: float = 75.0
    rsi_overheat_threshold: float = 80.0
    rsi_overheat_penalty: float = 8.0
    short_rsi_rebound_bonus: float = 5.0

    # 第2関門・戦略判定
    min_pullback_setup_score: float = 55.0
    min_breakout_setup_score: float = 55.0
    min_entry_score: float = 60.0
    watch_score_cap: float = 59.0

    # 押し目買い戦略の重み・裏付け加点
    pullback_weight_p001: float = 0.38
    pullback_weight_trend_env: float = 0.22
    pullback_weight_o001: float = 0.15
    pullback_weight_fundamental: float = 0.10
    pullback_weight_volatility_stability: float = 0.10
    pullback_weight_v001: float = 0.05
    double_bottom_bonus_factor: float = 0.10
    double_bottom_bonus_max: float = 10.0
    hammer_bonus_factor: float = 0.05
    hammer_bonus_max: float = 5.0
    pullback_dryup_rebound_bonus: float = 5.0

    # ブレイクアウト戦略の重み
    breakout_weight_p002: float = 0.40
    breakout_weight_v001: float = 0.25
    breakout_weight_o001: float = 0.15
    breakout_weight_trend_env: float = 0.10
    breakout_weight_fundamental: float = 0.10

    # ファンダメンタルズ特徴量別の相対重み（デフォルト均等 1.0、欠損時は取得可能項目へ自動再配分）
    fundamental_weight_f001: float = 1.0
    fundamental_weight_f002: float = 1.0
    fundamental_weight_f003: float = 1.0
    fundamental_weight_f004: float = 1.0
    fundamental_weight_f005: float = 1.0
    fundamental_weight_f006: float = 1.0

    # 必須特徴量チェック
    require_core_features: bool = True


class StrategyScoreCalculator(IScoreCalculator):
    """3段階ゲートと2戦略（押し目買い／ブレイクアウト）を用いたスコア計算クラス"""

    score_id: str = "S002_StrategyScore"
    score_name: str = "Strategy Score (3-Stage Gate)"
    score_category: str = "Strategy"

    def __init__(self, config: Optional[StrategyScoreConfig] = None):
        self.config = config or StrategyScoreConfig()

    def calculate(
        self,
        feature_sets: List[FeatureSetModel],
        pattern_sets: List[PatternSetModel],
        ohlcv_data: Optional[List[OhlcvModel]] = None,
        indicator_sets: Optional[List[IndicatorSetModel]] = None,
        market_context: Optional[MarketContextModel] = None,
    ) -> List[ScoreResultModel]:
        """
        特徴量セット・パターンセット・OHLCV・指標セット・市場コンテキストを日付単位で突合し、
        3段階ゲートによる戦略別スコアを計算する。
        """
        if not feature_sets:
            return []

        pattern_map = self._index_by_symbol_date(pattern_sets or [])
        ohlcv_map = self._index_by_symbol_date(ohlcv_data or [])
        indicator_map = self._index_by_symbol_date(indicator_sets or [])

        results: List[ScoreResultModel] = []
        for fs in feature_sets:
            key = (fs.symbol, self._normalize_date(fs.date))
            ps = pattern_map.get(key)
            ohlcv = ohlcv_map.get(key)
            ind_set = indicator_map.get(key)
            results.append(
                self._evaluate_single_day(
                    fs, ps, ohlcv, ind_set, market_context=market_context
                )
            )

        return results

    def _evaluate_single_day(
        self,
        feature_set: FeatureSetModel,
        pattern_set: Optional[PatternSetModel],
        ohlcv: Optional[OhlcvModel],
        indicator_set: Optional[IndicatorSetModel],
        market_context: Optional[MarketContextModel] = None,
    ) -> ScoreResultModel:
        """1日分の特徴量・パターン等から戦略スコアと根拠を算出する。"""
        feature_map: Dict[str, FeatureResultModel] = {
            fr.feature_id: fr for fr in feature_set.results
        }
        pattern_conf_map: Dict[str, float] = {}
        if pattern_set:
            for pr in pattern_set.results:
                prev = pattern_conf_map.get(pr.pattern_id, 0.0)
                pattern_conf_map[pr.pattern_id] = max(prev, float(pr.confidence))

        key_levels = self._extract_key_levels(feature_map, ohlcv, indicator_set)
        risk_metrics = self._extract_risk_metrics(
            feature_map, ohlcv, indicator_set, key_levels.get("close")
        )

        # 必須テクニカル特徴量の欠損チェック
        missing_core = [fid for fid in CORE_FEATURE_IDS if fid not in feature_map]
        if self.config.require_core_features and missing_core:
            reasons = [
                f"必須特徴量が欠損しているため見送り判定としました（欠損: {', '.join(missing_core)}）。"
            ]
            sub_scores = {
                "pullback_strategy_score": 0.0,
                "breakout_strategy_score": 0.0,
                "trend_env_score": 0.0,
                "fundamental_score": 0.0,
                "penalty_score": 0.0,
            }
            return ScoreResultModel(
                symbol=feature_set.symbol,
                date=feature_set.date,
                score_id=self.score_id,
                sub_scores=sub_scores,
                total_score=0.0,
                strategy_type="watch",
                reasons=reasons,
                key_levels=key_levels,
                risk_metrics=risk_metrics,
                metadata={
                    "strategy_type": "watch",
                    "reasons": reasons,
                    "key_levels": key_levels,
                    "risk_metrics": risk_metrics,
                    "missing_core_features": missing_core,
                    "gate1_passed": False,
                },
            )

        reasons: List[str] = []

        # 各特徴量スコアを取得（任意特徴量は欠損時中立50.0）
        m001 = self._get_feature_score(feature_map, "M001_MAAlignmentScore", 50.0)
        t001 = self._get_feature_score(feature_map, "T001_TrendStrengthScore", 50.0)
        p001 = self._get_feature_score(feature_map, "P001_PullbackScore", 50.0)
        p002 = self._get_feature_score(feature_map, "P002_BreakoutScore", 50.0)
        o001 = self._get_feature_score(feature_map, "O001_MomentumScore", 50.0)
        v001 = self._get_feature_score(feature_map, "V001_VolumeScore", 50.0)
        vol_score = self._get_feature_score(feature_map, "R001_VolatilityScore", 50.0)

        fundamental_score, fundamental_missing = self._calculate_fundamental_score(feature_map)
        if fundamental_missing:
            reasons.append("ファンダメンタルズ特徴量が未取得のため中立値(50.0)で補完しました。")
        else:
            reasons.append(f"ファンダメンタルズ平均スコアは {fundamental_score:.1f} 点です。")

        # 第1関門：トレンド環境判定
        trend_env_score = 0.5 * m001 + 0.5 * t001
        close_price = key_levels.get("close")
        sma75 = key_levels.get("sma75")

        trend_failed = trend_env_score < self.config.min_trend_env_score
        below_sma75 = (
            self.config.require_above_sma75
            and close_price is not None
            and sma75 is not None
            and close_price < sma75
        )
        gate1_passed = not (trend_failed or below_sma75)

        if gate1_passed:
            reasons.append(f"第1関門（トレンド環境）を通過しました（環境スコア: {trend_env_score:.1f}）。")
        else:
            if trend_failed:
                reasons.append(
                    f"第1関門未達: トレンド環境スコア({trend_env_score:.1f})が基準({self.config.min_trend_env_score:.1f})未満です。"
                )
            if below_sma75:
                reasons.append(
                    f"第1関門未達: 終値({close_price:.2f})が75日移動平均線({sma75:.2f})を下回っています。"
                )

        # ボラティリティ安定性（新R001: 高いほど低リスク・VCP収縮良好）と異常過熱ペナルティ
        volatility_stability = self._clip_score(vol_score)
        penalty_score = 0.0
        volatility_ratio = risk_metrics.get("volatility_ratio")
        low_vol_score_threshold = 100.0 - self.config.extreme_volatility_threshold
        is_extreme_volatility = (
            volatility_ratio is not None
            and volatility_ratio >= self.config.extreme_volatility_ratio_threshold
        ) or (vol_score <= low_vol_score_threshold)
        if is_extreme_volatility:
            penalty_score += self.config.extreme_volatility_penalty
            ratio_info = f", ratio={volatility_ratio:.2f}" if volatility_ratio is not None else ""
            reasons.append(
                f"異常ボラティリティ過熱(R001={vol_score:.1f}{ratio_info})のため {self.config.extreme_volatility_penalty:.1f} 点を減点しました。"
            )

        # 戦略別 RSI ベル型評価・RSI過熱減点・短期反転加点
        rsi14 = self._get_metadata_float(feature_map, ("O001_MomentumScore",), "rsi14")
        if rsi14 is None and indicator_set is not None:
            rsi14 = self._to_optional_float(indicator_set.indicators.get("RSI14"))

        if rsi14 is not None:
            pullback_bell_rsi = self._calc_rsi_bell_score(
                rsi14,
                self.config.pullback_rsi_ideal_min,
                self.config.pullback_rsi_ideal_max,
            )
            breakout_bell_rsi = self._calc_rsi_bell_score(
                rsi14,
                self.config.breakout_rsi_ideal_min,
                self.config.breakout_rsi_ideal_max,
            )
            pullback_momentum = 0.5 * o001 + 0.5 * pullback_bell_rsi
            breakout_momentum = 0.5 * o001 + 0.5 * breakout_bell_rsi

            if rsi14 > self.config.rsi_overheat_threshold:
                penalty_score += self.config.rsi_overheat_penalty
                reasons.append(
                    f"RSI過熱(RSI14={rsi14:.1f} > {self.config.rsi_overheat_threshold:.1f})のため {self.config.rsi_overheat_penalty:.1f} 点を減点しました。"
                )
        else:
            pullback_momentum = o001
            breakout_momentum = o001

        short_rsi = self._get_metadata_float(feature_map, ("O001_MomentumScore",), "short_rsi")
        prev_short_rsi = self._get_metadata_float(feature_map, ("O001_MomentumScore",), "prev_short_rsi")
        short_rsi_rebound_bonus = 0.0
        if (
            short_rsi is not None
            and prev_short_rsi is not None
            and prev_short_rsi <= 35.0
            and short_rsi > prev_short_rsi
        ):
            short_rsi_rebound_bonus = self.config.short_rsi_rebound_bonus
            reasons.append(
                f"短期RSI反転(RSI5: {prev_short_rsi:.1f}→{short_rsi:.1f})により押し目買いへ +{short_rsi_rebound_bonus:.1f} 点加点しました。"
            )

        # 押し目売り枯れ→反発出来高増の加点
        pullback_dryup_rebound_bonus = 0.0
        v001_fr = feature_map.get("V001_VolumeScore")
        if (
            v001_fr is not None
            and isinstance(v001_fr.metadata, dict)
            and v001_fr.metadata.get("pullback_dryup_rebound") is True
        ):
            pullback_dryup_rebound_bonus = self.config.pullback_dryup_rebound_bonus
            reasons.append(
                f"押し目売り枯れ後の反発出来高増により押し目買いへ +{pullback_dryup_rebound_bonus:.1f} 点加点しました。"
            )

        # 75日移動平均線からの過熱乖離ペナルティ
        if close_price is not None and sma75 is not None and sma75 > 0:
            sma75_dev = (close_price - sma75) / sma75
            if sma75_dev > self.config.sma75_dev_overheat_threshold:
                penalty_score += self.config.sma75_dev_overheat_penalty
                reasons.append(
                    f"75日線乖離過熱({sma75_dev * 100:.1f}% > {self.config.sma75_dev_overheat_threshold * 100:.1f}%)のため {self.config.sma75_dev_overheat_penalty:.1f} 点を減点しました。"
                )

        # 大幅ギャップアップ過熱ペナルティ（ブレイクアウト戦略専用）
        gap_pct = self._get_metadata_float(feature_map, ("P002_BreakoutScore",), "gap_pct")
        gap_up_penalty = 0.0
        if gap_pct is not None and gap_pct > self.config.gap_up_overheat_threshold:
            gap_up_penalty = self.config.gap_up_overheat_penalty
            reasons.append(
                f"大幅ギャップアップ過熱(gap={gap_pct * 100:.1f}% > {self.config.gap_up_overheat_threshold * 100:.1f}%)のためブレイクアウト戦略から {gap_up_penalty:.1f} 点を減点しました。"
            )

        # パターン確認：押し目買い裏付け加点＆ダブルトップ弱気ペナルティ
        double_bottom_bonus = 0.0
        if "R001_DoubleBottom" in pattern_conf_map:
            conf = pattern_conf_map["R001_DoubleBottom"]
            double_bottom_bonus = min(
                self.config.double_bottom_bonus_max,
                conf * self.config.double_bottom_bonus_factor,
            )
            reasons.append(
                f"ダブルボトム検出(信頼度 {conf:.1f})により押し目買いへ +{double_bottom_bonus:.1f} 点加点しました。"
            )

        hammer_bonus = 0.0
        if "P001_Hammer" in pattern_conf_map:
            conf = pattern_conf_map["P001_Hammer"]
            hammer_bonus = min(
                self.config.hammer_bonus_max,
                conf * self.config.hammer_bonus_factor,
            )
            reasons.append(
                f"ハンマー検出(信頼度 {conf:.1f})により押し目買いへ +{hammer_bonus:.1f} 点加点しました。"
            )

        double_top_conf = pattern_conf_map.get("R002_DoubleTop", 0.0)
        high_conf_double_top = False
        if (
            "R002_DoubleTop" in pattern_conf_map
            and double_top_conf >= self.config.double_top_penalty_threshold
        ):
            dt_penalty = double_top_conf * self.config.double_top_penalty_factor
            penalty_score += dt_penalty
            reasons.append(
                f"ダブルトップ警戒(信頼度 {double_top_conf:.1f})により {dt_penalty:.1f} 点を減点しました。"
            )
            if double_top_conf >= self.config.double_top_high_confidence_threshold:
                high_conf_double_top = True
                reasons.append(
                    f"高信頼度のダブルトップ検出のためスコア上限を {self.config.double_top_high_confidence_cap:.1f} 点に制限し、見送り判定としました。"
                )

        # 市場コンテキスト（RS・業種モメンタム・業種内相対バリュエーション・地合いレジーム）の整合解決
        fs_date = self._normalize_date(feature_set.date)
        context_applied = False
        sym_ctx: Optional[SymbolMarketMetricsModel] = None
        if market_context is not None and market_context.is_active:
            ctx_as_of = self._normalize_date(market_context.as_of_date)
            candidate_sym_ctx = market_context.symbol_metrics.get(feature_set.symbol)
            if candidate_sym_ctx is not None:
                sym_bar_dt = self._normalize_date(candidate_sym_ctx.bar_date)
                date_matched = (
                    (sym_bar_dt == fs_date)
                    if sym_bar_dt is not None
                    else (ctx_as_of == fs_date)
                )
                if date_matched:
                    context_applied = True
                    sym_ctx = candidate_sym_ctx
            elif ctx_as_of == fs_date:
                context_applied = True

        pullback_context_adj = 0.0
        breakout_context_adj = 0.0
        if context_applied and sym_ctx is not None:
            raw_pb_adj = self._to_optional_float(sym_ctx.pullback_adjustment)
            if raw_pb_adj is None:
                raw_pb_adj = self._to_optional_float(sym_ctx.total_adjustment)
            if raw_pb_adj is not None:
                pullback_context_adj = raw_pb_adj

            raw_bo_adj = self._to_optional_float(sym_ctx.breakout_adjustment)
            if raw_bo_adj is None:
                raw_bo_adj = self._to_optional_float(sym_ctx.total_adjustment)
            if raw_bo_adj is not None:
                breakout_context_adj = raw_bo_adj

        raw_delta = (
            self._to_optional_float(market_context.breakout_threshold_delta)
            if (context_applied and market_context is not None)
            else None
        )
        breakout_threshold_delta = max(0.0, raw_delta) if raw_delta is not None else 0.0

        raw_penalty = (
            self._to_optional_float(market_context.breakout_score_penalty)
            if (context_applied and market_context is not None)
            else None
        )
        breakout_regime_penalty = max(0.0, raw_penalty) if raw_penalty is not None else 0.0

        # 両戦略スコアの算出
        raw_pullback = (
            p001 * self.config.pullback_weight_p001
            + trend_env_score * self.config.pullback_weight_trend_env
            + pullback_momentum * self.config.pullback_weight_o001
            + fundamental_score * self.config.pullback_weight_fundamental
            + volatility_stability * self.config.pullback_weight_volatility_stability
            + v001 * self.config.pullback_weight_v001
            + double_bottom_bonus
            + hammer_bonus
            + short_rsi_rebound_bonus
            + pullback_dryup_rebound_bonus
            - penalty_score
            + pullback_context_adj
        )
        raw_breakout = (
            p002 * self.config.breakout_weight_p002
            + v001 * self.config.breakout_weight_v001
            + breakout_momentum * self.config.breakout_weight_o001
            + trend_env_score * self.config.breakout_weight_trend_env
            + fundamental_score * self.config.breakout_weight_fundamental
            - penalty_score
            - gap_up_penalty
            + breakout_context_adj
            - breakout_regime_penalty
        )

        if context_applied and sym_ctx is not None:
            ctx_parts: List[str] = []
            if sym_ctx.rs_percentile is not None:
                ctx_parts.append(
                    f"RS順位={sym_ctx.rs_percentile:.1f}%({sym_ctx.rs_adjustment:+.1f})"
                )
            if sym_ctx.sector_momentum_score is not None:
                sec_label = sym_ctx.sector_33 or "業種"
                ctx_parts.append(
                    f"{sec_label}モメンタム={sym_ctx.sector_momentum_score:.1f}({sym_ctx.sector_momentum_adjustment:+.1f})"
                )
            if sym_ctx.relative_valuation_z is not None:
                ctx_parts.append(
                    f"業種内相対バリュエーションZ={sym_ctx.relative_valuation_z:+.2f}({sym_ctx.relative_valuation_adjustment:+.1f})"
                )
            if ctx_parts:
                adj_label = (
                    f"{pullback_context_adj:+.1f}点"
                    if abs(pullback_context_adj - breakout_context_adj) < 1e-6
                    else f"押し目={pullback_context_adj:+.1f}点/ブレイク={breakout_context_adj:+.1f}点"
                )
                reasons.append(
                    f"市場コンテキスト補正({adj_label}): " + ", ".join(ctx_parts)
                )

        if (
            context_applied
            and (breakout_threshold_delta > 0.0 or breakout_regime_penalty > 0.0)
            and market_context is not None
        ):
            breadth_str = (
                f"{market_context.breadth_ratio * 100:.1f}%"
                if market_context.breadth_ratio is not None
                else "-"
            )
            effective_bo_entry = self.config.min_entry_score + breakout_threshold_delta
            regime_actions: List[str] = []
            if breakout_regime_penalty > 0.0:
                regime_actions.append(f"ブレイクアウト減点={-breakout_regime_penalty:+.1f}点")
            if breakout_threshold_delta > 0.0:
                regime_actions.append(
                    f"ブレイクアウト要求スコア={effective_bo_entry:.1f}点(+{breakout_threshold_delta:.1f})"
                )
            reasons.append(
                f"地合い悪化レジーム({market_context.regime}, Breadth={breadth_str})のため"
                + "、".join(regime_actions)
                + "を適用しました。"
            )

        # 第1関門未達・高信頼度ダブルトップによる上限キャップ適用
        if not gate1_passed:
            raw_pullback = min(raw_pullback, self.config.gate1_failed_cap)
            raw_breakout = min(raw_breakout, self.config.gate1_failed_cap)
        if high_conf_double_top:
            raw_pullback = min(raw_pullback, self.config.double_top_high_confidence_cap)
            raw_breakout = min(raw_breakout, self.config.double_top_high_confidence_cap)

        pullback_strategy_score = self._clip_score(raw_pullback)
        breakout_strategy_score = self._clip_score(raw_breakout)

        # 第2関門・推奨戦略タイプおよび代表スコアの連動決定
        strategy_type, total_score = self._decide_strategy_and_score(
            gate1_passed=gate1_passed,
            high_conf_double_top=high_conf_double_top,
            pullback_score=pullback_strategy_score,
            breakout_score=breakout_strategy_score,
            p001=p001,
            p002=p002,
            breakout_threshold_delta=breakout_threshold_delta,
        )

        if strategy_type == "pullback":
            reasons.append(
                f"第2・第3関門を通過し、押し目買い戦略を採用しました（押し目: {pullback_strategy_score:.1f} / ブレイク: {breakout_strategy_score:.1f}）。"
            )
        elif strategy_type == "breakout":
            reasons.append(
                f"第2・第3関門を通過し、ブレイクアウト戦略を採用しました（ブレイク: {breakout_strategy_score:.1f} / 押し目: {pullback_strategy_score:.1f}）。"
            )
        else:
            if gate1_passed and not high_conf_double_top:
                pullback_setup_ok = p001 >= self.config.min_pullback_setup_score
                breakout_setup_ok = p002 >= self.config.min_breakout_setup_score
                if not pullback_setup_ok and not breakout_setup_ok:
                    reasons.append(
                        f"主軸セットアップ条件（P001>={self.config.min_pullback_setup_score:.1f} または P002>={self.config.min_breakout_setup_score:.1f}）未達のため見送り(watch)としました。"
                    )
                else:
                    effective_bo_entry = self.config.min_entry_score + breakout_threshold_delta
                    if breakout_threshold_delta > 0.0 and breakout_setup_ok:
                        reasons.append(
                            f"適格戦略の総合スコアがエントリー基準(押し目:{self.config.min_entry_score:.1f} / ブレイク:{effective_bo_entry:.1f})未満のため見送り(watch)としました（押し目: {pullback_strategy_score:.1f} / ブレイク: {breakout_strategy_score:.1f}）。"
                        )
                    else:
                        reasons.append(
                            f"適格戦略の総合スコアがエントリー基準({self.config.min_entry_score:.1f})未満のため見送り(watch)としました（押し目: {pullback_strategy_score:.1f} / ブレイク: {breakout_strategy_score:.1f}）。"
                        )

        sub_scores: Dict[str, float] = {
            "pullback_strategy_score": pullback_strategy_score,
            "breakout_strategy_score": breakout_strategy_score,
            "trend_env_score": trend_env_score,
            "fundamental_score": fundamental_score,
            "penalty_score": penalty_score,
        }
        metadata: Dict[str, Any] = {
            "strategy_type": strategy_type,
            "reasons": reasons,
            "key_levels": key_levels,
            "risk_metrics": risk_metrics,
            "gate1_passed": gate1_passed,
            "volatility_stability": volatility_stability,
            "double_top_confidence": double_top_conf,
        }

        if context_applied and market_context is not None:
            if strategy_type == "pullback":
                applied_context_adj = pullback_context_adj
            elif strategy_type == "breakout":
                applied_context_adj = breakout_context_adj - breakout_regime_penalty
            else:
                applied_context_adj = (
                    float(sym_ctx.total_adjustment) if sym_ctx is not None else 0.0
                )
            sub_scores["market_context_adjustment"] = round(applied_context_adj, 4)
            if sym_ctx is not None:
                if sym_ctx.rs_percentile is not None:
                    sub_scores["rs_score"] = round(float(sym_ctx.rs_percentile), 4)
                if sym_ctx.sector_momentum_score is not None:
                    sub_scores["sector_momentum_score"] = round(
                        float(sym_ctx.sector_momentum_score), 4
                    )
                if sym_ctx.relative_valuation_score is not None:
                    sub_scores["relative_valuation_score"] = round(
                        float(sym_ctx.relative_valuation_score), 4
                    )

            ctx_as_of_norm = self._normalize_date(market_context.as_of_date)
            metadata["market_regime"] = market_context.regime
            metadata["market_breadth_ratio"] = market_context.breadth_ratio
            metadata["breakout_threshold_delta"] = breakout_threshold_delta
            metadata["market_context"] = {
                "as_of_date": ctx_as_of_norm.isoformat() if ctx_as_of_norm else None,
                "regime": market_context.regime,
                "breadth_ratio": market_context.breadth_ratio,
                "breakout_threshold_delta": breakout_threshold_delta,
                "breakout_score_penalty": breakout_regime_penalty,
                "benchmark_return_20d": market_context.benchmark.return_20d,
                "benchmark_return_60d": market_context.benchmark.return_60d,
                "sector_33": sym_ctx.sector_33 if sym_ctx else None,
                "rs_percentile": sym_ctx.rs_percentile if sym_ctx else None,
                "rs_adjustment": sym_ctx.rs_adjustment if sym_ctx else 0.0,
                "sector_momentum_score": sym_ctx.sector_momentum_score if sym_ctx else None,
                "sector_momentum_adjustment": (
                    sym_ctx.sector_momentum_adjustment if sym_ctx else 0.0
                ),
                "relative_valuation_z": sym_ctx.relative_valuation_z if sym_ctx else None,
                "relative_valuation_score": (
                    sym_ctx.relative_valuation_score if sym_ctx else None
                ),
                "relative_valuation_adjustment": (
                    sym_ctx.relative_valuation_adjustment if sym_ctx else 0.0
                ),
                "pullback_adjustment": pullback_context_adj,
                "breakout_adjustment": breakout_context_adj,
                "total_adjustment": applied_context_adj,
            }

        return ScoreResultModel(
            symbol=feature_set.symbol,
            date=feature_set.date,
            score_id=self.score_id,
            sub_scores=sub_scores,
            total_score=total_score,
            strategy_type=strategy_type,
            reasons=reasons,
            key_levels=key_levels,
            risk_metrics=risk_metrics,
            metadata=metadata,
        )

    def _decide_strategy_and_score(
        self,
        gate1_passed: bool,
        high_conf_double_top: bool,
        pullback_score: float,
        breakout_score: float,
        p001: float,
        p002: float,
        breakout_threshold_delta: float = 0.0,
    ) -> Tuple[str, float]:
        """第2関門の適格性判定に基づき、推奨戦略タイプと代表スコアを連動して決定する。"""
        base_ok = gate1_passed and not high_conf_double_top
        effective_breakout_min_entry = self.config.min_entry_score + max(
            0.0, breakout_threshold_delta
        )
        pullback_eligible = (
            base_ok
            and (p001 >= self.config.min_pullback_setup_score)
            and (pullback_score >= self.config.min_entry_score)
        )
        breakout_eligible = (
            base_ok
            and (p002 >= self.config.min_breakout_setup_score)
            and (breakout_score >= effective_breakout_min_entry)
        )

        if pullback_eligible and breakout_eligible:
            if pullback_score >= breakout_score:
                return "pullback", pullback_score
            return "breakout", breakout_score
        if pullback_eligible:
            return "pullback", pullback_score
        if breakout_eligible:
            return "breakout", breakout_score

        watch_score = min(max(pullback_score, breakout_score), self.config.watch_score_cap)
        return "watch", watch_score

    def _calculate_fundamental_score(
        self, feature_map: Dict[str, FeatureResultModel]
    ) -> Tuple[float, bool]:
        """ファンダメンタルズ特徴量（F001〜F006）の加重平均を算出する。全欠損・有効重みなし時は中立50.0を返す。"""
        weighted_sum = 0.0
        weight_sum = 0.0
        for fid, weight_field in FUNDAMENTAL_FEATURE_WEIGHT_FIELDS:
            if fid not in feature_map:
                continue
            score = self._to_optional_float(feature_map[fid].score)
            weight = self._to_optional_float(getattr(self.config, weight_field, 1.0))
            if score is None or weight is None or weight <= 0.0:
                continue
            weighted_sum += score * weight
            weight_sum += weight
        if weight_sum <= 0.0:
            return 50.0, True
        return weighted_sum / weight_sum, False

    def _extract_key_levels(
        self,
        feature_map: Dict[str, FeatureResultModel],
        ohlcv: Optional[OhlcvModel],
        indicator_set: Optional[IndicatorSetModel],
    ) -> Dict[str, Optional[float]]:
        """主要価格水準とSMA乖離率を構築する（indicator_sets / ohlcv 優先、metadata で補完）。"""
        indicators = indicator_set.indicators if indicator_set else {}

        close = self._to_optional_float(ohlcv.close) if ohlcv else None
        if close is None:
            close = self._get_metadata_float(
                feature_map,
                ("P001_PullbackScore", "P002_BreakoutScore", "T001_TrendStrengthScore", "R001_VolatilityScore"),
                "close",
            )

        sma5 = self._to_optional_float(indicators.get("SMA5"))
        if sma5 is None:
            sma5 = self._get_metadata_float(
                feature_map, ("M001_MAAlignmentScore", "T001_TrendStrengthScore", "P001_PullbackScore"), "sma5"
            )

        sma25 = self._to_optional_float(indicators.get("SMA25"))
        if sma25 is None:
            sma25 = self._get_metadata_float(
                feature_map, ("M001_MAAlignmentScore", "T001_TrendStrengthScore", "P001_PullbackScore"), "sma25"
            )

        sma75 = self._to_optional_float(indicators.get("SMA75"))
        if sma75 is None:
            sma75 = self._get_metadata_float(
                feature_map, ("M001_MAAlignmentScore", "T001_TrendStrengthScore", "P001_PullbackScore"), "sma75"
            )

        highest_high = self._to_optional_float(indicators.get("HIGHEST_HIGH_20"))
        if highest_high is None:
            highest_high = self._get_metadata_float(feature_map, ("P002_BreakoutScore",), "highest_high")

        lowest_low = self._to_optional_float(indicators.get("LOWEST_LOW_20"))
        if lowest_low is None:
            lowest_low = self._get_metadata_float(feature_map, ("P001_PullbackScore", "P002_BreakoutScore"), "lowest_low")

        return {
            "close": close,
            "sma5": sma5,
            "sma25": sma25,
            "sma75": sma75,
            "highest_high": highest_high,
            "lowest_low": lowest_low,
            "sma5_deviation_pct": self._calc_deviation_pct(close, sma5),
            "sma25_deviation_pct": self._calc_deviation_pct(close, sma25),
            "sma75_deviation_pct": self._calc_deviation_pct(close, sma75),
        }

    def _extract_risk_metrics(
        self,
        feature_map: Dict[str, FeatureResultModel],
        ohlcv: Optional[OhlcvModel],
        indicator_set: Optional[IndicatorSetModel],
        close: Optional[float],
    ) -> Dict[str, Optional[float]]:
        """ATR・ボラティリティ比率・出来高倍率等のリスク指標を構築する。"""
        indicators = indicator_set.indicators if indicator_set else {}

        avg_atr_meta = self._get_metadata_float(feature_map, ("R001_VolatilityScore",), "avg_atr")
        tr_today_meta = self._get_metadata_float(feature_map, ("R001_VolatilityScore",), "tr_today")

        atr = self._to_optional_float(indicators.get("ATR14"))
        if atr is None:
            atr = avg_atr_meta

        atr_pct: Optional[float] = None
        if atr is not None and close is not None and close != 0:
            atr_pct = (atr / close) * 100.0

        volatility_ratio = self._get_metadata_float(
            feature_map, ("R001_VolatilityScore",), "volatility_ratio"
        )
        if volatility_ratio is None and tr_today_meta is not None and avg_atr_meta is not None and avg_atr_meta != 0:
            volatility_ratio = tr_today_meta / avg_atr_meta

        volume_ratio = self._to_optional_float(indicators.get("VOLUME_RATIO"))
        if volume_ratio is None:
            volume_meta = self._get_metadata_float(feature_map, ("V001_VolumeScore",), "volume")
            if volume_meta is None and ohlcv is not None:
                volume_meta = self._to_optional_float(ohlcv.volume)
            avg_vol_25 = self._get_metadata_float(feature_map, ("V001_VolumeScore",), "avg_volume_25")
            if volume_meta is not None and avg_vol_25 is not None and avg_vol_25 != 0:
                volume_ratio = volume_meta / avg_vol_25

        return {
            "atr": atr,
            "atr_pct": atr_pct,
            "volatility_ratio": volatility_ratio,
            "volume_ratio": volume_ratio,
        }

    @staticmethod
    def _normalize_date(d: Any) -> date:
        if isinstance(d, datetime):
            return d.date()
        return d

    def _index_by_symbol_date(self, items: List[Any]) -> Dict[Tuple[str, date], Any]:
        indexed: Dict[Tuple[str, date], Any] = {}
        for item in items:
            indexed[(item.symbol, self._normalize_date(item.date))] = item
        return indexed

    @staticmethod
    def _get_feature_score(
        feature_map: Dict[str, FeatureResultModel], feature_id: str, default: float
    ) -> float:
        fr = feature_map.get(feature_id)
        return float(fr.score) if fr is not None else default

    def _get_metadata_float(
        self,
        feature_map: Dict[str, FeatureResultModel],
        feature_ids: Tuple[str, ...],
        key: str,
    ) -> Optional[float]:
        for fid in feature_ids:
            fr = feature_map.get(fid)
            if fr and isinstance(fr.metadata, dict) and key in fr.metadata:
                val = self._to_optional_float(fr.metadata.get(key))
                if val is not None:
                    return val
        return None

    @staticmethod
    def _to_optional_float(val: Any) -> Optional[float]:
        if val is None or isinstance(val, bool):
            return None
        try:
            num = float(val)
        except (TypeError, ValueError):
            return None
        return num if math.isfinite(num) else None

    @staticmethod
    def _calc_deviation_pct(close: Optional[float], level: Optional[float]) -> Optional[float]:
        if close is None or level is None or level == 0:
            return None
        return ((close - level) / level) * 100.0

    @staticmethod
    def _calc_rsi_bell_score(rsi: float, ideal_min: float, ideal_max: float) -> float:
        """RSI を理想帯 [ideal_min, ideal_max] が 100 点となるベル型スコア（0〜100）へ変換する。"""
        if not math.isfinite(rsi):
            return 50.0
        if ideal_min <= rsi <= ideal_max:
            return 100.0
        if rsi < ideal_min:
            if ideal_min <= 0.0:
                return 100.0
            ratio = max(0.0, min(1.0, rsi / ideal_min))
            return ratio * 100.0
        # rsi > ideal_max
        if ideal_max >= 100.0:
            return 100.0
        ratio = max(0.0, min(1.0, (100.0 - rsi) / (100.0 - ideal_max)))
        return ratio * 100.0

    @classmethod
    def _clip_score(cls, val: float) -> float:
        num = cls._to_optional_float(val)
        if num is None:
            return 0.0
        return max(0.0, min(100.0, num))


# レジストリにスコア計算クラスを登録
score_registry.register(StrategyScoreCalculator)
