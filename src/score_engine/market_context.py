"""
ユニバース横断コンテキスト（対TOPIX相対力・33業種モメンタム・業種内相対バリュエーション・地合いレジーム）算出モジュール
"""

from datetime import date, datetime
import math
import re
import statistics
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from pydantic import BaseModel, field_validator, model_validator

from src.common.logger import get_logger
from src.model.data_models import (
    BenchmarkMetricsModel,
    FinancialModel,
    IndicatorSetModel,
    MarketContextModel,
    OhlcvModel,
    SectorMetricsModel,
    StockMasterModel,
    SymbolMarketMetricsModel,
    SymbolMarketSnapshot,
)

logger = get_logger(__name__)

# 後方互換・呼び出し簡便化用のエイリアス
MarketContext = MarketContextModel


class MarketContextConfig(BaseModel):
    """ユニバース横断コンテキスト（MarketContext）の設定モデル"""

    enabled: bool = True
    benchmark_symbol: str = "1306.T"
    min_universe_size: int = 20
    min_sector_size: int = 5
    rs_lookback_short: int = 20
    rs_lookback_medium: int = 60
    rs_lookback_long: int = 120
    rs_weight_short: float = 0.25
    rs_weight_medium: float = 0.45
    rs_weight_long: float = 0.30
    breadth_severe_bearish_threshold: float = 0.35
    breadth_bearish_threshold: float = 0.40
    breadth_bullish_threshold: float = 0.60
    breakout_bearish_threshold_delta: float = 8.0
    breakout_bearish_score_penalty: float = 6.0
    pullback_rs_positive_factor: float = 0.3
    rs_adjustment_max: float = 4.0
    sector_momentum_adjustment_max: float = 4.0
    relative_valuation_adjustment_max: float = 4.0
    total_adjustment_cap: float = 8.0

    @field_validator("benchmark_symbol")
    @classmethod
    def _validate_benchmark_symbol(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("benchmark_symbol は空にできません。")
        return cleaned

    @field_validator(
        "min_universe_size",
        "rs_lookback_short",
        "rs_lookback_medium",
        "rs_lookback_long",
        mode="before",
    )
    @classmethod
    def _validate_positive_int(cls, value: Any, info: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{info.field_name} は 1 以上の整数を指定してください: {value}")
        return value

    @field_validator("min_sector_size", mode="before")
    @classmethod
    def _validate_min_sector_size(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 2:
            raise ValueError(f"min_sector_size は 2 以上の整数を指定してください: {value}")
        return value

    @field_validator(
        "rs_weight_short",
        "rs_weight_medium",
        "rs_weight_long",
        "breakout_bearish_threshold_delta",
        "breakout_bearish_score_penalty",
        "rs_adjustment_max",
        "sector_momentum_adjustment_max",
        "relative_valuation_adjustment_max",
        "total_adjustment_cap",
        mode="before",
    )
    @classmethod
    def _validate_non_negative_float(cls, value: Any, info: Any) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{info.field_name} に真偽値は指定できません: {value}")
        try:
            fval = float(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{info.field_name} は数値を指定してください: {value}") from e
        if not math.isfinite(fval) or fval < 0.0:
            raise ValueError(f"{info.field_name} は 0 以上の有限数である必要があります: {value}")
        return fval

    @field_validator(
        "breadth_severe_bearish_threshold",
        "breadth_bearish_threshold",
        "breadth_bullish_threshold",
        "pullback_rs_positive_factor",
        mode="before",
    )
    @classmethod
    def _validate_ratio(cls, value: Any, info: Any) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{info.field_name} に真偽値は指定できません: {value}")
        try:
            fval = float(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{info.field_name} は数値を指定してください: {value}") from e
        if not math.isfinite(fval) or fval < 0.0 or fval > 1.0:
            raise ValueError(f"{info.field_name} は 0.0〜1.0 の範囲で指定してください: {value}")
        return fval

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> "MarketContextConfig":
        if (self.rs_weight_short + self.rs_weight_medium + self.rs_weight_long) <= 0.0:
            raise ValueError(
                "rs_weight_short, rs_weight_medium, rs_weight_long の合計は 0 より大きい必要があります。"
            )
        if self.breadth_severe_bearish_threshold > self.breadth_bearish_threshold:
            raise ValueError(
                "breadth_severe_bearish_threshold は breadth_bearish_threshold 以下である必要があります。"
            )
        if self.breadth_bearish_threshold > self.breadth_bullish_threshold:
            raise ValueError(
                "breadth_bearish_threshold は breadth_bullish_threshold 以下である必要があります。"
            )
        return self


def _normalize_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _to_optional_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def _clip(value: float, low: float, high: float) -> float:
    fval = _to_optional_float(value)
    if fval is None:
        return 0.0 if (low <= 0.0 <= high) else 0.5 * (low + high)
    return max(low, min(high, fval))


def _extract_code(symbol: str) -> str:
    return re.sub(r"\.T$", "", symbol, flags=re.IGNORECASE).upper()


def _build_master_lookup(
    master_map: Optional[
        Union[Sequence[StockMasterModel], Mapping[str, StockMasterModel]]
    ],
) -> Dict[str, StockMasterModel]:
    lookup: Dict[str, StockMasterModel] = {}
    if not master_map:
        return lookup

    items: Iterable[StockMasterModel]
    if isinstance(master_map, Mapping):
        for key, stock in master_map.items():
            lookup[key] = stock
        items = master_map.values()
    else:
        items = master_map

    for stock in items:
        lookup[stock.symbol] = stock
        lookup[stock.code] = stock
        lookup[stock.code.upper()] = stock
        lookup[_extract_code(stock.symbol)] = stock
    return lookup


def _resolve_sector_33(
    symbol: str, master_lookup: Dict[str, StockMasterModel]
) -> Optional[str]:
    master = (
        master_lookup.get(symbol)
        or master_lookup.get(_extract_code(symbol))
        or master_lookup.get(symbol.upper())
    )
    if master is None or master.sector_33 is None:
        return None
    sec = str(master.sector_33).strip()
    if not sec or sec == "-" or sec.lower() in ("nan", "none"):
        return None
    return sec


def _compute_return_pct(
    bars: Sequence[OhlcvModel], lookback: int
) -> Optional[float]:
    if len(bars) <= lookback:
        return None
    latest_close = _to_optional_float(bars[-1].close)
    prev_close = _to_optional_float(bars[-1 - lookback].close)
    if latest_close is None or prev_close is None or prev_close <= 0.0 or latest_close <= 0.0:
        return None
    return (latest_close / prev_close - 1.0) * 100.0


def _compute_sma(bars: Sequence[OhlcvModel], window: int) -> Optional[float]:
    if len(bars) < window or window <= 0:
        return None
    vals: List[float] = []
    for bar in bars[-window:]:
        c = _to_optional_float(bar.close)
        if c is None:
            return None
        vals.append(c)
    return sum(vals) / window


def _compute_midrank_percentiles(
    items: Sequence[Tuple[str, float]],
) -> Dict[str, float]:
    """
    (key, value) リストに対し、タイ値を考慮した中点順位パーセンタイル（0.0〜100.0）を算出する。
    要素が1件のみ、または全要素が同値の場合は 50.0 を返す。
    """
    n = len(items)
    if n == 0:
        return {}
    if n == 1:
        return {items[0][0]: 50.0}

    sorted_items = sorted(items, key=lambda x: (x[1], x[0]))
    percentiles: Dict[str, float] = {}
    i = 0
    while i < n:
        j = i + 1
        while j < n and sorted_items[j][1] == sorted_items[i][1]:
            j += 1
        # 同値グループ [i, j - 1] に平均順位を与える
        avg_rank = (i + (j - 1)) / 2.0
        pct = (avg_rank / (n - 1)) * 100.0
        for k in range(i, j):
            percentiles[sorted_items[k][0]] = pct
        i = j
    return percentiles


def extract_symbol_market_snapshot(
    symbol: str,
    ohlcv_slice: Sequence[OhlcvModel],
    indicator_slice: Optional[Sequence[IndicatorSetModel]] = None,
    financial_data: Optional[FinancialModel] = None,
    config: Optional[MarketContextConfig] = None,
) -> SymbolMarketSnapshot:
    """
    単一銘柄の基準日以前OHLCV・指標・財務データから軽量スナップショットを抽出する。
    ワーカープロセス内での単一銘柄処理の末尾で生成し、親プロセスでの横断集計に受け渡す用途。
    """
    cfg = config or MarketContextConfig()
    if not ohlcv_slice:
        return SymbolMarketSnapshot(
            symbol=symbol,
            per=_to_optional_float(financial_data.per) if financial_data else None,
            pbr=_to_optional_float(financial_data.pbr) if financial_data else None,
            roe=_to_optional_float(financial_data.roe) if financial_data else None,
        )

    # 昇順でなければ日付順に整列（通常は既に昇順）
    is_sorted = True
    prev_dt: Optional[date] = None
    for bar in ohlcv_slice:
        cur_dt = _normalize_date(bar.date)
        if cur_dt is None or (prev_dt is not None and cur_dt < prev_dt):
            is_sorted = False
            break
        prev_dt = cur_dt

    bars: Sequence[OhlcvModel]
    if is_sorted:
        bars = ohlcv_slice
    else:
        bars = sorted(
            [b for b in ohlcv_slice if _normalize_date(b.date) is not None],
            key=lambda b: _normalize_date(b.date) or date.min,
        )
        if not bars:
            return SymbolMarketSnapshot(symbol=symbol)

    latest_bar = bars[-1]
    bar_date = _normalize_date(latest_bar.date)
    close = _to_optional_float(latest_bar.close)

    sma25: Optional[float] = None
    if indicator_slice:
        last_ind = indicator_slice[-1]
        if _normalize_date(last_ind.date) == bar_date:
            sma25 = _to_optional_float(last_ind.indicators.get("SMA25"))
        else:
            for ind in reversed(indicator_slice):
                if _normalize_date(ind.date) == bar_date:
                    sma25 = _to_optional_float(ind.indicators.get("SMA25"))
                    break
    if sma25 is None:
        sma25 = _compute_sma(bars, 25)

    above_sma25: Optional[bool] = None
    if close is not None and sma25 is not None and sma25 > 0.0:
        above_sma25 = bool(close > sma25)

    return_20d = _compute_return_pct(bars, cfg.rs_lookback_short)
    return_60d = _compute_return_pct(bars, cfg.rs_lookback_medium)
    return_120d = _compute_return_pct(bars, cfg.rs_lookback_long)

    return SymbolMarketSnapshot(
        symbol=symbol,
        bar_date=bar_date,
        close=close,
        sma25=sma25,
        above_sma25=above_sma25,
        return_20d=return_20d,
        return_60d=return_60d,
        return_120d=return_120d,
        per=_to_optional_float(financial_data.per) if financial_data else None,
        pbr=_to_optional_float(financial_data.pbr) if financial_data else None,
        roe=_to_optional_float(financial_data.roe) if financial_data else None,
    )


def compute_benchmark_metrics(
    benchmark_ohlcv: Optional[Sequence[OhlcvModel]],
    as_of_date: date,
    config: Optional[MarketContextConfig] = None,
) -> BenchmarkMetricsModel:
    """
    ベンチマーク銘柄（デフォルト 1306.T）の OHLCV から基準日以前の指標を厳密分離して算出する。
    """
    cfg = config or MarketContextConfig()
    norm_as_of = _normalize_date(as_of_date) or as_of_date

    if not benchmark_ohlcv:
        return BenchmarkMetricsModel(symbol=cfg.benchmark_symbol, available=False)

    # 先読みバイアス遮断: as_of_date 以前のバーのみ残し、同一日付は後勝ち重複排除
    by_date: Dict[date, OhlcvModel] = {}
    for bar in benchmark_ohlcv:
        dt = _normalize_date(bar.date)
        if dt is None or dt > norm_as_of:
            continue
        by_date[dt] = bar

    if not by_date:
        return BenchmarkMetricsModel(symbol=cfg.benchmark_symbol, available=False)

    sorted_dates = sorted(by_date.keys())
    sorted_bars = [by_date[d] for d in sorted_dates]

    latest_date = sorted_dates[-1]
    latest_close = _to_optional_float(sorted_bars[-1].close)
    if latest_close is None or latest_close <= 0.0:
        return BenchmarkMetricsModel(symbol=cfg.benchmark_symbol, available=False)

    sma25 = _compute_sma(sorted_bars, 25)
    sma75 = _compute_sma(sorted_bars, 75)
    above_sma25 = (
        bool(latest_close >= sma25)
        if (sma25 is not None and sma25 > 0.0)
        else None
    )
    above_sma75 = (
        bool(latest_close >= sma75)
        if (sma75 is not None and sma75 > 0.0)
        else None
    )

    return BenchmarkMetricsModel(
        symbol=cfg.benchmark_symbol,
        available=True,
        bar_date=latest_date,
        close=latest_close,
        sma25=sma25,
        sma75=sma75,
        above_sma25=above_sma25,
        above_sma75=above_sma75,
        return_20d=_compute_return_pct(sorted_bars, cfg.rs_lookback_short),
        return_60d=_compute_return_pct(sorted_bars, cfg.rs_lookback_medium),
        return_120d=_compute_return_pct(sorted_bars, cfg.rs_lookback_long),
    )


def _compute_sector_valuation_z_maps(
    sector_snaps: Sequence[SymbolMarketSnapshot],
    min_sector_size: int,
) -> Dict[str, float]:
    """
    同一33業種内の銘柄群に対し、PER(対数・低いほど良)・PBR(対数・低いほど良)・ROE(高いほど良)の
    標準化 Z スコア平均（[-2.5, +2.5] クリップ）を算出する。
    """
    # (field_values: Dict[symbol, transformed_val], higher_is_better: bool)
    metric_specs: List[Tuple[Dict[str, float], bool]] = []

    per_vals: Dict[str, float] = {}
    pbr_vals: Dict[str, float] = {}
    roe_vals: Dict[str, float] = {}
    for snap in sector_snaps:
        if snap.per is not None and 0.0 < snap.per <= 200.0:
            per_vals[snap.symbol] = math.log(snap.per)
        if snap.pbr is not None and 0.0 < snap.pbr <= 50.0:
            pbr_vals[snap.symbol] = math.log(snap.pbr)
        if snap.roe is not None and -50.0 <= snap.roe <= 100.0:
            roe_vals[snap.symbol] = snap.roe

    metric_specs.append((per_vals, False))
    metric_specs.append((pbr_vals, False))
    metric_specs.append((roe_vals, True))

    per_symbol_zs: Dict[str, List[float]] = {}
    for val_map, higher_is_better in metric_specs:
        if len(val_map) < min_sector_size:
            continue
        vals = list(val_map.values())
        mean_val = statistics.fmean(vals)
        std_val = statistics.pstdev(vals)
        if not math.isfinite(std_val) or std_val < 1e-6:
            continue
        sign = 1.0 if higher_is_better else -1.0
        for sym, v in val_map.items():
            z = _clip(sign * (v - mean_val) / std_val, -2.5, 2.5)
            per_symbol_zs.setdefault(sym, []).append(z)

    return {
        sym: _clip(statistics.fmean(z_list), -2.5, 2.5)
        for sym, z_list in per_symbol_zs.items()
        if z_list
    }


def build_market_context(
    as_of_date: date,
    snapshots: Sequence[SymbolMarketSnapshot],
    master_map: Optional[
        Union[Sequence[StockMasterModel], Mapping[str, StockMasterModel]]
    ] = None,
    benchmark_ohlcv: Optional[Sequence[OhlcvModel]] = None,
    config: Optional[MarketContextConfig] = None,
) -> MarketContextModel:
    """
    基準日断面のスナップショット群・銘柄マスタ・ベンチマークOHLCVから
    読み取り専用の MarketContextModel を構築する（親プロセス側で1回実行）。
    """
    cfg = config or MarketContextConfig()
    norm_as_of = _normalize_date(as_of_date) or as_of_date
    benchmark = compute_benchmark_metrics(benchmark_ohlcv, norm_as_of, cfg)

    if not cfg.enabled:
        return MarketContextModel(
            as_of_date=norm_as_of,
            is_active=False,
            inactive_reason="disabled",
            universe_size=len(snapshots),
            regime="unknown",
            breakout_threshold_delta=0.0,
            benchmark=benchmark,
        )

    # 未来日スナップショットの混入・非有限数値(NaN/inf)の混入を防御し、
    # symbol 単位で後勝ちユニーク化・決定性のためソート
    dedup_snaps: Dict[str, SymbolMarketSnapshot] = {}
    for snap in snapshots:
        snap_dt = _normalize_date(snap.bar_date)
        if snap_dt is not None and snap_dt > norm_as_of:
            logger.warning(
                f"未来日のスナップショットを除外しました [{snap.symbol}]: "
                f"bar_date={snap_dt} > as_of_date={norm_as_of}"
            )
            continue
        clean_close = _to_optional_float(snap.close)
        if clean_close is None:
            continue
        clean_sma25 = _to_optional_float(snap.sma25)
        clean_above_sma25 = (
            None
            if (snap.sma25 is not None and clean_sma25 is None)
            else snap.above_sma25
        )
        dedup_snaps[snap.symbol] = snap.model_copy(
            update={
                "bar_date": snap_dt,
                "close": clean_close,
                "sma25": clean_sma25,
                "above_sma25": clean_above_sma25,
                "return_20d": _to_optional_float(snap.return_20d),
                "return_60d": _to_optional_float(snap.return_60d),
                "return_120d": _to_optional_float(snap.return_120d),
                "per": _to_optional_float(snap.per),
                "pbr": _to_optional_float(snap.pbr),
                "roe": _to_optional_float(snap.roe),
            }
        )

    valid_snaps = [dedup_snaps[sym] for sym in sorted(dedup_snaps.keys())]
    universe_size = len(valid_snaps)

    if universe_size < cfg.min_universe_size:
        return MarketContextModel(
            as_of_date=norm_as_of,
            is_active=False,
            inactive_reason="insufficient_universe",
            universe_size=universe_size,
            regime="unknown",
            breakout_threshold_delta=0.0,
            benchmark=benchmark,
        )

    # 1. ユニバース中央値リターン（ベンチマーク欠損時の代替基準兼レジームフォールバック）
    r20_all = [s.return_20d for s in valid_snaps if s.return_20d is not None]
    r60_all = [s.return_60d for s in valid_snaps if s.return_60d is not None]
    r120_all = [s.return_120d for s in valid_snaps if s.return_120d is not None]

    med_r20 = statistics.median(r20_all) if r20_all else None
    med_r60 = statistics.median(r60_all) if r60_all else None
    med_r120 = statistics.median(r120_all) if r120_all else None

    # 2. Market Breadth ＆ 地合いレジーム判定
    sma25_flags = [s.above_sma25 for s in valid_snaps if s.above_sma25 is not None]
    valid_sma25_count = len(sma25_flags)
    above_sma25_count = sum(1 for flag in sma25_flags if flag)

    breadth_ratio: Optional[float] = None
    regime = "unknown"
    breakout_threshold_delta = 0.0
    breakout_score_penalty = 0.0

    if valid_sma25_count >= cfg.min_universe_size:
        breadth_ratio = above_sma25_count / valid_sma25_count
        if benchmark.above_sma25 is not None:
            is_market_weak = benchmark.above_sma25 is False
            is_market_strong = benchmark.above_sma25 is True
        else:
            is_market_weak = med_r20 is not None and med_r20 < 0.0
            is_market_strong = med_r20 is not None and med_r20 > 0.0

        is_severe_breadth_bearish = breadth_ratio < cfg.breadth_severe_bearish_threshold
        if (breadth_ratio < cfg.breadth_bearish_threshold and is_market_weak) or is_severe_breadth_bearish:
            regime = "bearish"
            breakout_threshold_delta = cfg.breakout_bearish_threshold_delta
            breakout_score_penalty = cfg.breakout_bearish_score_penalty
        elif breadth_ratio >= cfg.breadth_bullish_threshold and is_market_strong:
            regime = "bullish"
        else:
            regime = "neutral"

    # 3. 対 TOPIX 相対力（RS）超過リターン＆ユニバース内パーセンタイル順位
    ref_20d = benchmark.return_20d if benchmark.return_20d is not None else med_r20
    ref_60d = benchmark.return_60d if benchmark.return_60d is not None else med_r60
    ref_120d = benchmark.return_120d if benchmark.return_120d is not None else med_r120

    excess_by_sym: Dict[str, Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]] = {}
    composite_items: List[Tuple[str, float]] = []

    for snap in valid_snaps:
        ex20 = (
            (snap.return_20d - ref_20d)
            if (snap.return_20d is not None and ref_20d is not None)
            else None
        )
        ex60 = (
            (snap.return_60d - ref_60d)
            if (snap.return_60d is not None and ref_60d is not None)
            else None
        )
        ex120 = (
            (snap.return_120d - ref_120d)
            if (snap.return_120d is not None and ref_120d is not None)
            else None
        )

        weighted_sum = 0.0
        weight_total = 0.0
        for ex_val, w in (
            (ex20, cfg.rs_weight_short),
            (ex60, cfg.rs_weight_medium),
            (ex120, cfg.rs_weight_long),
        ):
            if ex_val is not None and w > 0.0:
                weighted_sum += ex_val * w
                weight_total += w

        comp_ex = (weighted_sum / weight_total) if weight_total > 0.0 else None
        excess_by_sym[snap.symbol] = (ex20, ex60, ex120, comp_ex)
        if comp_ex is not None:
            composite_items.append((snap.symbol, comp_ex))

    rs_percentiles: Dict[str, float] = {}
    if len(composite_items) >= cfg.min_universe_size:
        rs_percentiles = _compute_midrank_percentiles(composite_items)

    # 4. 33業種モメンタム＆業種内相対バリュエーション
    master_lookup = _build_master_lookup(master_map)
    symbol_sector_map: Dict[str, Optional[str]] = {}
    snaps_by_sector: Dict[str, List[SymbolMarketSnapshot]] = {}
    for snap in valid_snaps:
        sec = _resolve_sector_33(snap.symbol, master_lookup)
        symbol_sector_map[snap.symbol] = sec
        if sec is not None:
            snaps_by_sector.setdefault(sec, []).append(snap)

    sector_raw_stats: Dict[str, Dict[str, Any]] = {}
    sufficient_sector_returns: List[Tuple[str, float]] = []
    for sec in sorted(snaps_by_sector.keys()):
        sec_snaps = snaps_by_sector[sec]
        member_count = len(sec_snaps)
        clipped_r20 = [
            _clip(s.return_20d, -50.0, 100.0)
            for s in sec_snaps
            if s.return_20d is not None
        ]
        sma_flags = [s.above_sma25 for s in sec_snaps if s.above_sma25 is not None]
        avg_r20 = statistics.fmean(clipped_r20) if clipped_r20 else None
        above_ratio = (
            sum(1 for f in sma_flags if f) / len(sma_flags)
            if sma_flags
            else None
        )
        is_sufficient = (
            member_count >= cfg.min_sector_size
            and len(clipped_r20) >= cfg.min_sector_size
            and len(sma_flags) >= cfg.min_sector_size
        )
        sector_raw_stats[sec] = {
            "member_count": member_count,
            "is_sufficient": is_sufficient,
            "avg_return_20d": avg_r20,
            "above_sma25_ratio": above_ratio,
        }
        if is_sufficient and avg_r20 is not None:
            sufficient_sector_returns.append((sec, avg_r20))

    sector_return_pcts = _compute_midrank_percentiles(sufficient_sector_returns)
    sector_metrics: Dict[str, SectorMetricsModel] = {}
    for sec, stats in sector_raw_stats.items():
        if stats["is_sufficient"] and sec in sector_return_pcts and stats["above_sma25_ratio"] is not None:
            sec_ret_pct = sector_return_pcts[sec]
            sec_mom_score = 0.5 * sec_ret_pct + 0.5 * (stats["above_sma25_ratio"] * 100.0)
        else:
            sec_ret_pct = None
            sec_mom_score = None
        sector_metrics[sec] = SectorMetricsModel(
            sector_33=sec,
            member_count=stats["member_count"],
            is_sufficient=stats["is_sufficient"],
            avg_return_20d=stats["avg_return_20d"],
            above_sma25_ratio=stats["above_sma25_ratio"],
            sector_return_percentile=sec_ret_pct,
            sector_momentum_score=sec_mom_score,
        )

    rel_val_z_by_sym: Dict[str, float] = {}
    for sec, sec_snaps in snaps_by_sector.items():
        if len(sec_snaps) < cfg.min_sector_size:
            continue
        rel_val_z_by_sym.update(
            _compute_sector_valuation_z_maps(sec_snaps, cfg.min_sector_size)
        )

    # 5. 銘柄別 MarketMetrics と補正点の組み立て
    symbol_metrics: Dict[str, SymbolMarketMetricsModel] = {}
    for snap in valid_snaps:
        sym = snap.symbol
        sec = symbol_sector_map.get(sym)
        ex20, ex60, ex120, comp_ex = excess_by_sym[sym]

        rs_pct = rs_percentiles.get(sym)
        rs_adj = (
            ((rs_pct - 50.0) / 50.0) * cfg.rs_adjustment_max
            if rs_pct is not None
            else 0.0
        )

        sec_model = sector_metrics.get(sec) if sec is not None else None
        sec_mom_score = sec_model.sector_momentum_score if sec_model is not None else None
        sec_adj = (
            ((sec_mom_score - 50.0) / 50.0) * cfg.sector_momentum_adjustment_max
            if sec_mom_score is not None
            else 0.0
        )

        rel_z = rel_val_z_by_sym.get(sym)
        rel_val_score = (50.0 + (rel_z / 2.5) * 50.0) if rel_z is not None else None
        rel_val_adj = (
            (rel_z / 2.5) * cfg.relative_valuation_adjustment_max
            if rel_z is not None
            else 0.0
        )

        rs_adj_pullback = (
            rs_adj * cfg.pullback_rs_positive_factor if rs_adj > 0.0 else rs_adj
        )
        pullback_adj = _clip(
            rs_adj_pullback + sec_adj + rel_val_adj,
            -cfg.total_adjustment_cap,
            cfg.total_adjustment_cap,
        )
        breakout_adj = _clip(
            rs_adj + sec_adj + rel_val_adj,
            -cfg.total_adjustment_cap,
            cfg.total_adjustment_cap,
        )

        symbol_metrics[sym] = SymbolMarketMetricsModel(
            symbol=sym,
            bar_date=_normalize_date(snap.bar_date),
            sector_33=sec,
            return_20d=snap.return_20d,
            return_60d=snap.return_60d,
            return_120d=snap.return_120d,
            excess_return_20d=ex20,
            excess_return_60d=ex60,
            excess_return_120d=ex120,
            composite_excess_return=comp_ex,
            rs_percentile=rs_pct,
            sector_momentum_score=sec_mom_score,
            relative_valuation_z=rel_z,
            relative_valuation_score=rel_val_score,
            rs_adjustment=rs_adj,
            sector_momentum_adjustment=sec_adj,
            relative_valuation_adjustment=rel_val_adj,
            pullback_adjustment=pullback_adj,
            breakout_adjustment=breakout_adj,
            total_adjustment=breakout_adj,
        )

    return MarketContextModel(
        as_of_date=norm_as_of,
        is_active=True,
        inactive_reason=None,
        universe_size=universe_size,
        valid_sma25_count=valid_sma25_count,
        above_sma25_count=above_sma25_count,
        breadth_ratio=breadth_ratio,
        universe_median_return_20d=med_r20,
        universe_median_return_60d=med_r60,
        universe_median_return_120d=med_r120,
        regime=regime,
        breakout_threshold_delta=breakout_threshold_delta,
        breakout_score_penalty=breakout_score_penalty,
        benchmark=benchmark,
        sector_metrics=sector_metrics,
        symbol_metrics=symbol_metrics,
    )
