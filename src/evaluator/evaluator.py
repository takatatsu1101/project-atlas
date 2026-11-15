from datetime import date, datetime, timedelta
import statistics
from typing import Dict, List, Optional, Sequence, Tuple

from src.common.logger import get_logger
from src.data_collector.collector import DataCollector, data_collector
from src.model.data_models import (
    AnalysisResultModel,
    EvaluationSummaryModel,
    ForwardEvaluationItemModel,
    HorizonMetricsModel,
    HorizonSummaryModel,
    OhlcvModel,
)

logger = get_logger(__name__)

_ALLOWED_ENTRY_MODES = ("signal_close", "next_open")


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

    def evaluate(
        self,
        candidates: Sequence[AnalysisResultModel],
        as_of_date: date,
        ohlcv_map: Optional[Dict[str, List[OhlcvModel]]] = None,
        horizons: Sequence[int] = (5, 20, 60),
        entry_price_mode: str = "signal_close",
        eval_end_date: Optional[date] = None,
    ) -> EvaluationSummaryModel:
        """抽出銘柄リスト全体のフォワードリターン検証を実行し、集計サマリーを返す。"""
        resolved_horizons = self._normalize_horizons(horizons)
        self._validate_entry_price_mode(entry_price_mode)

        norm_as_of = self._normalize_date(as_of_date) or as_of_date
        norm_eval_end = self._normalize_date(eval_end_date)
        max_h = max(resolved_horizons)

        items: List[ForwardEvaluationItemModel] = []
        for candidate in candidates:
            symbol = candidate.symbol
            if ohlcv_map is not None and symbol in ohlcv_map:
                ohlcv_data = ohlcv_map[symbol]
            else:
                signal_date = self._normalize_date(candidate.date) or norm_as_of
                # signal_date が休場日の場合でも直前営業日の終値にフォールバックできるよう過去マージンを設ける
                fetch_start = min(signal_date, norm_as_of) - timedelta(days=7)
                fetch_end = norm_eval_end or min(
                    date.today(), norm_as_of + timedelta(days=max_h * 2 + 30)
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
            items.append(item)

        overall_summary = {
            h: self._aggregate_horizon_summary(items, h) for h in resolved_horizons
        }

        strategy_types = list(dict.fromkeys(item.strategy_type for item in items))
        strategy_summary: Dict[str, Dict[int, HorizonSummaryModel]] = {}
        for strat in strategy_types:
            strat_items = [it for it in items if it.strategy_type == strat]
            strategy_summary[strat] = {
                h: self._aggregate_horizon_summary(strat_items, h)
                for h in resolved_horizons
            }

        return EvaluationSummaryModel(
            as_of_date=norm_as_of,
            horizons=resolved_horizons,
            entry_price_mode=entry_price_mode,
            total_candidates=len(items),
            overall_summary=overall_summary,
            strategy_summary=strategy_summary,
            items=items,
        )


Evaluator = ForwardReturnEvaluator
