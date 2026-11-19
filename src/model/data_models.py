
from datetime import date as DateType
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

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
