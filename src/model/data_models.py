
from datetime import date as DateType, datetime
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

class OhlcvModel(BaseModel):
    symbol: str
    date: DateType
    open: float
    high: float
    low: float
    close: float
    volume: int

class FinancialModel(BaseModel):
    symbol: str
    fiscal_date: DateType
    eps: Optional[float] = None
    bps: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    per: Optional[float] = None
    pbr: Optional[float] = None
    revenue: Optional[float] = None
    operating_profit: Optional[float] = None
    net_profit: Optional[float] = None
    revenue_growth: Optional[float] = None
    net_profit_growth: Optional[float] = None
    revenue_growth_3y_avg: Optional[float] = None
    revenue_growth_5y_avg: Optional[float] = None
    net_profit_growth_3y_avg: Optional[float] = None
    net_profit_growth_5y_avg: Optional[float] = None
    total_assets: Optional[float] = None  # 総資産
    equity_ratio: Optional[float] = None  # 自己資本比率
    # BS 未抽出列
    net_assets: Optional[float] = None  # 純資産
    shareholders_equity: Optional[float] = None  # 株主資本
    retained_earnings: Optional[float] = None  # 利益剰余金
    short_term_debt: Optional[float] = None  # 短期借入金
    long_term_debt: Optional[float] = None  # 長期借入金
    # PL 未抽出列
    ordinary_profit: Optional[float] = None  # 経常利益
    # キャッシュフロー (CF) データ
    operating_cf: Optional[float] = None  # 営業CF
    investing_cf: Optional[float] = None  # 投資CF
    financing_cf: Optional[float] = None  # 財務CF
    capex: Optional[float] = None  # 設備投資（IR BANK 原値は通常負数）
    free_cash_flow: Optional[float] = None  # フリーCF（operating_cf - abs(capex)）
    cash_and_equivalents: Optional[float] = None  # 現金及び現金同等物
    operating_cf_margin: Optional[float] = None  # 営業CFマージン（%）
    # 株主還元データ
    dividend_per_share: Optional[float] = None  # 一株配当
    total_dividends: Optional[float] = None  # 剰余金の配当
    share_buyback: Optional[float] = None  # 自社株買い
    payout_ratio: Optional[float] = None  # 配当性向（%）
    total_payout_ratio: Optional[float] = None  # 総還元性向（%）
    doe: Optional[float] = None  # 純資産配当率（%）
    # 複数年株主還元モメンタム
    consecutive_dividend_increase_years: Optional[int] = None  # 連続増配年数
    consecutive_non_decrease_years: Optional[int] = None  # 連続非減配年数
    buyback_count_3y: Optional[int] = None  # 直近3期自社株買い実施回数


class StockMasterModel(BaseModel):
    """東証上場銘柄マスタモデル"""
    code: str  # 4桁銘柄コード（例: "7203", "130A"）
    symbol: str  # ティッカー（例: "7203.T"）
    name: str  # 銘柄名
    market: str  # 市場区分（"プライム", "スタンダード", "グロース" 等）
    sector_33: Optional[str] = None  # 33業種区分
    sector_17: Optional[str] = None  # 17業種区分
    scale: Optional[str] = None  # 規模区分

class IndicatorSetModel(BaseModel):
    symbol: str
    date: DateType
    indicators: Dict[str, Any] # 例: {"MA5": 123.45, "MACD": {"macd": 1.2, "signal": 1.0}}

class FeatureResultModel(BaseModel):
    feature_id: str
    feature_name: str
    score: float # 正規化後スコア (0-100)
    raw_value: float # 元の計算値
    metadata: Dict[str, Any] = {}
    date: Optional[DateType] = None

class FeatureSetModel(BaseModel):
    symbol: str
    date: DateType
    results: List[FeatureResultModel]

class PatternResultModel(BaseModel):
    pattern_id: str
    pattern_name: str
    confidence: float # 検出信頼度 (0-100)
    metadata: Dict[str, Any] = {}

class PatternSetModel(BaseModel):
    symbol: str
    date: DateType
    results: List[PatternResultModel]

class ScoreResultModel(BaseModel):
    symbol: str
    date: DateType
    score_id: str = "S001_OverallScore"  # スコア識別子を追加
    sub_scores: Dict[str, float]
    total_score: float
    metadata: Dict[str, Any] = {}
    strategy_type: str = "watch"  # 推奨戦略タイプ（"pullback" / "breakout" / "watch"）
    reasons: List[str] = Field(default_factory=list)  # 評価根拠の日本語メッセージリスト
    key_levels: Dict[str, Optional[float]] = Field(default_factory=dict)  # 主要価格水準・乖離率
    risk_metrics: Dict[str, Optional[float]] = Field(default_factory=dict)  # ボラティリティ・出来高等のリスク指標

