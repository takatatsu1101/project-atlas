import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from src.common.logger import get_logger
from src.model.data_models import (
    AnalysisResultModel,
    FeatureResultModel,
    FeatureSetModel,
    FinancialModel,
    PatternResultModel,
    PatternSetModel,
    ScoreResultModel,
    StockMasterModel,
)

logger = get_logger(__name__)

STRATEGY_LABELS: Dict[str, str] = {
    "pullback": "押し目買い型",
    "breakout": "ブレイクアウト型",
    "watch": "監視",
}

_FINANCIAL_SUMMARY_FIELDS: Tuple[str, ...] = (
    "per",
    "pbr",
    "roe",
    "roa",
    "revenue_growth",
    "net_profit_growth",
    "revenue_growth_3y_avg",
    "net_profit_growth_3y_avg",
    "equity_ratio",
    "eps",
    "bps",
    "revenue",
    "operating_profit",
    "net_profit",
)

_SetLookupTuple = Tuple[
    Dict[Tuple[str, date], Any],
    Dict[str, Any],
    Dict[Tuple[str, date], Any],
    Dict[str, Any],
]


class RankingGenerator:
    """スクリーニング済みスコア結果から総合・戦略別ランキングを生成するクラス"""

    def __init__(self, strict_date_match: bool = True) -> None:
        self.strict_date_match = strict_date_match

    @staticmethod
    def _normalize_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        return value

    @staticmethod
    def _extract_code(symbol: str) -> str:
        return re.sub(r"\.T$", "", symbol, flags=re.IGNORECASE).upper()

    @classmethod
    def _build_master_lookup(
        cls,
        master_map: Optional[Union[List[StockMasterModel], Dict[str, StockMasterModel]]],
    ) -> Dict[str, StockMasterModel]:
        """symbol（例: 7203.T）と code（例: 7203）のどちらでも検索可能な辞書を構築する"""
        lookup: Dict[str, StockMasterModel] = {}
        if not master_map:
            return lookup

        items: Iterable[StockMasterModel]
        if isinstance(master_map, dict):
            for key, stock in master_map.items():
                lookup[key] = stock
            items = master_map.values()
        else:
            items = master_map

        for stock in items:
            lookup[stock.symbol] = stock
            lookup[stock.code] = stock
            lookup[stock.code.upper()] = stock
            lookup[cls._extract_code(stock.symbol)] = stock
        return lookup

    @classmethod
    def _build_financial_lookup(
        cls,
        financial_map: Optional[Dict[str, FinancialModel]],
    ) -> Dict[str, FinancialModel]:
        """symbol と code のどちらでも検索可能な財務データ辞書を構築する"""
        lookup: Dict[str, FinancialModel] = {}
        if not financial_map:
            return lookup

        for key, fin in financial_map.items():
            lookup[key] = fin
            lookup[cls._extract_code(key)] = fin
            if fin.symbol:
                lookup[fin.symbol] = fin
                lookup[cls._extract_code(fin.symbol)] = fin
        return lookup

    @classmethod
    def _build_set_lookup(
        cls,
        sets: Optional[Union[List[Any], Dict[Any, Any]]],
    ) -> _SetLookupTuple:
        """
        FeatureSetModel / PatternSetModel の検索用インデックスを構築する。
        (symbol, date) 完全一致、symbol 最新、(code, date) コード一致、code 最新を返す。
        """
        by_symbol_date: Dict[Tuple[str, date], Any] = {}
        latest_by_symbol: Dict[str, Any] = {}
        by_code_date: Dict[Tuple[str, date], Any] = {}
        latest_by_code: Dict[str, Any] = {}
        if not sets:
            return by_symbol_date, latest_by_symbol, by_code_date, latest_by_code

        def _update_latest(target: Dict[str, Any], key: str, item: Any, norm_dt: Optional[date]) -> None:
            prev = target.get(key)
            prev_dt = cls._normalize_date(prev.date) if prev is not None else None
            if prev is None or (norm_dt is not None and (prev_dt is None or norm_dt >= prev_dt)):
                target[key] = item

        items: Iterable[Any]
        if isinstance(sets, dict):
            for key, item in sets.items():
                norm_item_dt = cls._normalize_date(item.date)
                if isinstance(key, str):
                    if key not in latest_by_symbol:
                        latest_by_symbol[key] = item
                    _update_latest(latest_by_code, cls._extract_code(key), item, norm_item_dt)
                elif isinstance(key, tuple) and len(key) == 2:
                    sym, dt = key
                    norm_dt = cls._normalize_date(dt)
                    if norm_dt is not None:
                        by_symbol_date[(sym, norm_dt)] = item
                        by_code_date[(cls._extract_code(sym), norm_dt)] = item
            items = sets.values()
        else:
            items = sets

        for item in items:
            norm_dt = cls._normalize_date(item.date)
            code = cls._extract_code(item.symbol)
            if norm_dt is not None:
                by_symbol_date[(item.symbol, norm_dt)] = item
                by_code_date[(code, norm_dt)] = item
            _update_latest(latest_by_symbol, item.symbol, item, norm_dt)
            _update_latest(latest_by_code, code, item, norm_dt)

        return by_symbol_date, latest_by_symbol, by_code_date, latest_by_code

    @classmethod
    def _lookup_set(
        cls,
        lookup_tuple: _SetLookupTuple,
        symbol: str,
        norm_date: Optional[date],
        strict_date_match: bool = True,
    ) -> Optional[Any]:
        """
        完全一致 symbol を優先し、無ければ正規化コードで検索する。
        norm_date が指定されている場合、strict_date_match=True なら別日へフォールバックせず None を返す。
        """
        by_symbol_date, latest_by_symbol, by_code_date, latest_by_code = lookup_tuple
        code = cls._extract_code(symbol)
        if norm_date is not None:
            matched = by_symbol_date.get((symbol, norm_date))
            if matched is not None:
                return matched
            matched = by_code_date.get((code, norm_date))
            if matched is not None:
                return matched
            if strict_date_match:
                return None
        return latest_by_symbol.get(symbol) or latest_by_code.get(code)

    @classmethod
    def _lookup_by_symbol(cls, lookup: Dict[str, Any], symbol: str) -> Optional[Any]:
        return (
            lookup.get(symbol)
            or lookup.get(cls._extract_code(symbol))
            or lookup.get(symbol.upper())
        )

    @staticmethod
    def _build_financial_summary(fin: Optional[FinancialModel]) -> Dict[str, Optional[float]]:
        if fin is None:
            return {}
        summary: Dict[str, Optional[float]] = {}
        for field in _FINANCIAL_SUMMARY_FIELDS:
            val = getattr(fin, field, None)
            summary[field] = float(val) if val is not None else None
        return summary

    @staticmethod
    def _get_sort_score(
        score_result: ScoreResultModel, strategy_filter: Optional[str]
    ) -> float:
        sub_scores = score_result.sub_scores or {}
        if strategy_filter == "pullback":
            return float(sub_scores.get("pullback_strategy_score", score_result.total_score))
        if strategy_filter == "breakout":
            return float(sub_scores.get("breakout_strategy_score", score_result.total_score))
        return float(score_result.total_score)

    @staticmethod
    def _build_summary(
        rank: int,
        company_name: str,
        symbol: str,
        strategy_type: str,
        total_score: float,
        reasons: List[str],
        strategy_filter: Optional[str] = None,
        sort_score: Optional[float] = None,
    ) -> str:
        strategy_label = STRATEGY_LABELS.get(strategy_type, strategy_type)
        base = (
            f"{rank}位: {company_name}（{symbol}）[{strategy_label}] "
            f"総合スコア {total_score:.1f}点"
        )
        if (
            strategy_filter in ("pullback", "breakout")
            and sort_score is not None
            and abs(sort_score - total_score) > 1e-6
        ):
            base += f"（{strategy_label}スコア {sort_score:.1f}点）"
        base += "。"
        if reasons:
            base += f" 主な根拠: {reasons[0]}"
        return base

    def _generate_ranking_with_lookups(
        self,
        filtered_score_results: List[ScoreResultModel],
        master_lookup: Dict[str, StockMasterModel],
        financial_lookup: Dict[str, FinancialModel],
        feature_lookup: _SetLookupTuple,
        pattern_lookup: _SetLookupTuple,
        strategy_filter: Optional[str] = None,
        top_n: Optional[int] = None,
        strict_date_match: Optional[bool] = None,
    ) -> List[AnalysisResultModel]:
        """構築済みルックアップ辞書を用いてランキングを生成する共通ヘルパー"""
        if not filtered_score_results:
            return []
        resolved_strict = self.strict_date_match if strict_date_match is None else strict_date_match

        candidates = list(filtered_score_results)
        if strategy_filter is not None:
            candidates = [r for r in candidates if r.strategy_type == strategy_filter]

        if not candidates:
            return []

        sorted_results = sorted(
            candidates,
            key=lambda x: (
                -self._get_sort_score(x, strategy_filter),
                -float((x.sub_scores or {}).get("trend_env_score", 0.0)),
                x.symbol,
            ),
        )

        if top_n is not None:
            sorted_results = sorted_results[: max(0, top_n)]

        analysis_results: List[AnalysisResultModel] = []
        for idx, score_result in enumerate(sorted_results):
            rank = idx + 1
            norm_date = self._normalize_date(score_result.date)
            metadata = score_result.metadata or {}

            master = self._lookup_by_symbol(master_lookup, score_result.symbol)
            company_name = (
                master.name if master and master.name else f"Company_{score_result.symbol}"
            )
            market = master.market if master and master.market else ""
            sector = (
                (master.sector_33 or master.sector_17 or "") if master else ""
            )

            matched_fs = self._lookup_set(
                feature_lookup,
                score_result.symbol,
                norm_date,
                strict_date_match=resolved_strict,
            )
            feature_results: List[FeatureResultModel] = (
                list(matched_fs.results) if matched_fs else []
            )

            matched_ps = self._lookup_set(
                pattern_lookup,
                score_result.symbol,
                norm_date,
                strict_date_match=resolved_strict,
            )
            pattern_results: List[PatternResultModel] = (
                list(matched_ps.results) if matched_ps else []
            )

            fin_model = self._lookup_by_symbol(financial_lookup, score_result.symbol)
            financial_summary = self._build_financial_summary(fin_model)

            reasons = (
                list(score_result.reasons)
                if score_result.reasons
                else list(metadata.get("reasons", []))
            )
            key_levels = (
                dict(score_result.key_levels)
                if score_result.key_levels
                else dict(metadata.get("key_levels", {}))
            )
            risk_metrics = (
                dict(score_result.risk_metrics)
                if score_result.risk_metrics
                else dict(metadata.get("risk_metrics", {}))
            )

            sort_score = self._get_sort_score(score_result, strategy_filter)
            summary = self._build_summary(
                rank=rank,
                company_name=company_name,
                symbol=score_result.symbol,
                strategy_type=score_result.strategy_type,
                total_score=score_result.total_score,
                reasons=reasons,
                strategy_filter=strategy_filter,
                sort_score=sort_score,
            )

            analysis_results.append(
                AnalysisResultModel(
                    symbol=score_result.symbol,
                    company_name=company_name,
                    date=norm_date,
                    market=market,
                    sector=sector,
                    total_score=score_result.total_score,
                    strategy_type=score_result.strategy_type,
                    sub_scores=dict(score_result.sub_scores or {}),
                    reasons=reasons,
                    key_levels=key_levels,
                    risk_metrics=risk_metrics,
                    feature_results=feature_results,
                    pattern_results=pattern_results,
                    financial_summary=financial_summary,
                    rank=rank,
                    summary=summary,
                )
            )

        logger.debug(f"ランキングを生成しました。{len(analysis_results)} 件の分析結果。")
        return analysis_results

    def generate_ranking(
        self,
        filtered_score_results: List[ScoreResultModel],
        master_map: Optional[Union[List[StockMasterModel], Dict[str, StockMasterModel]]] = None,
        feature_sets: Optional[Union[List[FeatureSetModel], Dict[Any, FeatureSetModel]]] = None,
        pattern_sets: Optional[Union[List[PatternSetModel], Dict[Any, PatternSetModel]]] = None,
        financial_map: Optional[Dict[str, FinancialModel]] = None,
        strategy_filter: Optional[str] = None,
        top_n: Optional[int] = None,
        strict_date_match: Optional[bool] = None,
    ) -> List[AnalysisResultModel]:
        """
        フィルタリングされたスコア結果からランキングを生成し、最終分析結果のリストを返す。
        - strategy_filter 指定時は該当戦略のみ抽出し、対応する戦略スコアでソートする。
        - タイブレークは trend_env_score 降順 -> symbol 昇順で決定論的にソートする。
        """
        if not filtered_score_results:
            return []
        if strategy_filter is not None and not any(
            r.strategy_type == strategy_filter for r in filtered_score_results
        ):
            return []

        master_lookup = self._build_master_lookup(master_map)
        financial_lookup = self._build_financial_lookup(financial_map)
        feature_lookup = self._build_set_lookup(feature_sets)
        pattern_lookup = self._build_set_lookup(pattern_sets)

        return self._generate_ranking_with_lookups(
            filtered_score_results,
            master_lookup=master_lookup,
            financial_lookup=financial_lookup,
            feature_lookup=feature_lookup,
            pattern_lookup=pattern_lookup,
            strategy_filter=strategy_filter,
            top_n=top_n,
            strict_date_match=strict_date_match,
        )

    def generate_strategy_rankings(
        self,
        filtered_score_results: List[ScoreResultModel],
        master_map: Optional[Union[List[StockMasterModel], Dict[str, StockMasterModel]]] = None,
        feature_sets: Optional[Union[List[FeatureSetModel], Dict[Any, FeatureSetModel]]] = None,
        pattern_sets: Optional[Union[List[PatternSetModel], Dict[Any, PatternSetModel]]] = None,
        financial_map: Optional[Dict[str, FinancialModel]] = None,
        overall_top_n: Optional[int] = None,
        strategy_top_n: Optional[int] = None,
        strict_date_match: Optional[bool] = None,
    ) -> Dict[str, List[AnalysisResultModel]]:
        """
        総合ランキング（overall）、押し目買い型（pullback）、ブレイクアウト型（breakout）の
        3種類のランキング辞書を生成して返す。
        """
        if not filtered_score_results:
            return {"overall": [], "pullback": [], "breakout": []}

        # 3種類のランキング生成でルックアップ辞書を1回だけ構築して使い回す
        master_lookup = self._build_master_lookup(master_map)
        financial_lookup = self._build_financial_lookup(financial_map)
        feature_lookup = self._build_set_lookup(feature_sets)
        pattern_lookup = self._build_set_lookup(pattern_sets)

        strategy_specs = (
            ("overall", None, overall_top_n),
            ("pullback", "pullback", strategy_top_n),
            ("breakout", "breakout", strategy_top_n),
        )
        return {
            key: self._generate_ranking_with_lookups(
                filtered_score_results,
                master_lookup=master_lookup,
                financial_lookup=financial_lookup,
                feature_lookup=feature_lookup,
                pattern_lookup=pattern_lookup,
                strategy_filter=strat_filter,
                top_n=top_n,
                strict_date_match=strict_date_match,
            )
            for key, strat_filter, top_n in strategy_specs
        }


