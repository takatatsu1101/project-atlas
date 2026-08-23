
from datetime import date
from typing import Dict, List, Any, Optional
from pydantic import BaseModel

class OhlcvModel(BaseModel):
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int

class FinancialModel(BaseModel):
    symbol: str
    fiscal_date: date
    eps: Optional[float] = None
    bps: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    per: Optional[float] = None
    pbr: Optional[float] = None
    revenue: Optional[float] = None
    operating_profit: Optional[float] = None
    net_profit: Optional[float] = None

class IndicatorSetModel(BaseModel):
    symbol: str
    date: date
    indicators: Dict[str, Any] # 例: {"MA5": 123.45, "MACD": {"macd": 1.2, "signal": 1.0}}

class FeatureResultModel(BaseModel):
    feature_id: str
    feature_name: str
    score: float # 正規化後スコア (0-100)
    raw_value: float # 元の計算値
    metadata: Dict[str, Any] = {}

class FeatureSetModel(BaseModel):
    symbol: str
    date: date
    results: List[FeatureResultModel]

class PatternResultModel(BaseModel):
    pattern_id: str
    pattern_name: str
    confidence: float # 検出信頼度 (0-100)
    metadata: Dict[str, Any] = {}

class PatternSetModel(BaseModel):
    symbol: str
    date: date
    results: List[PatternResultModel]

class ScoreResultModel(BaseModel):
    symbol: str
    date: date
    sub_scores: Dict[str, float]
    total_score: float
    metadata: Dict[str, Any] = {}

class AnalysisResultModel(BaseModel):
    symbol: str
    company_name: str = ""
    total_score: float
    feature_results: List[FeatureResultModel] = []
    pattern_results: List[PatternResultModel] = []
    rank: Optional[int] = None
    summary: Optional[str] = None
