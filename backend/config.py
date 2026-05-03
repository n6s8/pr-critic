from __future__ import annotations

from functools import cached_property
from typing import Any, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProfile(BaseModel):
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: float
    max_retries: int = 0

    def groq_kwargs(self, *, api_key: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "api_key": api_key,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout_seconds,
            "max_retries": self.max_retries,
        }


class ModelProfiles(BaseModel):
    review: LLMProfile
    branch: LLMProfile
    critic: LLMProfile
    selector: LLMProfile


class RetryPolicy(BaseModel):
    attempts: int
    base_delay_seconds: float
    max_backoff_seconds: float


class ThresholdPolicy(BaseModel):
    branch_score_threshold: int
    max_branch_alternatives: int


class CachePolicy(BaseModel):
    pr_ttl_seconds: int
    rag_ttl_seconds: int


class APISettings(BaseModel):
    cors_allowed_origins: list[str]


class RateLimitPolicy(BaseModel):
    requests: int
    window_seconds: int


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = Field(..., validation_alias="GROQ_API_KEY")
    github_token: Optional[str] = Field(default=None, validation_alias="GITHUB_TOKEN")
    app_env: str = Field(default="development", validation_alias="APP_ENV")

    generation_model: str = Field(default="llama-3.1-8b-instant", validation_alias="GENERATION_MODEL")
    reasoning_model: str = Field(default="llama-3.1-8b-instant", validation_alias="REASONING_MODEL")

    review_temperature: float = Field(default=0.2, validation_alias="REVIEW_TEMPERATURE")
    branch_temperature: float = Field(default=0.5, validation_alias="BRANCH_TEMPERATURE")
    critic_temperature: float = Field(default=0.1, validation_alias="CRITIC_TEMPERATURE")
    selector_temperature: float = Field(default=0.1, validation_alias="SELECTOR_TEMPERATURE")

    review_max_tokens: int = Field(default=1200, validation_alias="REVIEW_MAX_TOKENS")
    branch_max_tokens: int = Field(default=1200, validation_alias="BRANCH_MAX_TOKENS")
    critic_max_tokens: int = Field(default=512, validation_alias="CRITIC_MAX_TOKENS")
    selector_max_tokens: int = Field(default=256, validation_alias="SELECTOR_MAX_TOKENS")
    llm_max_retries: int = Field(default=0, validation_alias="LLM_MAX_RETRIES")

    branch_score_threshold: int = Field(default=7, validation_alias="BRANCH_SCORE_THRESHOLD")
    max_branch_alternatives: int = Field(default=2, validation_alias="MAX_BRANCH_ALTERNATIVES")

    chroma_dir: str = Field(default="data/chroma", validation_alias="CHROMA_DIR")
    log_dir: str = Field(default="logs", validation_alias="LOG_DIR")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    llm_timeout_seconds: float = Field(default=45.0, validation_alias="LLM_TIMEOUT_SECONDS")
    github_timeout_seconds: float = Field(default=20.0, validation_alias="GITHUB_TIMEOUT_SECONDS")
    repo_signal_timeout_seconds: float = Field(default=20.0, validation_alias="REPO_SIGNAL_TIMEOUT_SECONDS")
    mcp_transport: str = Field(default="inprocess", validation_alias="MCP_TRANSPORT")
    api_key: Optional[str] = Field(default=None, validation_alias="PR_CRITIC_API_KEY")
    max_review_input_chars: int = Field(default=200_000, validation_alias="MAX_REVIEW_INPUT_CHARS")

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
    cache_backend: str = Field(default="memory", validation_alias="CACHE_BACKEND")
    cors_allowed_origins_raw: str = Field(
        default=(
            "https://pr-critic.vercel.app,"
            "http://localhost:5173,"
            "http://127.0.0.1:5173,"
            "http://localhost:3000"
        ),
        validation_alias="CORS_ALLOWED_ORIGINS",
    )

    @cached_property
    def models(self) -> ModelProfiles:
        timeout = self.llm_timeout_seconds
        retries = self.llm_max_retries
        return ModelProfiles(
            review=LLMProfile(
                model=self.generation_model,
                temperature=self.review_temperature,
                max_tokens=self.review_max_tokens,
                timeout_seconds=timeout,
                max_retries=retries,
            ),
            branch=LLMProfile(
                model=self.generation_model,
                temperature=self.branch_temperature,
                max_tokens=self.branch_max_tokens,
                timeout_seconds=timeout,
                max_retries=retries,
            ),
            critic=LLMProfile(
                model=self.reasoning_model,
                temperature=self.critic_temperature,
                max_tokens=self.critic_max_tokens,
                timeout_seconds=timeout,
                max_retries=retries,
            ),
            selector=LLMProfile(
                model=self.reasoning_model,
                temperature=self.selector_temperature,
                max_tokens=self.selector_max_tokens,
                timeout_seconds=timeout,
                max_retries=retries,
            ),
        )

    @cached_property
    def retries(self) -> RetryPolicy:
        return RetryPolicy(
            attempts=self.external_api_retries,
            base_delay_seconds=self.external_api_retry_backoff_seconds,
            max_backoff_seconds=self.external_api_max_backoff_seconds,
        )

    @cached_property
    def thresholds(self) -> ThresholdPolicy:
        return ThresholdPolicy(
            branch_score_threshold=self.branch_score_threshold,
            max_branch_alternatives=self.max_branch_alternatives,
        )

    @cached_property
    def caches(self) -> CachePolicy:
        return CachePolicy(
            pr_ttl_seconds=self.pr_cache_ttl_seconds,
            rag_ttl_seconds=self.rag_cache_ttl_seconds,
        )

    @cached_property
    def rate_limit(self) -> RateLimitPolicy:
        return RateLimitPolicy(
            requests=self.rate_limit_requests,
            window_seconds=self.rate_limit_window_seconds,
        )

    @cached_property
    def api(self) -> APISettings:
        origins = [
            origin.strip()
            for origin in self.cors_allowed_origins_raw.split(",")
            if origin.strip()
        ]
        return APISettings(cors_allowed_origins=origins)


settings = Settings()
