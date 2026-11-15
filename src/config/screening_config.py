"""
YAMLベースのスクリーニング設定モデルおよびローダー
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml
from pydantic import BaseModel, Field, field_validator

from src.config.settings import Settings
from src.score_engine.scores.strategy import StrategyScoreConfig
from src.screener.pre_screener import PreScreeningCriteria
from src.screener.screener import ScreeningCriteria


class RankingConfig(BaseModel):
    """ランキング件数設定"""

    top_n: int = 20
    strategy_top_n: int = 10


class OutputConfig(BaseModel):
    """レポート出力設定"""

    output_dir: str = "./output"
    formats: List[str] = Field(default_factory=lambda: ["json", "markdown"])


class EvaluationConfig(BaseModel):
    """フォワードリターン検証設定"""

    horizons: List[int] = Field(default_factory=lambda: [5, 20, 60])
    entry_price_mode: str = "signal_close"

    @field_validator("horizons", mode="before")
    @classmethod
    def _validate_horizons(cls, value: Any) -> List[int]:
        if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set)):
            raise ValueError("horizons は整数のリストで指定してください。")
        items = list(value)
        if not items:
            raise ValueError("horizons は1つ以上の正の整数を指定してください。")
        cleaned: List[int] = []
        for item in items:
            if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
                raise ValueError(f"horizons の各要素は正の整数である必要があります: {item}")
            cleaned.append(item)
        return sorted(set(cleaned))

    @field_validator("entry_price_mode")
    @classmethod
    def _validate_entry_price_mode(cls, value: str) -> str:
        allowed = ("signal_close", "next_open")
        if value not in allowed:
            raise ValueError(
                f"entry_price_mode は {allowed} のいずれかを指定してください: {value}"
            )
        return value


class AtlasScreeningConfig(BaseModel):
    """Project Atlas スクリーニング統合設定モデル"""

    pre_screening: PreScreeningCriteria = Field(default_factory=PreScreeningCriteria)
    strategy_score: StrategyScoreConfig = Field(default_factory=StrategyScoreConfig)
    screener: ScreeningCriteria = Field(default_factory=ScreeningCriteria)
    ranking: RankingConfig = Field(default_factory=RankingConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)


def _normalize_partial_sections(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """空セクション（値が None）を空辞書に正規化し、Pydantic のデフォルト値マージを安全に行う。"""
    normalized: Dict[str, Any] = {}
    for key, value in raw_data.items():
        if value is None:
            normalized[key] = {}
        else:
            normalized[key] = value
    return normalized


def load_screening_config(
    config_path: Optional[Union[str, Path]] = None,
) -> AtlasScreeningConfig:
    """
    YAMLファイルからスクリーニング設定を読み込み、AtlasScreeningConfig を返す。
    - config_path が明示指定され、ファイルが存在しない場合は FileNotFoundError を送出する。
    - config_path が None の場合は Settings().SCREENING_CONFIG_PATH を参照し、
      ファイルが存在しない場合はデフォルト値の AtlasScreeningConfig() を返す。
    - 部分的な YAML 記述でも、未指定項目は各モデルのデフォルト値で補完される。
    """
    if config_path is not None:
        target_path = Path(config_path)
        if not target_path.exists():
            raise FileNotFoundError(f"設定ファイルが見つかりません: {target_path}")
    else:
        settings = Settings()
        target_path = Path(settings.SCREENING_CONFIG_PATH)
        if not target_path.exists():
            return AtlasScreeningConfig()

    with open(target_path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f)

    if raw_data is None:
        return AtlasScreeningConfig()

    if not isinstance(raw_data, dict):
        raise ValueError(
            f"設定ファイルのトップレベルはマッピング形式である必要があります: {target_path}"
        )

    cleaned_data = _normalize_partial_sections(raw_data)
    return AtlasScreeningConfig.model_validate(cleaned_data)
