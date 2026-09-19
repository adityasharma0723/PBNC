"""Application configuration via pydantic-settings.

All config is read from environment variables or a .env file.
Secrets (SECRET_KEY, LLM_API_KEY) must never be committed to the repo.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application ---
    APP_NAME: str = "DocIntel"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me"
    JWT_EXPIRY_MINUTES: int = 60
    JWT_ALGORITHM: str = "HS256"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://docintel:docintel@db:5432/docintel"
    DATABASE_URL_SYNC: str = "postgresql://docintel:docintel@db:5432/docintel"

    # --- Redis ---
    REDIS_URL: str = "redis://redis:6379/0"

    # --- LLM / Extractor ---
    EXTRACTOR: str = "fake"  # "llm" or "fake"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gemini-2.0-flash"
    LLM_TIMEOUT: int = 60
    LLM_MAX_RETRIES: int = 3
    LLM_CONCURRENCY: int = 4

    # --- Upload limits ---
    MAX_UPLOAD_SIZE_MB: int = 50
    MAX_PAGES: int = 200

    # --- Processing ---
    RENDER_DPI: int = 200
    MIN_TEXT_CHARS: int = 50
    CELERY_CONCURRENCY: int = 4

    # --- Confidence thresholds ---
    CONFIDENCE_HIGH: float = 0.80
    CONFIDENCE_LOW: float = 0.50

    # --- Rate limiting (requests per window) ---
    LOGIN_RATE_LIMIT: str = "10/minute"
    UPLOAD_RATE_LIMIT: str = "20/minute"

    # --- Storage ---
    UPLOAD_DIR: str = "/app/uploads"

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


settings = Settings()
