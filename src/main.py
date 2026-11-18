import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import nullcontext
from datetime import date, datetime, timedelta
import logging
from pathlib import Path
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from src.common.logger import get_logger, project_log_level
from src.common.progress import ProgressTracker
from src.common.storage import StorageManager
from src.config.screening_config import AtlasScreeningConfig, load_screening_config
from src.config.settings import load_settings
from src.data_collector.collector import (
    collect_financial_data,
    collect_ohlcv_data,
    data_collector,
    prefetch_ohlcv_batch,
)
from src.data_collector.master import MasterManager
from src.evaluator.evaluator import ForwardReturnEvaluator
import src.feature_engine  # 特徴量クラスをインポートしてレジストリに登録させる
from src.feature_engine.manager import FeatureManager, calculate_features
from src.indicator_calculator.calculator import IndicatorCalculator
from src.model.data_models import (
    AnalysisResultModel,
    BatchBacktestSummaryModel,
    EvaluationSummaryModel,
    FeatureSetModel,
    FinancialModel,
    OhlcvModel,
    PatternSetModel,
    ScoreResultModel,
    StockMasterModel,
)
import src.pattern_detector  # パターンクラスをインポートしてレジストリに登録させる
from src.pattern_detector.manager import detect_patterns
from src.pipeline_worker import (
    evaluate_single_symbol,
    evaluate_symbol_across_dates,
    init_pipeline_worker,
    normalize_bar_date,
    process_batch_symbol_task,
    process_symbol_task,
)
from src.presentation.presenter import Presenter
from src.ranking.generator import RankingGenerator
import src.score_engine  # スコアクラスをインポートしてレジストリに登録させる
from src.score_engine.manager import calculate_scores
from src.screener.pre_screener import PreScreener
from src.screener.screener import Screener

logger = get_logger(__name__)

DEFAULT_PARALLEL_MIN_SYMBOLS = 20
_DEFAULT_CALCULATE_FEATURES = calculate_features


def _resolve_sequential_calculators():
    """
    逐次実行用の IndicatorCalculator と特徴量計算関数を解決する。
    data_collector.storage がカスタム StorageManager の場合は逐次実行でも同一の
    StorageManager を引き継ぎ、並列実行との対称性を保つ（モック差し替え時はモックを優先）。
    """
    storage_obj = getattr(data_collector, "storage", None)
    if isinstance(storage_obj, StorageManager):
        indicator_calc = IndicatorCalculator(storage=storage_obj)
        if calculate_features is _DEFAULT_CALCULATE_FEATURES:
            feat_fn = FeatureManager(storage=storage_obj).calculate_features
        else:
            feat_fn = calculate_features
        return indicator_calc, feat_fn
    return IndicatorCalculator(), calculate_features


def _resolve_worker_count(
    workers: Optional[int],
    num_items: int,
    parallel_min_symbols: int = DEFAULT_PARALLEL_MIN_SYMBOLS,
) -> int:
    """
    並列ワーカー数を解決する。
    - workers is None の場合は settings.FEATURE_ENGINE_PARALLEL_PROCESSES を使用
    - 解決値が <= 0 または bool の場合は ValueError を送出
    - 解決値が 1 または num_items < parallel_min_symbols の場合は 1（逐次実行）
    - それ以外は min(resolved, num_items) を返す
    """
    resolved = (
        load_settings().FEATURE_ENGINE_PARALLEL_PROCESSES
        if workers is None
        else workers
    )
    if isinstance(resolved, bool) or not isinstance(resolved, int) or resolved <= 0:
        raise ValueError(f"workers は 1 以上の整数を指定してください: {resolved}")
    if resolved == 1 or num_items <= 0 or num_items < parallel_min_symbols:
        return 1
    return min(resolved, num_items)


def _resolve_worker_initargs(
    config: AtlasScreeningConfig,
    verbose: bool = False,
) -> Tuple[Dict[str, Any], Optional[str], Optional[str], Optional[str], Optional[str], bool]:
    """ワーカー初期化用の設定・ストレージパス群を安全に抽出する。"""
    storage_obj = getattr(data_collector, "storage", None)
    base_dir = getattr(storage_obj, "base_dir", None)
    storage_base_dir = str(base_dir) if isinstance(base_dir, (str, Path)) else None

    cache_dir_val = getattr(data_collector, "cache_dir", None)
    irbank_cache_dir = str(cache_dir_val) if isinstance(cache_dir_val, (str, Path)) else None

    local_dir_val = getattr(data_collector, "local_irbank_dir", None)
    local_irbank_dir = str(local_dir_val) if isinstance(local_dir_val, (str, Path)) else None

    user_dir_val = getattr(data_collector, "user_irbank_dir", None)
    user_irbank_dir = str(user_dir_val) if isinstance(user_dir_val, (str, Path)) else None

    return (
        config.model_dump(mode="json"),
        storage_base_dir,
        irbank_cache_dir,
        local_irbank_dir,
        user_irbank_dir,
        bool(verbose),
    )


def _classify_eval_outcome(res: Dict[str, Any]) -> Tuple[int, int, int]:
    """銘柄評価結果1件を (通過, スキップ, エラー) のカウント増分へ分類する。"""
    if res.get("error") is not None:
        return 0, 0, 1
    if res.get("ok"):
        return 1, 0, 0
    return 0, 1, 0


