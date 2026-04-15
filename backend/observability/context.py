"""Request-scoped observability context shared across API and agents."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator


_REQUEST_CONTEXT: ContextVar[dict[str, Any]] = ContextVar(
    "pr_critic_request_context",
    default={},
)


def get_request_context() -> dict[str, Any]:
    return dict(_REQUEST_CONTEXT.get())


def get_request_id(default: str | None = None) -> str | None:
    return get_request_context().get("request_id", default)


@contextmanager
def request_context_scope(**fields: Any) -> Iterator[dict[str, Any]]:
    current = get_request_context()
    merged = {**current, **{key: value for key, value in fields.items() if value is not None}}
    token: Token[dict[str, Any]] = _REQUEST_CONTEXT.set(merged)
    try:
        yield merged
    finally:
        _REQUEST_CONTEXT.reset(token)
