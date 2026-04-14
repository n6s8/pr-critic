from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = Field(..., validation_alias="GROQ_API_KEY")

    # Optional — needed for private repos, raises rate limit to 5000/hr
    github_token: Optional[str] = Field(default=None, validation_alias="GITHUB_TOKEN")

    generation_model: str = "llama-3.1-8b-instant"
    reasoning_model: str = "llama-3.1-8b-instant"

    branch_score_threshold: int = Field(default=7, validation_alias="BRANCH_SCORE_THRESHOLD")
    max_branch_alternatives: int = Field(default=2, validation_alias="MAX_BRANCH_ALTERNATIVES")

    chroma_dir: str = Field(default="data/chroma", validation_alias="CHROMA_DIR")
    log_dir: str = Field(default="logs", validation_alias="LOG_DIR")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    llm_timeout_seconds: float = Field(default=45.0, validation_alias="LLM_TIMEOUT_SECONDS")
    github_timeout_seconds: float = Field(default=20.0, validation_alias="GITHUB_TIMEOUT_SECONDS")
    external_api_retries: int = Field(default=3, validation_alias="EXTERNAL_API_RETRIES")
    external_api_retry_backoff_seconds: float = Field(
        default=0.5,
        validation_alias="EXTERNAL_API_RETRY_BACKOFF_SECONDS",
    )
    external_api_max_backoff_seconds: float = Field(
        default=4.0,
        validation_alias="EXTERNAL_API_MAX_BACKOFF_SECONDS",
    )
    rate_limit_requests: int = Field(default=30, validation_alias="RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(default=60, validation_alias="RATE_LIMIT_WINDOW_SECONDS")
    pr_cache_ttl_seconds: int = Field(default=120, validation_alias="PR_CACHE_TTL_SECONDS")
    rag_cache_ttl_seconds: int = Field(default=300, validation_alias="RAG_CACHE_TTL_SECONDS")


settings = Settings()
