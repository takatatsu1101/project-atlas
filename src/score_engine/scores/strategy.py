from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel

from src.model.data_models import (
    FeatureResultModel,
    FeatureSetModel,
    IndicatorSetModel,
    OhlcvModel,
    PatternSetModel,
    ScoreResultModel,
)
from src.score_engine.interfaces import IScoreCalculator
from src.score_engine.registry import score_registry

CORE_FEATURE_IDS: Tuple[str, ...] = (
    "M001_MAAlignmentScore",
    "T001_TrendStrengthScore",
    "P001_PullbackScore",
    "P002_BreakoutScore",
)

FUNDAMENTAL_FEATURE_IDS: Tuple[str, ...] = (
    "F001_ProfitabilityScore",
    "F002_GrowthScore",
    "F003_ValuationScore",
    "F004_FinancialHealthScore",
    "F005_EarningsQualityScore",
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

    # 第2関門・戦略判定
    min_pullback_setup_score: float = 55.0
    min_breakout_setup_score: float = 55.0
    min_entry_score: float = 60.0
    watch_score_cap: float = 59.0

    # 押し目買い戦略の重み・裏付け加点
    pullback_weight_p001: float = 0.40
    pullback_weight_trend_env: float = 0.25
    pullback_weight_o001: float = 0.15
    pullback_weight_fundamental: float = 0.10
    pullback_weight_volatility_stability: float = 0.10
    double_bottom_bonus_factor: float = 0.10
    double_bottom_bonus_max: float = 10.0
    hammer_bonus_factor: float = 0.05
    hammer_bonus_max: float = 5.0

    # ブレイクアウト戦略の重み
    breakout_weight_p002: float = 0.40
    breakout_weight_v001: float = 0.25
    breakout_weight_o001: float = 0.15
    breakout_weight_trend_env: float = 0.10
    breakout_weight_fundamental: float = 0.10

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
    ) -> List[ScoreResultModel]:
        """
        特徴量セット・パターンセット・OHLCV・指標セットを日付単位で突合し、
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
            results.append(self._evaluate_single_day(fs, ps, ohlcv, ind_set))

        return results

    def _evaluate_single_day(
        self,
        feature_set: FeatureSetModel,
        pattern_set: Optional[PatternSetModel],
        ohlcv: Optional[OhlcvModel],
        indicator_set: Optional[IndicatorSetModel],
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

        # ボラティリティ安定性補助と異常過熱ペナルティ
        volatility_stability = max(
            0.0, min(100.0, 100.0 - max(0.0, vol_score - 50.0) * 1.5)
        )
        penalty_score = 0.0
        if vol_score >= self.config.extreme_volatility_threshold:
            penalty_score += self.config.extreme_volatility_penalty
            reasons.append(
                f"異常ボラティリティ過熱(R001={vol_score:.1f})のため {self.config.extreme_volatility_penalty:.1f} 点を減点しました。"
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

        # 両戦略スコアの算出
        raw_pullback = (
            p001 * self.config.pullback_weight_p001
            + trend_env_score * self.config.pullback_weight_trend_env
            + o001 * self.config.pullback_weight_o001
            + fundamental_score * self.config.pullback_weight_fundamental
            + volatility_stability * self.config.pullback_weight_volatility_stability
            + double_bottom_bonus
            + hammer_bonus
            - penalty_score
        )
        raw_breakout = (
            p002 * self.config.breakout_weight_p002
            + v001 * self.config.breakout_weight_v001
            + o001 * self.config.breakout_weight_o001
            + trend_env_score * self.config.breakout_weight_trend_env
            + fundamental_score * self.config.breakout_weight_fundamental
            - penalty_score
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
                    reasons.append(
                        f"適格戦略の総合スコアがエントリー基準({self.config.min_entry_score:.1f})未満のため見送り(watch)としました（押し目: {pullback_strategy_score:.1f} / ブレイク: {breakout_strategy_score:.1f}）。"
                    )

        sub_scores = {
            "pullback_strategy_score": pullback_strategy_score,
            "breakout_strategy_score": breakout_strategy_score,
            "trend_env_score": trend_env_score,
            "fundamental_score": fundamental_score,
            "penalty_score": penalty_score,
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
            metadata={
                "strategy_type": strategy_type,
                "reasons": reasons,
                "key_levels": key_levels,
                "risk_metrics": risk_metrics,
                "gate1_passed": gate1_passed,
                "volatility_stability": volatility_stability,
                "double_top_confidence": double_top_conf,
            },
        )

    def _decide_strategy_and_score(
        self,
        gate1_passed: bool,
        high_conf_double_top: bool,
        pullback_score: float,
        breakout_score: float,
        p001: float,
        p002: float,
    ) -> Tuple[str, float]:
        """第2関門の適格性判定に基づき、推奨戦略タイプと代表スコアを連動して決定する。"""
        base_ok = gate1_passed and not high_conf_double_top
        pullback_eligible = (
            base_ok
            and (p001 >= self.config.min_pullback_setup_score)
            and (pullback_score >= self.config.min_entry_score)
        )
        breakout_eligible = (
            base_ok
            and (p002 >= self.config.min_breakout_setup_score)
            and (breakout_score >= self.config.min_entry_score)
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
        """ファンダメンタルズ特徴量（F001〜F005）の平均を算出する。全欠損時は中立50.0を返す。"""
        scores = [
            float(feature_map[fid].score)
            for fid in FUNDAMENTAL_FEATURE_IDS
            if fid in feature_map
        ]
        if not scores:
            return 50.0, True
        return sum(scores) / len(scores), False

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
            return float(val)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _calc_deviation_pct(close: Optional[float], level: Optional[float]) -> Optional[float]:
        if close is None or level is None or level == 0:
            return None
        return ((close - level) / level) * 100.0

    @staticmethod
    def _clip_score(val: float) -> float:
        return max(0.0, min(100.0, float(val)))


# レジストリにスコア計算クラスを登録
score_registry.register(StrategyScoreCalculator)
