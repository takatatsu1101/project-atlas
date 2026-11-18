"""
マルチプロセス並列評価ワーカーおよび逐次・並列共通の銘柄評価ロジック
"""

from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta
import logging
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional, Union

from src.common.logger import get_logger, set_project_log_level
from src.common.storage import StorageManager
from src.config.screening_config import AtlasScreeningConfig
from src.data_collector.collector import DataCollector
from src.feature_engine.manager import FeatureManager
from src.indicator_calculator.calculator import IndicatorCalculator
from src.model.data_models import (
    FeatureSetModel,
    FinancialModel,
    IndicatorSetModel,
    OhlcvModel,
    PatternSetModel,
    ScoreResultModel,
)
from src.pattern_detector.manager import PatternManager
from src.score_engine.manager import ScoreManager
from src.screener.pre_screener import PreScreener

logger = get_logger(__name__)

# ワーカープロセスごとの初期化済みコンポーネント保持領域
_WORKER_STATE: Dict[str, Any] = {}


def normalize_bar_date(value: date) -> date:
    """OhlcvModel.date が datetime の場合でも date 型へ正規化する。"""
    return value.date() if isinstance(value, datetime) else value


def init_pipeline_worker(
    config_dump: Dict[str, Any],
    storage_base_dir: Optional[Union[str, Path]] = None,
    irbank_cache_dir: Optional[Union[str, Path]] = None,
    local_irbank_dir: Optional[Union[str, Path]] = None,
    user_irbank_dir: Optional[Union[str, Path]] = None,
    verbose: bool = False,
) -> None:
    """
    ProcessPoolExecutor ワーカープロセス初期化関数（spawn 方式対応）。
    全レジストリを初期化し、ワーカープロセス固有の読取共有コンポーネントを1回だけ構築する。
    """
    if verbose:
        set_project_log_level(logging.DEBUG)

    import src.feature_engine  # noqa: F401
    import src.pattern_detector  # noqa: F401
    import src.score_engine  # noqa: F401

    storage = (
        StorageManager(base_dir=storage_base_dir)
        if storage_base_dir is not None
        else StorageManager()
    )

    collector = DataCollector(
        storage=storage,
        cache_dir=str(irbank_cache_dir) if irbank_cache_dir is not None else None,
        local_irbank_dir=str(local_irbank_dir) if local_irbank_dir is not None else None,
        user_irbank_dir=str(user_irbank_dir) if user_irbank_dir is not None else None,
        create_dirs=False,
    )

    indicator_calculator = IndicatorCalculator(storage=storage)
    feature_manager = FeatureManager(storage=storage)

    pattern_manager = PatternManager()
    score_manager = ScoreManager()
    pre_screener = PreScreener()
    config = AtlasScreeningConfig.model_validate(config_dump)

    _WORKER_STATE.clear()
    _WORKER_STATE.update(
        {
            "storage": storage,
            "collector": collector,
            "indicator_calculator": indicator_calculator,
            "feature_manager": feature_manager,
            "pattern_manager": pattern_manager,
            "score_manager": score_manager,
            "pre_screener": pre_screener,
            "config": config,
            "verbose": bool(verbose),
        }
    )


