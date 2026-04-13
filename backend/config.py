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


settings = Settings()