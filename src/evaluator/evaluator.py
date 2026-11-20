from datetime import date, datetime, timedelta
import math
import statistics
from typing import Dict, List, Optional, Sequence, Tuple

from src.common.logger import get_logger
from src.data_collector.collector import DataCollector, data_collector
from src.model.data_models import (
    AnalysisResultModel,
    BatchBacktestSummaryModel,
    EvaluationSummaryModel,
    FeatureQuantileRowModel,
    ForwardEvaluationItemModel,
    HorizonMetricsModel,
    HorizonSummaryModel,
    OhlcvModel,
)

logger = get_logger(__name__)

_ALLOWED_ENTRY_MODES = ("signal_close", "next_open")
_MARKET_CONTEXT_QUANTILE_SPECS: Tuple[Tuple[str, str, str], ...] = (
    ("rs_score", "MC_RS_Rank", "対TOPIX相対力(RSランク)"),
    ("sector_momentum_score", "MC_SectorMomentum", "33業種モメンタム"),
    ("relative_valuation_score", "MC_RelativeValuation", "業種内相対バリュエーション"),
)


class ForwardReturnEvaluator:
    """スクリーニング抽出銘柄のフォワードリターン・MFE/MAEを検証するクラス"""

    def __init__(self, collector: Optional[DataCollector] = None) -> None:
        self.collector = collector if collector is not None else data_collector

    @staticmethod
    def _normalize_date(value: Optional[date]) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        return value

    @staticmethod
    def _normalize_horizons(horizons: Sequence[int]) -> List[int]:
        if not horizons:
            raise ValueError("horizons は1つ以上の正の整数を指定してください。")
        cleaned: List[int] = []
        for h in horizons:
            if isinstance(h, bool) or not isinstance(h, int) or h <= 0:
                raise ValueError(f"horizons の各要素は正の整数である必要があります: {h}")
            cleaned.append(h)
        return sorted(set(cleaned))

    @staticmethod
    def _validate_entry_price_mode(entry_price_mode: str) -> str:
        if entry_price_mode not in _ALLOWED_ENTRY_MODES:
            raise ValueError(
                f"entry_price_mode は {_ALLOWED_ENTRY_MODES} のいずれかを指定してください: {entry_price_mode}"
            )
        return entry_price_mode

    @staticmethod
    def compute_default_fetch_end(as_of_date: date, horizons: Sequence[int]) -> date:
        """フォワード検証用 OHLCV の既定取得終了日を算出する。"""
        norm_as_of = ForwardReturnEvaluator._normalize_date(as_of_date) or as_of_date
        resolved_horizons = ForwardReturnEvaluator._normalize_horizons(horizons)
        return min(
            date.today(),
            norm_as_of + timedelta(days=max(resolved_horizons) * 2 + 30),
        )

    @classmethod
    def _sort_and_dedup_bars(cls, ohlcv_data: Sequence[OhlcvModel]) -> List[OhlcvModel]:
        """OHLCVデータを正規化済みの日付昇順に整列し、同一日付は後勝ちで重複排除する。"""
        by_date: Dict[date, OhlcvModel] = {}
        for bar in ohlcv_data:
            norm_date = cls._normalize_date(bar.date)
            if norm_date is None:
                continue
            by_date[norm_date] = bar
        return [by_date[d] for d in sorted(by_date.keys())]

    @classmethod
    def _resolve_signal_close_entry(
        cls,
        candidate: AnalysisResultModel,
        sorted_bars: Sequence[OhlcvModel],
        signal_date: date,
    ) -> Optional[float]:
        key_close = (candidate.key_levels or {}).get("close")
        if key_close is not None:
            try:
                val = float(key_close)
                if val > 0.0:
                    return val
            except (TypeError, ValueError):
                pass

        prior_bars = [
            b
            for b in sorted_bars
            if (bar_date := cls._normalize_date(b.date)) is not None
            and bar_date <= signal_date
        ]
        if prior_bars:
            val = float(prior_bars[-1].close)
            if val > 0.0:
                return val
        return None

    def evaluate_candidate(
        self,
        candidate: AnalysisResultModel,
        ohlcv_data: Sequence[OhlcvModel],
        as_of_date: date,
        horizons: Sequence[int] = (5, 20, 60),
        entry_price_mode: str = "signal_close",
    ) -> ForwardEvaluationItemModel:
        """単一銘柄のフォワードリターンおよび MFE / MAE を計算する。"""
        resolved_horizons = self._normalize_horizons(horizons)
        self._validate_entry_price_mode(entry_price_mode)

        norm_as_of = self._normalize_date(as_of_date) or as_of_date
        signal_date = self._normalize_date(candidate.date) or norm_as_of
        sorted_bars = self._sort_and_dedup_bars(ohlcv_data)
        forward_bars = [
            b
            for b in sorted_bars
            if (bar_date := self._normalize_date(b.date)) is not None
            and bar_date > signal_date
        ]

        def _unavailable_map() -> Dict[int, HorizonMetricsModel]:
            return {h: HorizonMetricsModel(horizon_days=h, available=False) for h in resolved_horizons}

        entry_price: Optional[float] = None
        if entry_price_mode == "signal_close":
            entry_price = self._resolve_signal_close_entry(
                candidate, sorted_bars, signal_date
            )
            if entry_price is None or entry_price <= 0.0:
                return ForwardEvaluationItemModel(
                    symbol=candidate.symbol,
                    company_name=candidate.company_name,
                    market=candidate.market,
                    sector=candidate.sector,
                    strategy_type=candidate.strategy_type,
                    rank=candidate.rank,
                    total_score=candidate.total_score,
                    signal_date=signal_date,
                    entry_price=None,
                    horizons=_unavailable_map(),
                    status="missing_entry_price",
                )
            if not forward_bars:
                return ForwardEvaluationItemModel(
                    symbol=candidate.symbol,
                    company_name=candidate.company_name,
                    market=candidate.market,
                    sector=candidate.sector,
                    strategy_type=candidate.strategy_type,
                    rank=candidate.rank,
                    total_score=candidate.total_score,
                    signal_date=signal_date,
                    entry_price=entry_price,
                    horizons=_unavailable_map(),
                    status="no_forward_data",
                )
        else:  # next_open
            if not forward_bars:
                return ForwardEvaluationItemModel(
                    symbol=candidate.symbol,
                    company_name=candidate.company_name,
                    market=candidate.market,
                    sector=candidate.sector,
                    strategy_type=candidate.strategy_type,
                    rank=candidate.rank,
                    total_score=candidate.total_score,
                    signal_date=signal_date,
                    entry_price=None,
                    horizons=_unavailable_map(),
                    status="no_forward_data",
                )
            raw_open = float(forward_bars[0].open)
            if raw_open <= 0.0:
                return ForwardEvaluationItemModel(
                    symbol=candidate.symbol,
                    company_name=candidate.company_name,
                    market=candidate.market,
                    sector=candidate.sector,
                    strategy_type=candidate.strategy_type,
                    rank=candidate.rank,
                    total_score=candidate.total_score,
                    signal_date=signal_date,
                    entry_price=None,
                    horizons=_unavailable_map(),
                    status="missing_entry_price",
                )
            entry_price = raw_open

        horizon_metrics: Dict[int, HorizonMetricsModel] = {}
        for h in resolved_horizons:
            if len(forward_bars) < h:
                horizon_metrics[h] = HorizonMetricsModel(horizon_days=h, available=False)
                continue

            window = forward_bars[:h]
            exit_bar = window[h - 1]
            return_pct = (float(exit_bar.close) - entry_price) / entry_price * 100.0
            mfe_pct = (max(float(b.high) for b in window) - entry_price) / entry_price * 100.0
            mae_pct = (min(float(b.low) for b in window) - entry_price) / entry_price * 100.0
            horizon_metrics[h] = HorizonMetricsModel(
                horizon_days=h,
                available=True,
                target_date=self._normalize_date(exit_bar.date),
                exit_close=float(exit_bar.close),
                return_pct=float(return_pct),
                mfe_pct=float(mfe_pct),
                mae_pct=float(mae_pct),
                is_win=return_pct > 0.0,
            )

        return ForwardEvaluationItemModel(
            symbol=candidate.symbol,
            company_name=candidate.company_name,
            market=candidate.market,
            sector=candidate.sector,
            strategy_type=candidate.strategy_type,
            rank=candidate.rank,
            total_score=candidate.total_score,
            signal_date=signal_date,
            entry_price=entry_price,
            horizons=horizon_metrics,
            status="evaluated",
        )

    @staticmethod
    def _aggregate_horizon_summary(
        items: Sequence[ForwardEvaluationItemModel],
        horizon_days: int,
    ) -> HorizonSummaryModel:
        total_candidates = len(items)
        eval_entries: List[Tuple[str, HorizonMetricsModel]] = [
            (item.symbol, item.horizons[horizon_days])
            for item in items
            if horizon_days in item.horizons
            and item.horizons[horizon_days].available
            and item.horizons[horizon_days].return_pct is not None
        ]
        evaluated_count = len(eval_entries)
        if evaluated_count == 0:
            return HorizonSummaryModel(
                horizon_days=horizon_days,
                total_candidates=total_candidates,
                evaluated_count=0,
                win_count=0,
            )

        returns = [float(m.return_pct) for _, m in eval_entries if m.return_pct is not None]
        mfes = [float(m.mfe_pct) for _, m in eval_entries if m.mfe_pct is not None]
        maes = [float(m.mae_pct) for _, m in eval_entries if m.mae_pct is not None]
        win_count = sum(1 for _, m in eval_entries if m.is_win)

        best_symbol, best_metrics = max(
            eval_entries, key=lambda pair: float(pair[1].return_pct or 0.0)
        )
        worst_symbol, worst_metrics = min(
            eval_entries, key=lambda pair: float(pair[1].return_pct or 0.0)
        )

        return HorizonSummaryModel(
            horizon_days=horizon_days,
            total_candidates=total_candidates,
            evaluated_count=evaluated_count,
            win_count=win_count,
            win_rate_pct=win_count / evaluated_count * 100.0,
            avg_return_pct=statistics.mean(returns),
            median_return_pct=statistics.median(returns),
            avg_mfe_pct=statistics.mean(mfes) if mfes else None,
            avg_mae_pct=statistics.mean(maes) if maes else None,
            best_symbol=best_symbol,
            best_return_pct=best_metrics.return_pct,
            worst_symbol=worst_symbol,
            worst_return_pct=worst_metrics.return_pct,
        )

    def _evaluate_single_candidate(
        self,
        candidate: AnalysisResultModel,
        norm_as_of: date,
        resolved_horizons: Sequence[int],
        entry_price_mode: str,
        ohlcv_map: Optional[Dict[str, List[OhlcvModel]]],
        norm_eval_end: Optional[date],
        eval_cache: Dict[Tuple[str, date], ForwardEvaluationItemModel],
    ) -> ForwardEvaluationItemModel:
        """単一候補を評価する（同一銘柄・基準日の重複評価はキャッシュを再利用する）。"""
        symbol = candidate.symbol
        signal_date = self._normalize_date(candidate.date) or norm_as_of
        cache_key = (symbol, signal_date)
        cached = eval_cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(
                update={
                    "rank": candidate.rank,
                    "strategy_type": candidate.strategy_type,
                    "total_score": candidate.total_score,
                }
            )

        if ohlcv_map is not None and symbol in ohlcv_map:
            ohlcv_data = ohlcv_map[symbol]
            if norm_eval_end is not None:
                ohlcv_data = [
                    b
                    for b in ohlcv_data
                    if (bar_dt := self._normalize_date(b.date)) is not None
                    and bar_dt <= norm_eval_end
                ]
        else:
            # signal_date が休場日の場合でも直前営業日の終値にフォールバックできるよう過去マージンを設ける
            fetch_start = min(signal_date, norm_as_of) - timedelta(days=7)
            fetch_end = norm_eval_end or self.compute_default_fetch_end(
                norm_as_of, resolved_horizons
            )
            if fetch_end < fetch_start:
                ohlcv_data = []
            else:
                try:
                    ohlcv_data = self.collector.collect_ohlcv_data(
                        symbol,
                        fetch_start,
                        fetch_end,
                        as_of_date=fetch_end,
                    )
                except Exception as e:
                    logger.warning(
                        f"{symbol} のフォワードOHLCVデータ取得に失敗しました: {e}"
                    )
                    ohlcv_data = []

        item = self.evaluate_candidate(
            candidate=candidate,
            ohlcv_data=ohlcv_data,
            as_of_date=norm_as_of,
            horizons=resolved_horizons,
            entry_price_mode=entry_price_mode,
        )
        eval_cache[cache_key] = item
        return item

    def evaluate_with_passed(
        self,
        candidates: Sequence[AnalysisResultModel],
        as_of_date: date,
        ohlcv_map: Optional[Dict[str, List[OhlcvModel]]] = None,
        horizons: Sequence[int] = (5, 20, 60),
        entry_price_mode: str = "signal_close",
        eval_end_date: Optional[date] = None,
        passed_candidates: Optional[Sequence[AnalysisResultModel]] = None,
    ) -> Tuple[EvaluationSummaryModel, List[ForwardEvaluationItemModel]]:
        """抽出銘柄および全通過銘柄のフォワードリターン検証を実行し、(サマリー, 全通過評価一覧) を返す。"""
        resolved_horizons = self._normalize_horizons(horizons)
        self._validate_entry_price_mode(entry_price_mode)

        norm_as_of = self._normalize_date(as_of_date) or as_of_date
        norm_eval_end = self._normalize_date(eval_end_date)

        eval_cache: Dict[Tuple[str, date], ForwardEvaluationItemModel] = {}
        items: List[ForwardEvaluationItemModel] = [
            self._evaluate_single_candidate(
                candidate=candidate,
                norm_as_of=norm_as_of,
                resolved_horizons=resolved_horizons,
                entry_price_mode=entry_price_mode,
                ohlcv_map=ohlcv_map,
                norm_eval_end=norm_eval_end,
                eval_cache=eval_cache,
            )
            for candidate in candidates
        ]

        overall_summary, strategy_summary = self._build_summary_maps(
            items, resolved_horizons
        )

        passed_items: List[ForwardEvaluationItemModel] = []
        passed_total_candidates = 0
        passed_overall_summary: Dict[int, HorizonSummaryModel] = {}
        passed_strategy_summary: Dict[str, Dict[int, HorizonSummaryModel]] = {}
        feature_quantile_summary: Dict[str, Dict[int, FeatureQuantileRowModel]] = {}

        if passed_candidates is not None:
            passed_items = [
                self._evaluate_single_candidate(
                    candidate=candidate,
                    norm_as_of=norm_as_of,
                    resolved_horizons=resolved_horizons,
                    entry_price_mode=entry_price_mode,
                    ohlcv_map=ohlcv_map,
                    norm_eval_end=norm_eval_end,
                    eval_cache=eval_cache,
                )
                for candidate in passed_candidates
            ]
            passed_total_candidates = len(passed_items)
            passed_overall_summary, passed_strategy_summary = self._build_summary_maps(
                passed_items, resolved_horizons
            )
            passed_records = list(zip(passed_candidates, passed_items))
            feature_quantile_summary = self.compute_feature_quantiles(
                passed_records, resolved_horizons
            )

        summary = EvaluationSummaryModel(
            as_of_date=norm_as_of,
            horizons=resolved_horizons,
            entry_price_mode=entry_price_mode,
            total_candidates=len(items),
            overall_summary=overall_summary,
            strategy_summary=strategy_summary,
            items=items,
            passed_total_candidates=passed_total_candidates,
            passed_overall_summary=passed_overall_summary,
            passed_strategy_summary=passed_strategy_summary,
            feature_quantile_summary=feature_quantile_summary,
        )
        return summary, passed_items

    def evaluate(
        self,
        candidates: Sequence[AnalysisResultModel],
        as_of_date: date,
        ohlcv_map: Optional[Dict[str, List[OhlcvModel]]] = None,
        horizons: Sequence[int] = (5, 20, 60),
        entry_price_mode: str = "signal_close",
        eval_end_date: Optional[date] = None,
        passed_candidates: Optional[Sequence[AnalysisResultModel]] = None,
    ) -> EvaluationSummaryModel:
        """抽出銘柄リスト全体のフォワードリターン検証を実行し、集計サマリーを返す。"""
        summary, _ = self.evaluate_with_passed(
            candidates=candidates,
            as_of_date=as_of_date,
            ohlcv_map=ohlcv_map,
            horizons=horizons,
            entry_price_mode=entry_price_mode,
            eval_end_date=eval_end_date,
            passed_candidates=passed_candidates,
        )
        return summary

    @staticmethod
    def _calc_quantile_group_stats(
        metrics_list: Sequence[HorizonMetricsModel],
    ) -> Tuple[float, float, Optional[float], Optional[float]]:
        """分位群（上位/下位）の勝率・平均リターン・平均MFE・平均MAEを算出する。"""
        n = len(metrics_list)
        win_count = sum(1 for m in metrics_list if m.is_win)
        win_rate_pct = win_count / n * 100.0
        returns = [float(m.return_pct) for m in metrics_list if m.return_pct is not None]
        mfes = [float(m.mfe_pct) for m in metrics_list if m.mfe_pct is not None]
        maes = [float(m.mae_pct) for m in metrics_list if m.mae_pct is not None]
        avg_return_pct = statistics.mean(returns)
        avg_mfe_pct = statistics.mean(mfes) if mfes else None
        avg_mae_pct = statistics.mean(maes) if maes else None
        return win_rate_pct, avg_return_pct, avg_mfe_pct, avg_mae_pct

    @classmethod
    def compute_feature_quantiles(
        cls,
        passed_records: Sequence[Tuple[AnalysisResultModel, ForwardEvaluationItemModel]],
        resolved_horizons: Sequence[int],
    ) -> Dict[str, Dict[int, FeatureQuantileRowModel]]:
        """
        全通過銘柄の (AnalysisResultModel, ForwardEvaluationItemModel) ペア群から、
        各 feature_id × 各 horizon ごとに上位20% vs 下位20%の分位統計を算出する。
        """
        if not passed_records:
            return {}

        feature_names: Dict[str, str] = {}
        # feature_id -> horizon -> List[(score, symbol, signal_date, HorizonMetricsModel)]
        grouped: Dict[str, Dict[int, List[Tuple[float, str, date, HorizonMetricsModel]]]] = {}

        for candidate, item in passed_records:
            sub_scores = candidate.sub_scores or {}
            for fr in candidate.feature_results:
                fid = fr.feature_id
                if fid not in feature_names or (not feature_names[fid] and fr.feature_name):
                    feature_names[fid] = fr.feature_name or ""
            for sub_key, mc_fid, mc_fname in _MARKET_CONTEXT_QUANTILE_SPECS:
                if sub_key in sub_scores and mc_fid not in feature_names:
                    feature_names[mc_fid] = mc_fname

            if item.status != "evaluated":
                continue

            sig_dt = item.signal_date or cls._normalize_date(candidate.date) or date.min

            for fr in candidate.feature_results:
                score_val = fr.score
                if (
                    isinstance(score_val, bool)
                    or not isinstance(score_val, (int, float))
                    or not math.isfinite(float(score_val))
                ):
                    continue
                score_f = float(score_val)
                fid = fr.feature_id
                fid_map = grouped.setdefault(fid, {})
                for h in resolved_horizons:
                    hm = item.horizons.get(h)
                    if hm is not None and hm.available and hm.return_pct is not None:
                        fid_map.setdefault(h, []).append((score_f, item.symbol, sig_dt, hm))

            for sub_key, mc_fid, _ in _MARKET_CONTEXT_QUANTILE_SPECS:
                if sub_key not in sub_scores:
                    continue
                mc_val = sub_scores.get(sub_key)
                if (
                    isinstance(mc_val, bool)
                    or not isinstance(mc_val, (int, float))
                    or not math.isfinite(float(mc_val))
                ):
                    continue
                mc_f = float(mc_val)
                mc_map = grouped.setdefault(mc_fid, {})
                for h in resolved_horizons:
                    hm = item.horizons.get(h)
                    if hm is not None and hm.available and hm.return_pct is not None:
                        mc_map.setdefault(h, []).append((mc_f, item.symbol, sig_dt, hm))

        result: Dict[str, Dict[int, FeatureQuantileRowModel]] = {}
        for fid in sorted(feature_names.keys()):
            fname = feature_names[fid]
            h_map: Dict[int, FeatureQuantileRowModel] = {}
            fid_samples = grouped.get(fid, {})
            for h in resolved_horizons:
                samples = fid_samples.get(h, [])
                total_samples = len(samples)
                unique_score_count = len({s[0] for s in samples})
                if total_samples < 5:
                    h_map[h] = FeatureQuantileRowModel(
                        feature_id=fid,
                        feature_name=fname,
                        horizon_days=h,
                        total_samples=total_samples,
                        unique_score_count=unique_score_count,
                    )
                    continue

                sorted_samples = sorted(samples, key=lambda x: (x[0], x[1], x[2]))
                k = max(1, total_samples // 5)
                bottom_metrics = [s[3] for s in sorted_samples[:k]]
                top_metrics = [s[3] for s in sorted_samples[-k:]]

                t_win, t_ret, t_mfe, t_mae = cls._calc_quantile_group_stats(top_metrics)
                b_win, b_ret, b_mfe, b_mae = cls._calc_quantile_group_stats(bottom_metrics)

                h_map[h] = FeatureQuantileRowModel(
                    feature_id=fid,
                    feature_name=fname,
                    horizon_days=h,
                    total_samples=total_samples,
                    unique_score_count=unique_score_count,
                    top_count=len(top_metrics),
                    top_win_rate_pct=t_win,
                    top_avg_return_pct=t_ret,
                    top_avg_mfe_pct=t_mfe,
                    top_avg_mae_pct=t_mae,
                    bottom_count=len(bottom_metrics),
                    bottom_win_rate_pct=b_win,
                    bottom_avg_return_pct=b_ret,
                    bottom_avg_mfe_pct=b_mfe,
                    bottom_avg_mae_pct=b_mae,
                    spread_return_pct=t_ret - b_ret,
                    spread_win_rate_pct=t_win - b_win,
                )
            result[fid] = h_map

        return result

    @classmethod
    def _build_summary_maps(
        cls,
        items: Sequence[ForwardEvaluationItemModel],
        resolved_horizons: Sequence[int],
    ) -> Tuple[Dict[int, HorizonSummaryModel], Dict[str, Dict[int, HorizonSummaryModel]]]:
        """候補アイテム一覧から全体集計および戦略別集計マップを構築する。"""
        overall_summary = {
            h: cls._aggregate_horizon_summary(items, h) for h in resolved_horizons
        }

        strategy_types = list(dict.fromkeys(item.strategy_type for item in items))
        strategy_summary: Dict[str, Dict[int, HorizonSummaryModel]] = {}
        for strat in strategy_types:
            strat_items = [it for it in items if it.strategy_type == strat]
            strategy_summary[strat] = {
                h: cls._aggregate_horizon_summary(strat_items, h)
                for h in resolved_horizons
            }
        return overall_summary, strategy_summary

    @classmethod
    def aggregate_batch_summaries(
        cls,
        per_date_summaries: Dict[date, EvaluationSummaryModel],
        horizons: Sequence[int],
        entry_price_mode: str = "signal_close",
        passed_items_all: Optional[Sequence[ForwardEvaluationItemModel]] = None,
        passed_records_all: Optional[
            Sequence[Tuple[AnalysisResultModel, ForwardEvaluationItemModel]]
        ] = None,
    ) -> BatchBacktestSummaryModel:
        """
        複数基準日の EvaluationSummaryModel 群から、全期間・全候補横断の
        BatchBacktestSummaryModel を構築する。
        """
        resolved_horizons = cls._normalize_horizons(horizons)
        cls._validate_entry_price_mode(entry_price_mode)

        normalized_per_date: Dict[date, EvaluationSummaryModel] = {}
        for raw_dt, summary in per_date_summaries.items():
            norm_dt = cls._normalize_date(raw_dt)
            if norm_dt is None:
                continue
            normalized_per_date[norm_dt] = summary

        sorted_dates = sorted(normalized_per_date.keys())
        ordered_summaries = {d: normalized_per_date[d] for d in sorted_dates}

        all_items: List[ForwardEvaluationItemModel] = []
        for d in sorted_dates:
            all_items.extend(ordered_summaries[d].items)

        aggregated_overall_summary, aggregated_strategy_summary = cls._build_summary_maps(
            all_items, resolved_horizons
        )

        resolved_passed_items: Optional[Sequence[ForwardEvaluationItemModel]] = passed_items_all
        if resolved_passed_items is None and passed_records_all is not None:
            resolved_passed_items = [item for _, item in passed_records_all]

        passed_total_candidates = 0
        aggregated_passed_overall_summary: Dict[int, HorizonSummaryModel] = {}
        aggregated_passed_strategy_summary: Dict[str, Dict[int, HorizonSummaryModel]] = {}
        if resolved_passed_items is not None:
            passed_total_candidates = len(resolved_passed_items)
            aggregated_passed_overall_summary, aggregated_passed_strategy_summary = (
                cls._build_summary_maps(resolved_passed_items, resolved_horizons)
            )

        aggregated_feature_quantile_summary: Dict[str, Dict[int, FeatureQuantileRowModel]] = {}
        if passed_records_all is not None:
            aggregated_feature_quantile_summary = cls.compute_feature_quantiles(
                passed_records_all, resolved_horizons
            )

        return BatchBacktestSummaryModel(
            as_of_dates=sorted_dates,
            horizons=resolved_horizons,
            entry_price_mode=entry_price_mode,
            total_dates=len(sorted_dates),
            total_candidates=len(all_items),
            aggregated_overall_summary=aggregated_overall_summary,
            aggregated_strategy_summary=aggregated_strategy_summary,
            per_date_summaries=ordered_summaries,
            passed_total_candidates=passed_total_candidates,
            aggregated_passed_overall_summary=aggregated_passed_overall_summary,
            aggregated_passed_strategy_summary=aggregated_passed_strategy_summary,
            aggregated_feature_quantile_summary=aggregated_feature_quantile_summary,
        )


Evaluator = ForwardReturnEvaluator