def _execute_symbol_tasks_with_progress(
    symbols: Sequence[str],
    progress_label: str,
    effective_workers: int,
    config: AtlasScreeningConfig,
    verbose: bool,
    worker_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_task_fn: Callable[[str], Dict[str, Any]],
    sequential_fn: Callable[[str], Dict[str, Any]],
    build_error_result_fn: Callable[[str, Exception], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    銘柄評価タスク群を並列または逐次で実行し、ProgressTracker で進捗表示しつつ
    元の symbols 順を維持した結果リストを返す。
    """
    total = len(symbols)
    if total == 0:
        return []

    ordered_results: List[Optional[Dict[str, Any]]] = [None] * total
    tracker = ProgressTracker(label=progress_label, total=total)
    passed_cnt = 0
    skipped_cnt = 0
    error_cnt = 0

    def _record_and_report(idx: int, res: Dict[str, Any], completed_cnt: int) -> None:
        nonlocal passed_cnt, skipped_cnt, error_cnt
        ordered_results[idx] = res
        p_inc, s_inc, e_inc = _classify_eval_outcome(res)
        passed_cnt += p_inc
        skipped_cnt += s_inc
        error_cnt += e_inc
        tracker.update(
            completed_cnt,
            detail=f"通過={passed_cnt}, スキップ={skipped_cnt}, エラー={error_cnt}",
        )

    if effective_workers > 1:
        initargs = _resolve_worker_initargs(config, verbose=verbose)
        with ProcessPoolExecutor(
            max_workers=effective_workers,
            initializer=init_pipeline_worker,
            initargs=initargs,
        ) as executor:
            future_to_idx = {
                executor.submit(worker_fn, build_task_fn(sym)): idx
                for idx, sym in enumerate(symbols)
            }
            for completed_cnt, future in enumerate(as_completed(future_to_idx), start=1):
                idx = future_to_idx[future]
                sym = symbols[idx]
                try:
                    res = future.result()
                except Exception as e:
                    res = build_error_result_fn(sym, e)
                _record_and_report(idx, res, completed_cnt)
    else:
        for idx, sym in enumerate(symbols):
            try:
                res = sequential_fn(sym)
            except Exception as e:
                res = build_error_result_fn(sym, e)
            _record_and_report(idx, res, idx + 1)

    return [r for r in ordered_results if r is not None]


def _resolve_target_symbols(
    symbols: Optional[List[str]],
    master_stocks: List[StockMasterModel],
    pre_screener: PreScreener,
    config: AtlasScreeningConfig,
    effective_fiscal_year: int,
    as_of_date: Optional[date],
    apply_liquidity_filter: Optional[bool],
    use_pre_screening: bool,
) -> Tuple[List[str], bool]:
    """対象銘柄リストと流動性フィルタ適用可否を解決する共通ヘルパー。"""
    if symbols is None:
        financial_snapshot = data_collector.load_financial_snapshot(
            fiscal_year=effective_fiscal_year,
            as_of_date=as_of_date,
        )
        filtered_stocks = pre_screener.filter_universe(
            master_stocks,
            financial_snapshot,
            criteria=config.pre_screening,
        )
        target_symbols = [s.symbol for s in filtered_stocks]
        should_check_liquidity = (
            True if apply_liquidity_filter is None else apply_liquidity_filter
        )
        return target_symbols, should_check_liquidity

    if use_pre_screening and master_stocks:
        symbol_set = set(symbols)
        subset_masters = [
            s for s in master_stocks if s.symbol in symbol_set or s.code in symbol_set
        ]
        financial_snapshot = data_collector.load_financial_snapshot(
            fiscal_year=effective_fiscal_year,
            as_of_date=as_of_date,
        )
        filtered_stocks = pre_screener.filter_universe(
            subset_masters,
            financial_snapshot,
            criteria=config.pre_screening,
        )
        target_symbols = [s.symbol for s in filtered_stocks]
    else:
        target_symbols = list(symbols)
    should_check_liquidity = (
        bool(apply_liquidity_filter)
        if apply_liquidity_filter is not None
        else False
    )
    return target_symbols, should_check_liquidity


def run_full_pipeline(
    symbols: Optional[List[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    fiscal_year: Optional[int] = None,
    as_of_date: Optional[date] = None,
    config_path: Optional[Union[str, Path]] = None,
    output_dir: Optional[Union[str, Path]] = None,
    export_reports: bool = True,
    apply_liquidity_filter: Optional[bool] = None,
    use_pre_screening: bool = False,
    mode: str = "screen",
    horizons: Optional[List[int]] = None,
    use_cache: bool = True,
    use_feature_cache: bool = False,
    update_master: bool = False,
    allow_irbank_download: bool = True,
    workers: Optional[int] = None,
    parallel_min_symbols: int = DEFAULT_PARALLEL_MIN_SYMBOLS,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Project Atlas 全パイプラインを実行する。
    1. 引数検証・YAML設定ロード
    2. マスタ・財務スナップショットに基づく事前スクリーニング（symbols 未指定時または use_pre_screening=True 時）
    3. OHLCV・財務データ収集、流動性チェック、テクニカル指標・特徴量・パターン検出
    4. 戦略スコア計算（S002_StrategyScore）
    5. スクリーニング・総合＆戦略別ランキング生成
    6. evaluate モード時はフォワードリターン検証を実行
    7. CLI表示および JSON / Markdown レポート出力

    Note:
        - 戻り値 ``timings_sec`` の ``total`` およびレポートメタ情報 ``elapsed_sec`` は、
          パイプライン開始からステップ6（フォワード評価）完了時点＝レポート出力・CLI表示前までの
          壁時計所要時間（秒）を計測する。
        - 並列実行時（``workers > 1``）、銘柄評価各フェーズの ``timings_sec`` は各ワーカーの
          延べ処理時間を合算するため、壁時計時間である ``total`` を上回り得る。
    """
    if mode not in ("screen", "evaluate"):
        raise ValueError(
            f"不正な実行モードが指定されました: {mode} ('screen' または 'evaluate' を指定してください)"
        )
    if mode == "evaluate" and as_of_date is None:
        raise ValueError("evaluate モードでは as_of_date の指定が必須です。")
    _resolve_worker_count(workers, 0, parallel_min_symbols=parallel_min_symbols)

    as_of_date = normalize_bar_date(as_of_date) if as_of_date is not None else None
    start_date = normalize_bar_date(start_date) if start_date is not None else None
    end_date = normalize_bar_date(end_date) if end_date is not None else None

    with project_log_level(logging.DEBUG) if verbose else nullcontext():
        pipeline_start = time.perf_counter()
        timings_sec: Dict[str, float] = {
            "setup_and_prescreen": 0.0,
            "ohlcv_collection": 0.0,
            "liquidity_filter": 0.0,
            "financial_collection": 0.0,
            "indicator_calculation": 0.0,
            "feature_calculation": 0.0,
            "pattern_detection": 0.0,
            "score_calculation": 0.0,
            "screening_and_ranking": 0.0,
            "forward_evaluation": 0.0,
            "total": 0.0,
        }

        print("=== Project Atlas 全パイプライン実行 ===", flush=True)
        print("[1/4] セットアップ・事前スクリーニング...", flush=True)

        t_setup = time.perf_counter()
        config: AtlasScreeningConfig = load_screening_config(config_path=config_path)
        resolved_horizons = horizons if horizons is not None else list(config.evaluation.horizons)
        if mode == "evaluate":
            resolved_horizons = ForwardReturnEvaluator._normalize_horizons(resolved_horizons)

        cache_key_suffix = f"asof_{as_of_date.isoformat()}" if as_of_date is not None else None

        analysis_end = (
            min(end_date, as_of_date)
            if (end_date is not None and as_of_date is not None)
            else (as_of_date or end_date or date.today())
        )
        effective_start = start_date or (analysis_end - timedelta(days=365))
        effective_fiscal_year = (
            fiscal_year
            if fiscal_year is not None
            else (as_of_date or analysis_end).year
        )

        # evaluate モード時は end_date の指定状況に応じてフォワード検証用 OHLCV の一括取得可否を決定する
        fetch_end = analysis_end
        fetch_as_of = as_of_date
        eval_end_arg: Optional[date] = None
        use_bulk_eval_ohlcv = False
        if mode == "evaluate":
            assert as_of_date is not None
            if end_date is None:
                eval_fetch_end = ForwardReturnEvaluator.compute_default_fetch_end(
                    as_of_date, resolved_horizons
                )
                eval_end_arg = None
            elif end_date > as_of_date:
                eval_fetch_end = end_date
                eval_end_arg = end_date
            else:
                eval_fetch_end = analysis_end
                eval_end_arg = None

            if eval_fetch_end > analysis_end:
                fetch_end = eval_fetch_end
                fetch_as_of = eval_fetch_end
                use_bulk_eval_ohlcv = True

        master_manager = MasterManager()
        if update_master:
            master_stocks = master_manager.update_from_jpx()
        else:
            master_stocks = master_manager.load_master()
        master_map: Dict[str, StockMasterModel] = {s.symbol: s for s in master_stocks}

        pre_screener = PreScreener()
        target_symbols, should_check_liquidity = _resolve_target_symbols(
            symbols=symbols,
            master_stocks=master_stocks,
            pre_screener=pre_screener,
            config=config,
            effective_fiscal_year=effective_fiscal_year,
            as_of_date=as_of_date,
            apply_liquidity_filter=apply_liquidity_filter,
            use_pre_screening=use_pre_screening,
        )
        effective_workers = _resolve_worker_count(
            workers,
            len(target_symbols),
            parallel_min_symbols=parallel_min_symbols,
        )
        timings_sec["setup_and_prescreen"] = time.perf_counter() - t_setup
        print(
            f"  対象銘柄: {len(target_symbols)}銘柄 (workers={effective_workers})",
            flush=True,
        )

        calculator, sequential_feature_calc = _resolve_sequential_calculators()
        all_feature_sets: List[FeatureSetModel] = []
        all_pattern_sets: List[PatternSetModel] = []
        all_score_results: List[ScoreResultModel] = []
        financial_map: Dict[str, FinancialModel] = {}
        eval_ohlcv_map: Dict[str, List[OhlcvModel]] = {}
        processed_symbols: List[str] = []

        # 対象銘柄の OHLCV を事前にチャンク並列で一括プリフェッチ
        print("[2/4] OHLCV・財務データ準備...", flush=True)
        if target_symbols:
            t_prefetch = time.perf_counter()
            if fetch_as_of is not None:
                prefetch_ohlcv_batch(
                    target_symbols,
                    effective_start,
                    fetch_end,
                    as_of_date=fetch_as_of,
                )
            else:
                prefetch_ohlcv_batch(target_symbols, effective_start, fetch_end)
            timings_sec["ohlcv_collection"] += time.perf_counter() - t_prefetch

        if effective_workers > 1 and target_symbols:
            # 並列ワーカーは完全読取専用で動かすため、親プロセス側で IR BANK キャッシュを事前ウォームアップする
            t_warmup = time.perf_counter()
            warmup_years = list(range(effective_fiscal_year - 7, effective_fiscal_year + 1))
            data_collector.warmup_irbank_cache(
                warmup_years, allow_download=allow_irbank_download
            )
            timings_sec["financial_collection"] += time.perf_counter() - t_warmup

        print(f"[3/4] 銘柄評価 ({len(target_symbols)}銘柄)...", flush=True)
        symbol_eval_results = _execute_symbol_tasks_with_progress(
            symbols=target_symbols,
            progress_label="銘柄評価",
            effective_workers=effective_workers,
            config=config,
            verbose=verbose,
            worker_fn=process_symbol_task,
            build_task_fn=lambda sym: {
                "symbol": sym,
                "effective_start": effective_start,
                "fetch_end": fetch_end,
                "fetch_as_of": fetch_as_of,
                "as_of_date": as_of_date,
                "effective_fiscal_year": effective_fiscal_year,
                "should_check_liquidity": should_check_liquidity,
                "use_bulk_eval_ohlcv": use_bulk_eval_ohlcv,
                "use_cache": use_cache,
                "use_feature_cache": use_feature_cache,
                "cache_key_suffix": cache_key_suffix,
            },
            sequential_fn=lambda sym: evaluate_single_symbol(
                symbol=sym,
                effective_start=effective_start,
                fetch_end=fetch_end,
                fetch_as_of=fetch_as_of,
                as_of_date=as_of_date,
                effective_fiscal_year=effective_fiscal_year,
                should_check_liquidity=should_check_liquidity,
                use_bulk_eval_ohlcv=use_bulk_eval_ohlcv,
                use_cache=use_cache,
                use_feature_cache=use_feature_cache,
                cache_key_suffix=cache_key_suffix,
                allow_irbank_download=allow_irbank_download,
                config=config,
                ohlcv_collector_fn=collect_ohlcv_data,
                financial_collector_fn=collect_financial_data,
                indicator_calc_fn=calculator.calculate_indicators,
                feature_calc_fn=sequential_feature_calc,
                pattern_detect_fn=detect_patterns,
                score_calc_fn=calculate_scores,
                pre_screener=pre_screener,
                read_only=False,
                verbose=verbose,
            ),
            build_error_result_fn=lambda sym, e: {
                "symbol": sym,
                "ok": False,
                "skipped_reason": None,
                "error": str(e),
                "phase_timings": {},
            },
        )

        # 決定性を保証するため、target_symbols の元の順序で結果を結合する
        for res in symbol_eval_results:
            sym = res["symbol"]
            for phase_key, elapsed in (res.get("phase_timings") or {}).items():
                if phase_key in timings_sec:
                    timings_sec[phase_key] += float(elapsed)

            if res.get("error") is not None:
                logger.error(f"パイプライン処理中にエラーが発生しました [{sym}]: {res['error']}")
                continue
            if not res.get("ok"):
                continue

            if res.get("eval_ohlcv") is not None:
                eval_ohlcv_map[sym] = res["eval_ohlcv"]
            if res.get("financial_data") is not None:
                financial_map[sym] = res["financial_data"]

            all_feature_sets.extend(res["feature_sets"])
            all_pattern_sets.extend(res["pattern_sets"])
            all_score_results.extend(res["score_results"])
            processed_symbols.append(sym)

        # 7. スクリーニング適用 & 8. 総合・戦略別ランキング生成
        print("[4/4] スクリーニング・ランキング生成...", flush=True)
        t_screen_rank = time.perf_counter()
        screener_instance = Screener()
        filtered_scores = screener_instance.apply_screener(
            all_score_results, criteria=config.screener
        )

        ranking_gen = RankingGenerator()
        strategy_rankings = ranking_gen.generate_strategy_rankings(
            filtered_scores,
            master_map=master_map,
            feature_sets=all_feature_sets,
            pattern_sets=all_pattern_sets,
            financial_map=financial_map,
            overall_top_n=config.ranking.top_n,
            strategy_top_n=config.ranking.strategy_top_n,
        )
        overall_ranking: List[AnalysisResultModel] = strategy_rankings["overall"]
        timings_sec["screening_and_ranking"] = time.perf_counter() - t_screen_rank

        evaluation_summary: Optional[EvaluationSummaryModel] = None
        if mode == "evaluate":
            assert as_of_date is not None
            print("  フォワードリターン検証を実行中...", flush=True)
            t_eval = time.perf_counter()
            evaluator = ForwardReturnEvaluator()
            evaluation_summary = evaluator.evaluate(
                overall_ranking,
                as_of_date=as_of_date,
                ohlcv_map=eval_ohlcv_map if use_bulk_eval_ohlcv else None,
                horizons=resolved_horizons,
                entry_price_mode=config.evaluation.entry_price_mode,
                eval_end_date=eval_end_arg,
            )
            timings_sec["forward_evaluation"] = time.perf_counter() - t_eval

        print(
            f"\n=== 全パイプライン処理完了: 抽出結果 {len(overall_ranking)} 件 "
            f"(対象 {len(processed_symbols)} 銘柄) ===",
            flush=True,
        )

        # レポート出力・CLI表示前（ステップ1〜6完了時点）までを合計所要時間として計測する
        timings_sec["total"] = time.perf_counter() - pipeline_start
        rounded_timings: Dict[str, float] = {k: round(v, 4) for k, v in timings_sec.items()}

        run_metadata: Dict[str, Any] = {
            "mode": mode,
            "target_symbols_count": len(target_symbols),
            "processed_symbols_count": len(processed_symbols),
            "total_score_results": len(all_score_results),
            "filtered_count": len(filtered_scores),
            "fiscal_year": effective_fiscal_year,
            "elapsed_sec": rounded_timings["total"],
        }

        # 9. プレゼンテーション出力（CLI表示 ＋ レポート出力）
        presenter_instance = Presenter()
        presenter_instance.display_results(
            overall_ranking,
            output_type="cli",
            evaluation_summary=evaluation_summary,
        )

        report_paths: Dict[str, Path] = {}
        if export_reports:
            resolved_output_dir = (
                output_dir if output_dir is not None else config.output.output_dir
            )
            report_paths = presenter_instance.export_reports(
                overall_ranking,
                output_dir=resolved_output_dir,
                formats=config.output.formats,
                as_of_date=as_of_date,
                strategy_rankings=strategy_rankings,
                metadata=run_metadata,
                evaluation_summary=evaluation_summary,
            )

        if report_paths:
            paths_str = ", ".join(f"{k}={v}" for k, v in report_paths.items())
            print(f"レポート出力先: {paths_str}", flush=True)

        timing_summary = ", ".join(f"{k}={v:.3f}s" for k, v in rounded_timings.items())
        logger.debug(f"パイプラインフェーズ別所要時間: {timing_summary}")
        print(f"フェーズ別所要時間: {timing_summary}", flush=True)

        return {
            "as_of_date": as_of_date,
            "processed_symbols": processed_symbols,
            "score_results": all_score_results,
            "filtered_scores": filtered_scores,
            "analysis_results": overall_ranking,
            "strategy_rankings": strategy_rankings,
            "evaluation_summary": evaluation_summary,
            "report_paths": report_paths,
            "config": config,
            "timings_sec": rounded_timings,
        }


def run_batch_backtest(
    as_of_dates: Sequence[date],
    symbols: Optional[List[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    fiscal_year: Optional[int] = None,
    config_path: Optional[Union[str, Path]] = None,
    output_dir: Optional[Union[str, Path]] = None,
    export_reports: bool = True,
    apply_liquidity_filter: Optional[bool] = None,
    use_pre_screening: bool = False,
    horizons: Optional[List[int]] = None,
    use_cache: bool = True,
    use_feature_cache: bool = False,
    update_master: bool = False,
    allow_irbank_download: bool = True,
    workers: Optional[int] = None,
    parallel_min_symbols: int = DEFAULT_PARALLEL_MIN_SYMBOLS,
    lookback_days: int = 365,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    複数基準日一括バックテストを実行する（「全期間1回読込・ベクトル指標1回算出・基準日断面厳密分離」）。

    Note:
        - ``global_start = start_date or (min_as_of - timedelta(days=lookback_days))`` から
          ``global_eval_end`` までの全期間 OHLCV を 1 回だけ読み込み、全期間ベクトル指標を 1 回算出する。
        - 全 9 指標（SMA5/25/75, RSI14, MACD, HIGHEST_HIGH_20, LOWEST_LOW_20, ATR14, VOLUME_RATIO）は
          因果的（未来バー非参照）であり、各基準日 ``d`` の断面評価には
          ``[d - timedelta(days=lookback_days), d]`` の範囲のみを厳密分離スライスして渡す。
          EMA 系指標（MACD）は ``global_start`` からの連続ウォームアップを後続断面へ引き継ぐ一方、
          ``d`` より後のバーには一切依存しない。
        - 並列実行時（``workers > 1``）、``timings_sec["ohlcv_collection"]`` や
          ``timings_sec["symbol_evaluation"]`` には各ワーカーの延べ処理時間が合算されるため、
          壁時計時間である ``total`` を上回り得る。
    """
    if not as_of_dates:
        raise ValueError("as_of_dates には1つ以上の基準日を指定してください。")
    if isinstance(lookback_days, bool) or not isinstance(lookback_days, int) or lookback_days <= 0:
        raise ValueError(f"lookback_days は 1 以上の整数を指定してください: {lookback_days}")
    _resolve_worker_count(workers, 0, parallel_min_symbols=parallel_min_symbols)

    sorted_dates = sorted({normalize_bar_date(d) for d in as_of_dates})
    start_date = normalize_bar_date(start_date) if start_date is not None else None
    end_date = normalize_bar_date(end_date) if end_date is not None else None

    min_as_of = sorted_dates[0]
    max_as_of = sorted_dates[-1]
    if end_date is not None and end_date < max_as_of:
        raise ValueError(
            f"end_date ({end_date.isoformat()}) は最遅基準日 ({max_as_of.isoformat()}) 以上を指定してください。"
        )

    with project_log_level(logging.DEBUG) if verbose else nullcontext():
        pipeline_start = time.perf_counter()
        timings_sec: Dict[str, float] = {
            "setup_and_prescreen": 0.0,
            "ohlcv_collection": 0.0,
            "symbol_evaluation": 0.0,
            "screening_and_ranking": 0.0,
            "forward_evaluation": 0.0,
            "total": 0.0,
        }

        print("=== Project Atlas 一括バックテスト実行 ===", flush=True)
        print("[1/5] セットアップ・IR BANK キャッシュ準備・基準日別ユニバース解決...", flush=True)

        t_setup = time.perf_counter()
        config: AtlasScreeningConfig = load_screening_config(config_path=config_path)
        resolved_horizons = ForwardReturnEvaluator._normalize_horizons(
            horizons if horizons is not None else list(config.evaluation.horizons)
        )

        master_manager = MasterManager()
        if update_master:
            master_stocks = master_manager.update_from_jpx()
        else:
            master_stocks = master_manager.load_master()
        master_map: Dict[str, StockMasterModel] = {s.symbol: s for s in master_stocks}

        # load_financial_snapshot (allow_download=False) および並列ワーカー読取専用実行の前に、
        # 必要全年度の IR BANK JSON キャッシュを事前ウォームアップする
        if symbols is None or len(symbols) > 0:
            timings_sec["setup_and_prescreen"] += time.perf_counter() - t_setup
            t_warmup = time.perf_counter()
            fiscal_years_needed = [
                fiscal_year if fiscal_year is not None else d.year for d in sorted_dates
            ]
            min_fy = min(fiscal_years_needed)
            max_fy = max(fiscal_years_needed)
            warmup_years = list(range(min_fy - 7, max_fy + 1))
            data_collector.warmup_irbank_cache(
                warmup_years, allow_download=allow_irbank_download
            )
            timings_sec["symbol_evaluation"] += time.perf_counter() - t_warmup
            t_setup = time.perf_counter()

        pre_screener = PreScreener()
        target_symbols_by_date: Dict[date, List[str]] = {}
        should_check_liquidity = False
        if symbols is not None and not use_pre_screening:
            shared_symbols = list(dict.fromkeys(symbols))
            should_check_liquidity = (
                bool(apply_liquidity_filter)
                if apply_liquidity_filter is not None
                else False
            )
            for d in sorted_dates:
                target_symbols_by_date[d] = list(shared_symbols)
        else:
            for d in sorted_dates:
                fiscal_year_d = fiscal_year if fiscal_year is not None else d.year
                t_syms, liq_flag = _resolve_target_symbols(
                    symbols=symbols,
                    master_stocks=master_stocks,
                    pre_screener=pre_screener,
                    config=config,
                    effective_fiscal_year=fiscal_year_d,
                    as_of_date=d,
                    apply_liquidity_filter=apply_liquidity_filter,
                    use_pre_screening=use_pre_screening,
                )
                target_symbols_by_date[d] = list(dict.fromkeys(t_syms))
                should_check_liquidity = liq_flag

        # 全基準日の対象銘柄和集合と銘柄別の評価対象基準日リストを構築
        union_symbols_map: Dict[str, None] = {}
        dates_by_symbol: Dict[str, List[date]] = {}
        for d in sorted_dates:
            for sym in target_symbols_by_date[d]:
                union_symbols_map[sym] = None
                dates_by_symbol.setdefault(sym, []).append(d)
        union_symbols = list(union_symbols_map.keys())

        global_start = start_date or (min_as_of - timedelta(days=lookback_days))
        default_eval_end = ForwardReturnEvaluator.compute_default_fetch_end(
            max_as_of, resolved_horizons
        )
        global_eval_end = max(
            max_as_of,
            end_date if end_date is not None else default_eval_end,
        )

        effective_workers = _resolve_worker_count(
            workers,
            len(union_symbols),
            parallel_min_symbols=parallel_min_symbols,
        )
        timings_sec["setup_and_prescreen"] += time.perf_counter() - t_setup
        print(
            f"  対象期間: {len(sorted_dates)}基準日 ({min_as_of.isoformat()} 〜 {max_as_of.isoformat()}), "
            f"ユニーク {len(union_symbols)}銘柄 (workers={effective_workers})",
            flush=True,
        )

        # 3. 全期間1回プリフェッチ
        print("[2/5] 全期間 OHLCV キャッシュ準備...", flush=True)
        if union_symbols:
            t_prefetch = time.perf_counter()
            prefetch_ohlcv_batch(
                union_symbols,
                global_start,
                global_eval_end,
                as_of_date=global_eval_end,
            )
            timings_sec["ohlcv_collection"] += time.perf_counter() - t_prefetch

        # 4. 銘柄ごとの「全期間1回読込・ベクトル指標1回算出・基準日断面評価」
        print(f"[3/5] 全期間指標・基準日断面評価 ({len(union_symbols)}銘柄)...", flush=True)
        calculator, sequential_feature_calc = _resolve_sequential_calculators()
        symbol_batch_results = _execute_symbol_tasks_with_progress(
            symbols=union_symbols,
            progress_label="全期間指標・基準日断面評価",
            effective_workers=effective_workers,
            config=config,
            verbose=verbose,
            worker_fn=process_batch_symbol_task,
            build_task_fn=lambda sym: {
                "symbol": sym,
                "symbol_dates": dates_by_symbol[sym],
                "global_start": global_start,
                "global_eval_end": global_eval_end,
                "fiscal_year": fiscal_year,
                "lookback_days": lookback_days,
                "should_check_liquidity": should_check_liquidity,
                "use_cache": use_cache,
                "use_feature_cache": use_feature_cache,
            },
            sequential_fn=lambda sym: evaluate_symbol_across_dates(
                symbol=sym,
                symbol_dates=dates_by_symbol[sym],
                global_start=global_start,
                global_eval_end=global_eval_end,
                fiscal_year=fiscal_year,
                lookback_days=lookback_days,
                should_check_liquidity=should_check_liquidity,
                use_cache=use_cache,
                use_feature_cache=use_feature_cache,
                allow_irbank_download=allow_irbank_download,
                config=config,
                ohlcv_collector_fn=collect_ohlcv_data,
                financial_collector_fn=collect_financial_data,
                indicator_calc_fn=calculator.calculate_indicators,
                feature_calc_fn=sequential_feature_calc,
                pattern_detect_fn=detect_patterns,
                score_calc_fn=calculate_scores,
                pre_screener=pre_screener,
                read_only=False,
                verbose=verbose,
            ),
            build_error_result_fn=lambda sym, e: {
                "symbol": sym,
                "ok": False,
                "skipped_reason": None,
                "error": str(e),
                "full_ohlcv": [],
                "per_date_outputs": {},
                "ohlcv_elapsed": 0.0,
                "eval_elapsed": 0.0,
            },
        )

        full_ohlcv_map: Dict[str, List[OhlcvModel]] = {}
        date_features: Dict[date, List[FeatureSetModel]] = {d: [] for d in sorted_dates}
        date_patterns: Dict[date, List[PatternSetModel]] = {d: [] for d in sorted_dates}
        date_scores: Dict[date, List[ScoreResultModel]] = {d: [] for d in sorted_dates}
        date_financial_map: Dict[date, Dict[str, FinancialModel]] = {d: {} for d in sorted_dates}
        date_processed_symbols: Dict[date, List[str]] = {d: [] for d in sorted_dates}

        # union_symbols の決定性を維持したまま各基準日の結果へ振り分ける
        per_symbol_map: Dict[str, Dict[str, Any]] = {}
        for res in symbol_batch_results:
            sym = res["symbol"]
            timings_sec["ohlcv_collection"] += float(res.get("ohlcv_elapsed", 0.0))
            timings_sec["symbol_evaluation"] += float(res.get("eval_elapsed", 0.0))
            if res.get("error") is not None:
                logger.error(f"一括バックテスト処理中にエラーが発生しました [{sym}]: {res['error']}")
                continue
            if not res.get("ok"):
                continue
            full_ohlcv_map[sym] = res["full_ohlcv"]
            per_symbol_map[sym] = res

        for d in sorted_dates:
            for sym in target_symbols_by_date[d]:
                sym_res = per_symbol_map.get(sym)
                if sym_res is None:
                    continue
                d_out = sym_res["per_date_outputs"].get(d)
                if d_out is None:
                    continue
                date_processed_symbols[d].append(sym)
                date_features[d].extend(d_out["feature_sets"])
                date_patterns[d].extend(d_out["pattern_sets"])
                date_scores[d].extend(d_out["score_results"])
                if d_out["financial_data"] is not None:
                    date_financial_map[d][sym] = d_out["financial_data"]

        # 5. 基準日別ランキング・フォワード評価・横断集計
        print(f"[4/5] 基準日別スクリーニング・フォワード検証 ({len(sorted_dates)}基準日)...", flush=True)
        screener_instance = Screener()
        ranking_gen = RankingGenerator()
        evaluator = ForwardReturnEvaluator()

        per_date_results: Dict[date, Dict[str, Any]] = {}
        per_date_summaries: Dict[date, EvaluationSummaryModel] = {}
        date_tracker = ProgressTracker(
            label="基準日別スクリーニング・検証",
            total=len(sorted_dates),
        )

        for idx, d in enumerate(sorted_dates, start=1):
            t_rank = time.perf_counter()
            filtered_scores = screener_instance.apply_screener(
                date_scores[d], criteria=config.screener
            )
            strategy_rankings = ranking_gen.generate_strategy_rankings(
                filtered_scores,
                master_map=master_map,
                feature_sets=date_features[d],
                pattern_sets=date_patterns[d],
                financial_map=date_financial_map[d],
                overall_top_n=config.ranking.top_n,
                strategy_top_n=config.ranking.strategy_top_n,
            )
            overall_ranking: List[AnalysisResultModel] = strategy_rankings["overall"]
            timings_sec["screening_and_ranking"] += time.perf_counter() - t_rank

            t_eval = time.perf_counter()
            eval_summary = evaluator.evaluate(
                overall_ranking,
                as_of_date=d,
                ohlcv_map=full_ohlcv_map,
                horizons=resolved_horizons,
                entry_price_mode=config.evaluation.entry_price_mode,
                eval_end_date=end_date,
            )
            timings_sec["forward_evaluation"] += time.perf_counter() - t_eval

            per_date_summaries[d] = eval_summary
            per_date_results[d] = {
                "as_of_date": d,
                "target_symbols": target_symbols_by_date[d],
                "processed_symbols": date_processed_symbols[d],
                "score_results": date_scores[d],
                "filtered_scores": filtered_scores,
                "analysis_results": overall_ranking,
                "strategy_rankings": strategy_rankings,
                "evaluation_summary": eval_summary,
            }
            date_tracker.update(
                idx,
                detail=f"基準日={d.isoformat()}, 抽出={len(overall_ranking)}件",
            )

        print("[5/5] 横断集計・最終結果出力...", flush=True)
        batch_summary: BatchBacktestSummaryModel = ForwardReturnEvaluator.aggregate_batch_summaries(
            per_date_summaries,
            horizons=resolved_horizons,
            entry_price_mode=config.evaluation.entry_price_mode,
        )

        timings_sec["total"] = time.perf_counter() - pipeline_start
        rounded_timings: Dict[str, float] = {k: round(v, 4) for k, v in timings_sec.items()}

        run_metadata: Dict[str, Any] = {
            "mode": "backtest",
            "total_dates": batch_summary.total_dates,
            "union_symbols_count": len(union_symbols),
            "total_candidates": batch_summary.total_candidates,
            "workers_used": effective_workers,
            "elapsed_sec": rounded_timings["total"],
        }

        presenter_instance = Presenter()
        presenter_instance.display_batch_backtest_results(batch_summary)

        report_paths: Dict[str, Path] = {}
        if export_reports:
            resolved_output_dir = (
                output_dir if output_dir is not None else config.output.output_dir
            )
            report_paths = presenter_instance.export_batch_backtest_reports(
                batch_summary,
                output_dir=resolved_output_dir,
                formats=config.output.formats,
                metadata=run_metadata,
            )

        if report_paths:
            paths_str = ", ".join(f"{k}={v}" for k, v in report_paths.items())
            print(f"レポート出力先: {paths_str}", flush=True)

        timing_summary = ", ".join(f"{k}={v:.3f}s" for k, v in rounded_timings.items())
        logger.debug(f"一括バックテストフェーズ別所要時間: {timing_summary}")
        print(f"フェーズ別所要時間: {timing_summary}", flush=True)

        return {
            "as_of_dates": sorted_dates,
            "batch_summary": batch_summary,
            "per_date_results": per_date_results,
            "report_paths": report_paths,
            "config": config,
            "timings_sec": rounded_timings,
            "workers_used": effective_workers,
        }


def _parse_date(value: str) -> date:
    """YYYY-MM-DD 形式の文字列を date 型へ変換する。"""
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"日付は YYYY-MM-DD 形式で指定してください: {value}"
        ) from e


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """コマンドライン引数をパースする。"""
    parser = argparse.ArgumentParser(
        description="Project Atlas 株式スクリーニング＆フォワードリターン検証パイプライン"
    )
    parser.add_argument(
        "--mode",
        choices=["screen", "evaluate", "backtest"],
        default="screen",
        help="実行モード（screen: スクリーニング / evaluate: フォワードリターン検証 / backtest: 複数基準日一括バックテスト）",
    )
    parser.add_argument(
        "--as-of-date",
        type=_parse_date,
        default=None,
        help="分析基準日 (YYYY-MM-DD)。evaluate モードでは必須",
    )
    parser.add_argument(
        "--as-of-dates",
        nargs="+",
        type=_parse_date,
        default=None,
        help="一括バックテスト用の複数基準日 (YYYY-MM-DD ...)。指定時は一括バックテストを実行",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="対象銘柄コード（例: 7203.T 6758.T）。未指定時はマスタから自動抽出",
    )
    parser.add_argument(
        "--start-date",
        type=_parse_date,
        default=None,
        help="OHLCV取得開始日 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=_parse_date,
        default=None,
        help="OHLCV取得終了日 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--fiscal-year",
        type=int,
        default=None,
        help="対象会計年度（例: 2025）",
    )
    parser.add_argument(
        "--horizons",
        nargs="+",
        type=int,
        default=None,
        help="evaluate / backtest モード時の検証ホライズン（営業日数、例: 5 20 60）",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="スクリーニング設定YAMLファイルのパス",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="レポート出力先ディレクトリ",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="JSON / Markdown レポートのファイル出力を無効化する",
    )
    parser.add_argument(
        "--use-pre-screening",
        action="store_true",
        help="--symbols 指定時にも事前スクリーニングフィルタを適用する",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="指標・特徴量のファイルキャッシュを読み書きしない",
    )
    parser.add_argument(
        "--use-feature-cache",
        action="store_true",
        help="特徴量のファイルキャッシュを読み書きする（デフォルト無効）",
    )
    parser.add_argument(
        "--update-master",
        action="store_true",
        help="JPXから最新の東証上場銘柄マスタを取得して更新する",
    )
    parser.add_argument(
        "--no-irbank-download",
        action="store_true",
        help="IR BANKからの新規財務データダウンロードを抑止する",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="並列評価ワーカープロセス数（未指定時は設定値を使用、1で逐次実行）",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="銘柄単位の詳細ログ（DEBUG）を表示する",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI エントリポイント"""
    args = parse_args(argv)
    try:
        if args.mode == "evaluate" and args.as_of_dates:
            raise ValueError(
                "--mode evaluate と --as-of-dates は併用できません。複数基準日のバックテストには --mode backtest を使用してください。"
            )
        if args.as_of_dates or args.mode == "backtest":
            resolved_dates = args.as_of_dates or (
                [args.as_of_date] if args.as_of_date is not None else None
            )
            if not resolved_dates:
                raise ValueError(
                    "backtest モードでは --as-of-dates（または --as-of-date）の指定が必須です。"
                )
            run_batch_backtest(
                as_of_dates=resolved_dates,
                symbols=args.symbols,
                start_date=args.start_date,
                end_date=args.end_date,
                fiscal_year=args.fiscal_year,
                config_path=args.config,
                output_dir=args.output_dir,
                export_reports=not args.no_export,
                use_pre_screening=args.use_pre_screening,
                horizons=args.horizons,
                use_cache=not args.no_cache,
                use_feature_cache=args.use_feature_cache,
                update_master=args.update_master,
                allow_irbank_download=not args.no_irbank_download,
                workers=args.workers,
                verbose=args.verbose,
            )
            return 0

        run_full_pipeline(
            symbols=args.symbols,
            start_date=args.start_date,
            end_date=args.end_date,
            fiscal_year=args.fiscal_year,
            as_of_date=args.as_of_date,
            config_path=args.config,
            output_dir=args.output_dir,
            export_reports=not args.no_export,
            use_pre_screening=args.use_pre_screening,
            mode=args.mode,
            horizons=args.horizons,
            use_cache=not args.no_cache,
            use_feature_cache=args.use_feature_cache,
            update_master=args.update_master,
            allow_irbank_download=not args.no_irbank_download,
            workers=args.workers,
            verbose=args.verbose,
        )
        return 0
    except Exception as e:
        logger.error(f"パイプライン実行に失敗しました: {e}")
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
