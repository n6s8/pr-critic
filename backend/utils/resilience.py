from __future__ import annotations

from email.utils import parsedate_to_datetime
import random
import time
from typing import Any, Callable, Mapping, TypeVar

import httpx

from backend.config import settings
from backend.errors import LLMRateLimitError
from backend.observability.logger import log_structured

T = TypeVar("T")


def _extract_status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) is not None:
        return int(response.status_code)

    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        try:
            return int(status_code)
        except (TypeError, ValueError):
            return None

    return None


def _extract_headers(exc: Exception) -> Mapping[str, str]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        return headers

    direct_headers = getattr(exc, "headers", None)
    if direct_headers is not None:
        return direct_headers

    return {}


def _extract_error_text(exc: Exception) -> str:
    parts = [
        type(exc).__name__,
        str(getattr(exc, "message", "")),
        str(getattr(exc, "body", "")),
        str(exc),
    ]
    return " ".join(part for part in parts if part).lower()


def get_retry_delay_seconds(exc: Exception) -> float | None:
    headers = _extract_headers(exc)
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_after_at = parsedate_to_datetime(retry_after)
            except (TypeError, ValueError):
                retry_after_at = None
            if retry_after_at is not None:
                return max(0.0, retry_after_at.timestamp() - time.time())

    reset_at = headers.get("x-ratelimit-reset") or headers.get("X-RateLimit-Reset")
    if reset_at:
        try:
            return max(0.0, float(reset_at) - time.time())
        except ValueError:
            return None

    retry_after_seconds = getattr(exc, "retry_after", None)
    if retry_after_seconds is not None:
        try:
            return max(0.0, float(retry_after_seconds))
        except (TypeError, ValueError):
            return None

    return None


def is_retryable_github_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code if exc.response is not None else None
        # 403 = rate limit exceeded, 429 = too many requests
        # Both are retryable with backoff
        return status_code in {403, 408, 409, 425, 429} or (status_code is not None and status_code >= 500)

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


def is_llm_rate_limit_error(exc: Exception) -> bool:
    status_code = _extract_status_code(exc)
    if status_code == 429:
        return True

    error_text = _extract_error_text(exc)
    error_code = str(getattr(exc, "code", "")).lower()
    return (
        "rate limit" in error_text
        or "too many requests" in error_text
        or "ratelimit" in error_text
        or error_code in {"rate_limit", "rate_limit_exceeded", "too_many_requests"}
    )


def is_retryable_llm_error(exc: Exception) -> bool:
    if is_llm_rate_limit_error(exc):
        return True

    status_code = _extract_status_code(exc)
    if status_code in {408, 409, 425}:
        return True
    if status_code is not None and status_code >= 500:
        return True

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
    delay_resolver: Callable[[Exception], float | None] | None = None,
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
                delay * (2 ** (attempt - 1)) + random.uniform(0.0, delay),
                retry_policy.max_backoff_seconds,
            )
            provider_delay = delay_resolver(exc) if delay_resolver else None
            if provider_delay is not None:
                sleep_seconds = min(max(0.0, provider_delay), retry_policy.max_backoff_seconds)

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    raise RuntimeError(f"{service}:{operation_name} exhausted retries without raising a terminal error")


def invoke_llm(llm: Any, messages: list[Any], *, agent: str, attempts: int | None = None) -> Any:
    try:
        return retry_call(
            lambda: llm.invoke(messages),
            service="llm",
            operation_name=agent,
            should_retry=is_retryable_llm_error,
            delay_resolver=get_retry_delay_seconds,
            attempts=attempts,
            context={"agent": agent},
        )
    except Exception as exc:
        if is_llm_rate_limit_error(exc):
            retry_after_seconds = get_retry_delay_seconds(exc)
            raise LLMRateLimitError(
                retry_after_seconds=retry_after_seconds,
                details={"agent": agent},
            ) from exc
        raise