class AnalysisResultModel(BaseModel):
    symbol: str
    company_name: str = ""
    total_score: float
    feature_results: List[FeatureResultModel] = []
    pattern_results: List[PatternResultModel] = []
    rank: Optional[int] = None
    summary: Optional[str] = None
    date: Optional[DateType] = None  # 分析基準日
    market: str = ""  # 市場区分
    sector: str = ""  # 業種
    strategy_type: str = "watch"  # 推奨戦略タイプ（"pullback" / "breakout" / "watch"）
    sub_scores: Dict[str, float] = Field(default_factory=dict)  # サブスコア内訳
    reasons: List[str] = Field(default_factory=list)  # 評価根拠リスト
    key_levels: Dict[str, Optional[float]] = Field(default_factory=dict)  # 主要価格水準・乖離率
    risk_metrics: Dict[str, Optional[float]] = Field(default_factory=dict)  # リスク指標
    financial_summary: Dict[str, Optional[float]] = Field(default_factory=dict)  # 財務サマリー


class HorizonMetricsModel(BaseModel):
    """個別ホライズン（営業日ベース）のフォワードリターン評価指標モデル"""

    horizon_days: int
    available: bool = False
    target_date: Optional[DateType] = None
    exit_close: Optional[float] = None
    return_pct: Optional[float] = None
    mfe_pct: Optional[float] = None
    mae_pct: Optional[float] = None
    is_win: Optional[bool] = None


class ForwardEvaluationItemModel(BaseModel):
    """銘柄単位のフォワードリターン検証結果モデル"""

    symbol: str
    company_name: str = ""
    market: str = ""
    sector: str = ""
    strategy_type: str = "watch"
    rank: Optional[int] = None
    total_score: float = 0.0
    signal_date: Optional[DateType] = None
    entry_price: Optional[float] = None
    horizons: Dict[int, HorizonMetricsModel] = Field(default_factory=dict)
    status: str = "evaluated"  # "evaluated" / "no_forward_data" / "missing_entry_price"


class HorizonSummaryModel(BaseModel):
    """ホライズン別の検証サマリー統計モデル"""

    horizon_days: int
    total_candidates: int = 0
    evaluated_count: int = 0
    win_count: int = 0
    win_rate_pct: Optional[float] = None
    avg_return_pct: Optional[float] = None
    median_return_pct: Optional[float] = None
    avg_mfe_pct: Optional[float] = None
    avg_mae_pct: Optional[float] = None
    best_symbol: Optional[str] = None
    best_return_pct: Optional[float] = None
    worst_symbol: Optional[str] = None
    worst_return_pct: Optional[float] = None


class FeatureQuantileRowModel(BaseModel):
    """特徴量別分位評価（上位20% vs 下位20%）の1行分サマリーモデル"""

    feature_id: str
    feature_name: str = ""
    horizon_days: int
    total_samples: int = 0
    unique_score_count: int = 0
    top_count: int = 0
    top_win_rate_pct: Optional[float] = None
    top_avg_return_pct: Optional[float] = None
    top_avg_mfe_pct: Optional[float] = None
    top_avg_mae_pct: Optional[float] = None
    bottom_count: int = 0
    bottom_win_rate_pct: Optional[float] = None
    bottom_avg_return_pct: Optional[float] = None
    bottom_avg_mfe_pct: Optional[float] = None
    bottom_avg_mae_pct: Optional[float] = None
    spread_return_pct: Optional[float] = None
    spread_win_rate_pct: Optional[float] = None


class SymbolMarketSnapshot(BaseModel):
    """個別銘柄の基準日時点スナップショット（MarketContext 横断集計用軽量モデル）"""

    symbol: str
    bar_date: Optional[DateType] = None
    close: Optional[float] = None
    sma25: Optional[float] = None
    above_sma25: Optional[bool] = None
    return_20d: Optional[float] = None
    return_60d: Optional[float] = None
    return_120d: Optional[float] = None
    per: Optional[float] = None
    pbr: Optional[float] = None
    roe: Optional[float] = None


class BenchmarkMetricsModel(BaseModel):
    """市場ベンチマーク（例: 1306.T）の基準日時点指標モデル（読み取り専用）"""

    model_config = ConfigDict(frozen=True)

    symbol: str = "1306.T"
    available: bool = False
    bar_date: Optional[DateType] = None
    close: Optional[float] = None
    sma25: Optional[float] = None
    sma75: Optional[float] = None
    above_sma25: Optional[bool] = None
    above_sma75: Optional[bool] = None
    return_20d: Optional[float] = None
    return_60d: Optional[float] = None
    return_120d: Optional[float] = None


class SectorMetricsModel(BaseModel):
    """33業種ごとのモメンタム・騰落統計モデル（読み取り専用）"""

    model_config = ConfigDict(frozen=True)

    sector_33: str
    member_count: int = 0
    is_sufficient: bool = False
    avg_return_20d: Optional[float] = None
    above_sma25_ratio: Optional[float] = None
    sector_return_percentile: Optional[float] = None
    sector_momentum_score: Optional[float] = None