# モジュールレベルでインスタンス化
ranking_generator = RankingGenerator()


def generate_ranking(
    filtered_score_results: List[ScoreResultModel],
    master_map: Optional[Union[List[StockMasterModel], Dict[str, StockMasterModel]]] = None,
    feature_sets: Optional[Union[List[FeatureSetModel], Dict[Any, FeatureSetModel]]] = None,
    pattern_sets: Optional[Union[List[PatternSetModel], Dict[Any, PatternSetModel]]] = None,
    financial_map: Optional[Dict[str, FinancialModel]] = None,
    strategy_filter: Optional[str] = None,
    top_n: Optional[int] = None,
    strict_date_match: Optional[bool] = None,
) -> List[AnalysisResultModel]:
    return ranking_generator.generate_ranking(
        filtered_score_results,
        master_map=master_map,
        feature_sets=feature_sets,
        pattern_sets=pattern_sets,
        financial_map=financial_map,
        strategy_filter=strategy_filter,
        top_n=top_n,
        strict_date_match=strict_date_match,
    )


def generate_strategy_rankings(
    filtered_score_results: List[ScoreResultModel],
    master_map: Optional[Union[List[StockMasterModel], Dict[str, StockMasterModel]]] = None,
    feature_sets: Optional[Union[List[FeatureSetModel], Dict[Any, FeatureSetModel]]] = None,
    pattern_sets: Optional[Union[List[PatternSetModel], Dict[Any, PatternSetModel]]] = None,
    financial_map: Optional[Dict[str, FinancialModel]] = None,
    overall_top_n: Optional[int] = None,
    strategy_top_n: Optional[int] = None,
    strict_date_match: Optional[bool] = None,
) -> Dict[str, List[AnalysisResultModel]]:
    return ranking_generator.generate_strategy_rankings(
        filtered_score_results,
        master_map=master_map,
        feature_sets=feature_sets,
        pattern_sets=pattern_sets,
        financial_map=financial_map,
        overall_top_n=overall_top_n,
        strategy_top_n=strategy_top_n,
        strict_date_match=strict_date_match,
    )
