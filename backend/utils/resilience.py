from __future__ import annotations

import time
from typing import Any, Callable, TypeVar

import httpx

from backend.config import settings
from backend.observability.logger import log_structured

T = TypeVar("T")


def is_retryable_github_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code if exc.response is not None else None
        return status_code in {408, 409, 425, 429} or (status_code is not None and status_code >= 500)

    return isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
            httpx.ReadError,
            httpx.WriteError,
        ),
    )


def retry_call(
    operation: Callable[[], T],
    *,
    service: str,
    operation_name: str,
    should_retry: Callable[[Exception], bool] | None = None,
    attempts: int | None = None,
    base_delay_seconds: float | None = None,
    context: dict[str, Any] | None = None,
) -> T:
    retry_policy = settings.retries
    max_attempts = max(1, attempts or retry_policy.attempts)
    delay = max(0.0, base_delay_seconds or retry_policy.base_delay_seconds)
    fields = dict(context or {})

    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as exc:
            retryable = attempt < max_attempts and (should_retry(exc) if should_retry else True)
            log_structured(
                "WARNING" if retryable else "ERROR",
                "external_call_failed",
                service=service,
                operation=operation_name,
                attempt=attempt,
                max_attempts=max_attempts,
                retryable=retryable,
                error_type=type(exc).__name__,
                error=str(exc),
                **fields,
            )
            if not retryable:
                raise

            sleep_seconds = min(
                delay * (2 ** (attempt - 1)),
                retry_policy.max_backoff_seconds,
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    raise RuntimeError(f"{service}:{operation_name} exhausted retries without raising a terminal error")


def invoke_llm(llm: Any, messages: list[Any], *, agent: str) -> Any:
    return retry_call(
        lambda: llm.invoke(messages),
        service="llm",
        operation_name=agent,
        should_retry=lambda exc: True,
        context={"agent": agent},
    )