class SymbolMarketMetricsModel(BaseModel):
    """銘柄別の対市場相対力・業種モメンタム・業種内相対バリュエーション評価モデル（読み取り専用）"""

    model_config = ConfigDict(frozen=True)

    symbol: str
    bar_date: Optional[DateType] = None
    sector_33: Optional[str] = None
    return_20d: Optional[float] = None
    return_60d: Optional[float] = None
    return_120d: Optional[float] = None
    excess_return_20d: Optional[float] = None
    excess_return_60d: Optional[float] = None
    excess_return_120d: Optional[float] = None
    composite_excess_return: Optional[float] = None
    rs_percentile: Optional[float] = None
    sector_momentum_score: Optional[float] = None
    relative_valuation_z: Optional[float] = None
    relative_valuation_score: Optional[float] = None
    rs_adjustment: float = 0.0
    sector_momentum_adjustment: float = 0.0
    relative_valuation_adjustment: float = 0.0
    pullback_adjustment: Optional[float] = None
    breakout_adjustment: Optional[float] = None
    total_adjustment: float = 0.0


class MarketContextModel(BaseModel):
    """基準日断面のユニバース横断コンテキスト（読み取り専用）"""

    model_config = ConfigDict(frozen=True)

    as_of_date: DateType
    is_active: bool = False
    inactive_reason: Optional[str] = None
    universe_size: int = 0
    valid_sma25_count: int = 0
    above_sma25_count: int = 0
    breadth_ratio: Optional[float] = None
    universe_median_return_20d: Optional[float] = None
    universe_median_return_60d: Optional[float] = None
    universe_median_return_120d: Optional[float] = None
    regime: str = "unknown"
    breakout_threshold_delta: float = 0.0
    breakout_score_penalty: float = 0.0
    benchmark: BenchmarkMetricsModel = Field(default_factory=BenchmarkMetricsModel)
    sector_metrics: Dict[str, SectorMetricsModel] = Field(default_factory=dict)
    symbol_metrics: Dict[str, SymbolMarketMetricsModel] = Field(default_factory=dict)

    def to_regime_summary(self) -> Dict[str, Any]:
        """地合いレジーム・ベンチマーク状態のサマリー辞書を返す。"""
        as_of_norm = (
            self.as_of_date.date()
            if isinstance(self.as_of_date, datetime)
            else self.as_of_date
        )
        return {
            "as_of_date": as_of_norm.isoformat(),
            "is_active": self.is_active,
            "regime": self.regime,
            "universe_size": self.universe_size,
            "breadth_ratio": self.breadth_ratio,
            "breakout_threshold_delta": self.breakout_threshold_delta,
            "breakout_score_penalty": self.breakout_score_penalty,
            "benchmark_symbol": self.benchmark.symbol,
            "benchmark_available": self.benchmark.available,
            "benchmark_above_sma25": self.benchmark.above_sma25,
            "benchmark_above_sma75": self.benchmark.above_sma75,
            "benchmark_return_20d": self.benchmark.return_20d,
            "benchmark_return_60d": self.benchmark.return_60d,
        }


class EvaluationSummaryModel(BaseModel):
    """フォワードリターン検証全体のサマリーモデル"""

    as_of_date: DateType
    horizons: List[int]
    entry_price_mode: str = "signal_close"
    total_candidates: int = 0
    overall_summary: Dict[int, HorizonSummaryModel] = Field(default_factory=dict)
    strategy_summary: Dict[str, Dict[int, HorizonSummaryModel]] = Field(default_factory=dict)
    items: List[ForwardEvaluationItemModel] = Field(default_factory=list)
    passed_total_candidates: int = 0
    passed_overall_summary: Dict[int, HorizonSummaryModel] = Field(default_factory=dict)
    passed_strategy_summary: Dict[str, Dict[int, HorizonSummaryModel]] = Field(default_factory=dict)
    feature_quantile_summary: Dict[str, Dict[int, FeatureQuantileRowModel]] = Field(default_factory=dict)
    market_regime_summary: Optional[Dict[str, Any]] = None


class BatchBacktestSummaryModel(BaseModel):
    """複数基準日一括バックテストの横断集計サマリーモデル"""

    as_of_dates: List[DateType]
    horizons: List[int]
    entry_price_mode: str = "signal_close"
    total_dates: int = 0
    total_candidates: int = 0
    aggregated_overall_summary: Dict[int, HorizonSummaryModel] = Field(default_factory=dict)
    aggregated_strategy_summary: Dict[str, Dict[int, HorizonSummaryModel]] = Field(default_factory=dict)
    per_date_summaries: Dict[DateType, EvaluationSummaryModel] = Field(default_factory=dict)
    passed_total_candidates: int = 0
    aggregated_passed_overall_summary: Dict[int, HorizonSummaryModel] = Field(default_factory=dict)
    aggregated_passed_strategy_summary: Dict[str, Dict[int, HorizonSummaryModel]] = Field(default_factory=dict)
    aggregated_feature_quantile_summary: Dict[str, Dict[int, FeatureQuantileRowModel]] = Field(default_factory=dict)
