
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # 環境設定
    APP_ENV: str = "development"
    DEBUG_MODE: bool = True

    # データ収集設定
    DATA_SOURCE_API_KEY: str = "your_api_key"
    DATA_CACHE_DIR: str = "./data/cache"
    DATA_FINANCIAL_DIR: str = "./data/financial"
    DATA_MASTER_DIR: str = "./data/master"
    FINANCIAL_DISCLOSURE_LAG_DAYS: int = 60

    # データベース設定
    DATABASE_URL: str = "sqlite:///./data/app.db"

    # スクリーニング設定・出力設定
    SCREENING_CONFIG_PATH: str = "./config/screening.yaml"
    OUTPUT_DIR: str = "./output"

    # その他の設定（必要に応じて追加）
    # 例えば、特徴量計算の並列処理設定など
    FEATURE_ENGINE_PARALLEL_PROCESSES: int = 4

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

def load_settings(env: str = "development") -> Settings:
    """
    環境に応じた設定をロードする。
    """
    # .env ファイルから設定を読み込む
    # 環境変数を上書きすることも可能
    return Settings(APP_ENV=env)