def evaluate_single_symbol(
    symbol: str,
    effective_start: date,
    fetch_end: date,
    fetch_as_of: Optional[date],
    as_of_date: Optional[date],
    effective_fiscal_year: int,
    should_check_liquidity: bool,
    use_bulk_eval_ohlcv: bool,
    use_cache: bool,
    use_feature_cache: bool,
    cache_key_suffix: Optional[str],
    allow_irbank_download: bool,
    config: AtlasScreeningConfig,
    ohlcv_collector_fn: Callable[..., List[OhlcvModel]],
    financial_collector_fn: Callable[..., Optional[FinancialModel]],
    indicator_calc_fn: Callable[..., List[IndicatorSetModel]],
    feature_calc_fn: Callable[..., List[FeatureSetModel]],
    pattern_detect_fn: Callable[..., List[PatternSetModel]],
    score_calc_fn: Callable[..., List[ScoreResultModel]],
    pre_screener: PreScreener,
    read_only: bool = False,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    単一銘柄の OHLCV 取得・流動性判定・財務取得・指標/特徴量/パターン/スコア算出を行う共通ヘルパー。
    逐次実行・並列ワーカー双方から利用される。
    """
    phase_timings: Dict[str, float] = {
        "ohlcv_collection": 0.0,
        "liquidity_filter": 0.0,
        "financial_collection": 0.0,
        "indicator_calculation": 0.0,
        "feature_calculation": 0.0,
        "pattern_detection": 0.0,
        "score_calculation": 0.0,
    }
    latest_only_eval = bool(config.screener.latest_only_per_symbol)

    if verbose:
        print(f"\n--- [{symbol}] 処理開始 ---")

    try:
        # 1. OHLCVデータ収集（evaluate 一括取得時も分析側には as_of_date 以前のバーのみ渡す）
        t_ohlcv = time.perf_counter()
        ohlcv_kwargs: Dict[str, Any] = {}
        if fetch_as_of is not None:
            ohlcv_kwargs["as_of_date"] = fetch_as_of
        if read_only:
            ohlcv_kwargs["read_only"] = True
        raw_ohlcv = ohlcv_collector_fn(symbol, effective_start, fetch_end, **ohlcv_kwargs)

        if as_of_date is not None:
            analysis_ohlcv = [
                b for b in raw_ohlcv if normalize_bar_date(b.date) <= as_of_date
            ]
        else:
            analysis_ohlcv = list(raw_ohlcv)
        analysis_ohlcv.sort(key=lambda b: normalize_bar_date(b.date))
        phase_timings["ohlcv_collection"] = time.perf_counter() - t_ohlcv

        if verbose:
            print(f"  OHLCVデータ取得件数: {len(analysis_ohlcv)} 件")
        if not analysis_ohlcv:
            if verbose:
                print(f"  警告: {symbol} のOHLCVデータが存在しないためスキップします。")
            return {
                "symbol": symbol,
                "ok": False,
                "skipped_reason": "empty_ohlcv",
                "error": None,
                "phase_timings": phase_timings,
            }

        # 流動性フィルタ（有効時）
        if should_check_liquidity:
            t_liq = time.perf_counter()
            passed_liquidity = pre_screener.check_liquidity(
                analysis_ohlcv,
                as_of_date=as_of_date,
                criteria=config.pre_screening,
            )
            phase_timings["liquidity_filter"] = time.perf_counter() - t_liq
            if not passed_liquidity:
                if verbose:
                    print(f"  スキップ: {symbol} は流動性基準を満たしませんでした。")
                return {
                    "symbol": symbol,
                    "ok": False,
                    "skipped_reason": "failed_liquidity",
                    "error": None,
                    "phase_timings": phase_timings,
                }

        # 一括取得を実行した銘柄は、未来バーが0件でも取得完了済みとして評価用共有マップへ格納する
        eval_ohlcv = raw_ohlcv if use_bulk_eval_ohlcv else None

        # 2. 財務データ収集（既取得終値を渡して内部の重複 OHLCV 取得を抑止）
        t_fin = time.perf_counter()
        latest_close = analysis_ohlcv[-1].close
        effective_allow_download = False if read_only else allow_irbank_download
        fin_kwargs: Dict[str, Any] = {
            "allow_download": effective_allow_download,
            "latest_close": latest_close,
        }
        if read_only:
            fin_kwargs["read_only"] = True
        if as_of_date is not None:
            financial_data = financial_collector_fn(
                symbol,
                fiscal_year=effective_fiscal_year,
                as_of_date=as_of_date,
                **fin_kwargs,
            )
        else:
            financial_data = financial_collector_fn(
                symbol,
                effective_fiscal_year,
                **fin_kwargs,
            )
        phase_timings["financial_collection"] = time.perf_counter() - t_fin

        if verbose:
            if financial_data:
                print(
                    f"  財務データ取得成功: 決算日={financial_data.fiscal_date}, ROE={financial_data.roe}%"
                )
            else:
                print(f"  警告: {symbol} の財務データが取得できませんでした。")

        # 3. テクニカル指標計算
        t_ind = time.perf_counter()
        ind_kwargs: Dict[str, Any] = {
            "use_cache": use_cache,
            "cache_key_suffix": cache_key_suffix,
        }
        if read_only:
            ind_kwargs["write_cache"] = False
        indicator_sets = indicator_calc_fn(analysis_ohlcv, **ind_kwargs)
        phase_timings["indicator_calculation"] = time.perf_counter() - t_ind
        if verbose:
            print(f"  テクニカル指標計算成功: {len(indicator_sets)} 件")

        # 4. 全特徴量計算（特徴量キャッシュは use_feature_cache 指定時のみ有効）
        t_feat = time.perf_counter()
        feat_kwargs: Dict[str, Any] = {
            "feature_ids": None,
            "use_cache": use_cache and use_feature_cache,
            "cache_key_suffix": cache_key_suffix,
            "latest_only": latest_only_eval,
        }
        if read_only:
            feat_kwargs["write_cache"] = False
        feature_sets = feature_calc_fn(
            analysis_ohlcv,
            indicator_sets,
            financial_data,
            **feat_kwargs,
        )
        phase_timings["feature_calculation"] = time.perf_counter() - t_feat
        if verbose:
            print(f"  特徴量計算成功: {len(feature_sets)} 件の日付データ")

        # 5. パターン検出
        t_pat = time.perf_counter()
        pattern_sets = pattern_detect_fn(
            analysis_ohlcv,
            indicator_sets,
            pattern_ids=None,
            latest_only=latest_only_eval,
        )
        phase_timings["pattern_detection"] = time.perf_counter() - t_pat
        if verbose:
            print(f"  パターン検出成功: {len(pattern_sets)} 件の日付データ")

        # 6. 戦略スコア計算（設定注入）
        t_score = time.perf_counter()
        score_results = score_calc_fn(
            feature_sets,
            pattern_sets,
            score_ids=["S002_StrategyScore"],
            ohlcv_data=analysis_ohlcv,
            indicator_sets=indicator_sets,
            score_configs={"S002_StrategyScore": config.strategy_score},
        )
        phase_timings["score_calculation"] = time.perf_counter() - t_score
        if verbose:
            print(f"  スコア計算成功: {len(score_results)} 件")

        return {
            "symbol": symbol,
            "ok": True,
            "skipped_reason": None,
            "error": None,
            "feature_sets": feature_sets,
            "pattern_sets": pattern_sets,
            "score_results": score_results,
            "financial_data": financial_data,
            "eval_ohlcv": eval_ohlcv,
            "phase_timings": phase_timings,
        }
    except Exception as e:
        if verbose:
            print(f"  エラー [{symbol}]: {e}")
        return {
            "symbol": symbol,
            "ok": False,
            "skipped_reason": None,
            "error": str(e),
            "phase_timings": phase_timings,
        }


def process_symbol_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    ProcessPoolExecutor 用トップレベル銘柄評価タスク（読取専用制約で実行）。
    """
    if not _WORKER_STATE:
        return {
            "symbol": task.get("symbol", ""),
            "ok": False,
            "skipped_reason": None,
            "error": "ワーカープロセスが初期化されていません。",
            "phase_timings": {},
        }

    collector: DataCollector = _WORKER_STATE["collector"]
    indicator_calculator: IndicatorCalculator = _WORKER_STATE["indicator_calculator"]
    feature_manager: FeatureManager = _WORKER_STATE["feature_manager"]
    pattern_manager: PatternManager = _WORKER_STATE["pattern_manager"]
    score_manager: ScoreManager = _WORKER_STATE["score_manager"]
    pre_screener: PreScreener = _WORKER_STATE["pre_screener"]
    config: AtlasScreeningConfig = _WORKER_STATE["config"]

    return evaluate_single_symbol(
        symbol=task["symbol"],
        effective_start=task["effective_start"],
        fetch_end=task["fetch_end"],
        fetch_as_of=task["fetch_as_of"],
        as_of_date=task["as_of_date"],
        effective_fiscal_year=task["effective_fiscal_year"],
        should_check_liquidity=task["should_check_liquidity"],
        use_bulk_eval_ohlcv=task["use_bulk_eval_ohlcv"],
        use_cache=task["use_cache"],
        use_feature_cache=task["use_feature_cache"],
        cache_key_suffix=task["cache_key_suffix"],
        allow_irbank_download=False,
        config=config,
        ohlcv_collector_fn=collector.collect_ohlcv_data,
        financial_collector_fn=collector.collect_financial_data,
        indicator_calc_fn=indicator_calculator.calculate_indicators,
        feature_calc_fn=feature_manager.calculate_features,
        pattern_detect_fn=pattern_manager.detect_patterns,
        score_calc_fn=score_manager.calculate_scores,
        pre_screener=pre_screener,
        read_only=True,
        verbose=bool(_WORKER_STATE.get("verbose", False)),
    )


def evaluate_symbol_across_dates(
    symbol: str,
    symbol_dates: List[date],
    global_start: date,
    global_eval_end: date,
    fiscal_year: Optional[int],
    lookback_days: int,
    should_check_liquidity: bool,
    use_cache: bool,
    use_feature_cache: bool,
    allow_irbank_download: bool,
    config: AtlasScreeningConfig,
    ohlcv_collector_fn: Callable[..., List[OhlcvModel]],
    financial_collector_fn: Callable[..., Optional[FinancialModel]],
    indicator_calc_fn: Callable[..., List[IndicatorSetModel]],
    feature_calc_fn: Callable[..., List[FeatureSetModel]],
    pattern_detect_fn: Callable[..., List[PatternSetModel]],
    score_calc_fn: Callable[..., List[ScoreResultModel]],
    pre_screener: PreScreener,
    read_only: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    複数基準日バックテスト向けの共通単一銘柄評価ヘルパー。
    全期間 OHLCV 読込および全期間ベクトル指標計算を1銘柄につき1回だけ実行し、
    各基準日ごとに未来バーを完全に除外した断面スライスを作成して評価する。
    """
    ohlcv_elapsed = 0.0
    eval_elapsed = 0.0
    latest_only_eval = bool(config.screener.latest_only_per_symbol)

    if verbose:
        print(f"\n--- [{symbol}] 処理開始 ({len(symbol_dates)}基準日) ---")

    try:
        # 1. 全期間 OHLCV を1回だけ読込
        t_ohlcv = time.perf_counter()
        ohlcv_kwargs: Dict[str, Any] = {"as_of_date": global_eval_end}
        if read_only:
            ohlcv_kwargs["read_only"] = True
        raw_ohlcv = ohlcv_collector_fn(
            symbol, global_start, global_eval_end, **ohlcv_kwargs
        )
        full_ohlcv = list(raw_ohlcv)
        full_ohlcv.sort(key=lambda b: normalize_bar_date(b.date))
        ohlcv_elapsed = time.perf_counter() - t_ohlcv

        if verbose:
            print(f"  全期間OHLCV取得件数: {len(full_ohlcv)} 件")

        if not full_ohlcv:
            if verbose:
                print(f"  警告: {symbol} のOHLCVデータが存在しないためスキップします。")
            return {
                "symbol": symbol,
                "ok": False,
                "skipped_reason": "empty_ohlcv",
                "error": None,
                "full_ohlcv": [],
                "per_date_outputs": {},
                "ohlcv_elapsed": ohlcv_elapsed,
                "eval_elapsed": eval_elapsed,
            }

        t_eval = time.perf_counter()
        # 2. 全期間ベクトルテクニカル指標を1回だけ算出（全9指標は因果的）
        batch_cache_suffix = (
            f"batch_{global_start.isoformat()}_{global_eval_end.isoformat()}"
        )
        ind_kwargs: Dict[str, Any] = {
            "use_cache": use_cache,
            "cache_key_suffix": batch_cache_suffix,
        }
        if read_only:
            ind_kwargs["write_cache"] = False
        full_indicators = indicator_calc_fn(full_ohlcv, **ind_kwargs)

        bar_dates = [normalize_bar_date(b.date) for b in full_ohlcv]
        per_date_outputs: Dict[date, Dict[str, Any]] = {}
        effective_allow_download = False if read_only else allow_irbank_download

        # 3. 各基準日断面を bisect_left / bisect_right で厳密分離スライス（d より後のバーを含めない）
        for d in symbol_dates:
            slice_start = d - timedelta(days=lookback_days)
            left_idx = bisect_left(bar_dates, slice_start)
            right_idx = bisect_right(bar_dates, d)
            slice_ohlcv = full_ohlcv[left_idx:right_idx]
            slice_ind = full_indicators[left_idx:right_idx]

            if not slice_ohlcv:
                continue

            if should_check_liquidity:
                if not pre_screener.check_liquidity(
                    slice_ohlcv,
                    as_of_date=d,
                    criteria=config.pre_screening,
                ):
                    continue

            fiscal_year_d = fiscal_year if fiscal_year is not None else d.year
            latest_close = slice_ohlcv[-1].close
            fin_kwargs: Dict[str, Any] = {
                "fiscal_year": fiscal_year_d,
                "as_of_date": d,
                "allow_download": effective_allow_download,
                "latest_close": latest_close,
            }
            if read_only:
                fin_kwargs["read_only"] = True
            financial_data = financial_collector_fn(symbol, **fin_kwargs)

            date_cache_suffix = f"asof_{d.isoformat()}"
            feat_kwargs: Dict[str, Any] = {
                "feature_ids": None,
                "use_cache": use_cache and use_feature_cache,
                "cache_key_suffix": date_cache_suffix,
                "latest_only": latest_only_eval,
            }
            if read_only:
                feat_kwargs["write_cache"] = False
            feature_sets = feature_calc_fn(
                slice_ohlcv,
                slice_ind,
                financial_data,
                **feat_kwargs,
            )

            pattern_sets = pattern_detect_fn(
                slice_ohlcv,
                slice_ind,
                pattern_ids=None,
                latest_only=latest_only_eval,
            )

            score_results = score_calc_fn(
                feature_sets,
                pattern_sets,
                score_ids=["S002_StrategyScore"],
                ohlcv_data=slice_ohlcv,
                indicator_sets=slice_ind,
                score_configs={"S002_StrategyScore": config.strategy_score},
            )

            per_date_outputs[d] = {
                "feature_sets": feature_sets,
                "pattern_sets": pattern_sets,
                "score_results": score_results,
                "financial_data": financial_data,
            }

        eval_elapsed = time.perf_counter() - t_eval
        if verbose:
            print(
                f"  [{symbol}] 全期間指標計算・基準日断面評価完了: "
                f"{len(per_date_outputs)}/{len(symbol_dates)}日通過 "
                f"(OHLCV={ohlcv_elapsed:.2f}s, 評価={eval_elapsed:.2f}s)"
            )
        return {
            "symbol": symbol,
            "ok": True,
            "skipped_reason": None,
            "error": None,
            "full_ohlcv": full_ohlcv,
            "per_date_outputs": per_date_outputs,
            "ohlcv_elapsed": ohlcv_elapsed,
            "eval_elapsed": eval_elapsed,
        }
    except Exception as e:
        if verbose:
            print(f"  エラー [{symbol}]: {e}")
        return {
            "symbol": symbol,
            "ok": False,
            "skipped_reason": None,
            "error": str(e),
            "full_ohlcv": [],
            "per_date_outputs": {},
            "ohlcv_elapsed": ohlcv_elapsed,
            "eval_elapsed": eval_elapsed,
        }


def process_batch_symbol_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    ProcessPoolExecutor 用トップレベル複数基準日バックテスト評価タスク（読取専用制約で実行）。
    """
    if not _WORKER_STATE:
        return {
            "symbol": task.get("symbol", ""),
            "ok": False,
            "skipped_reason": None,
            "error": "ワーカープロセスが初期化されていません。",
            "full_ohlcv": [],
            "per_date_outputs": {},
            "ohlcv_elapsed": 0.0,
            "eval_elapsed": 0.0,
        }

    collector: DataCollector = _WORKER_STATE["collector"]
    indicator_calculator: IndicatorCalculator = _WORKER_STATE["indicator_calculator"]
    feature_manager: FeatureManager = _WORKER_STATE["feature_manager"]
    pattern_manager: PatternManager = _WORKER_STATE["pattern_manager"]
    score_manager: ScoreManager = _WORKER_STATE["score_manager"]
    pre_screener: PreScreener = _WORKER_STATE["pre_screener"]
    config: AtlasScreeningConfig = _WORKER_STATE["config"]

    return evaluate_symbol_across_dates(
        symbol=task["symbol"],
        symbol_dates=task["symbol_dates"],
        global_start=task["global_start"],
        global_eval_end=task["global_eval_end"],
        fiscal_year=task["fiscal_year"],
        lookback_days=task["lookback_days"],
        should_check_liquidity=task["should_check_liquidity"],
        use_cache=task["use_cache"],
        use_feature_cache=task["use_feature_cache"],
        allow_irbank_download=False,
        config=config,
        ohlcv_collector_fn=collector.collect_ohlcv_data,
        financial_collector_fn=collector.collect_financial_data,
        indicator_calc_fn=indicator_calculator.calculate_indicators,
        feature_calc_fn=feature_manager.calculate_features,
        pattern_detect_fn=pattern_manager.detect_patterns,
        score_calc_fn=score_manager.calculate_scores,
        pre_screener=pre_screener,
        read_only=True,
        verbose=bool(_WORKER_STATE.get("verbose", False)),
    )
