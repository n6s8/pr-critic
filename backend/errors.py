from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PRCriticError(Exception):
    message: str
    status_code: int = 500
    code: str = "internal_error"
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)


class UpstreamFetchError(PRCriticError):
    pass


class LLMServiceError(PRCriticError):
    pass


class LLMRateLimitError(LLMServiceError):
    def __init__(
        self,
        message: str = "LLM unavailable due to rate limit",
        *,
        retry_after_seconds: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = dict(details or {})
        if retry_after_seconds is not None:
            merged_details["retry_after_seconds"] = retry_after_seconds

        super().__init__(
            message=message,
            status_code=503,
            code="llm_rate_limited",
            details=merged_details,
        )
        self.retry_after_seconds = retry_after_seconds
