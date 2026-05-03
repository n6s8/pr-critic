from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any


_LOCK = Lock()
_MAX_RECENT_ERRORS = 50
_MAX_FEEDBACK = 100


@dataclass
class MetricsRegistry:
    request_count: int = 0
    feedback_count: int = 0
    agent_runs: Counter[str] = field(default_factory=Counter)
    agent_errors: Counter[str] = field(default_factory=Counter)
    agent_latency_ms: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    estimated_input_tokens: Counter[str] = field(default_factory=Counter)
    estimated_output_tokens: Counter[str] = field(default_factory=Counter)
    estimated_cost_usd: Counter[str] = field(default_factory=Counter)
    retrieval_hit_count: Counter[str] = field(default_factory=Counter)
    cache_hits: Counter[str] = field(default_factory=Counter)
    cache_misses: Counter[str] = field(default_factory=Counter)
    mcp_tool_runs: Counter[str] = field(default_factory=Counter)
    mcp_tool_latency_ms: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    mcp_tool_errors: Counter[str] = field(default_factory=Counter)
    error_codes: Counter[str] = field(default_factory=Counter)
    recent_errors: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=_MAX_RECENT_ERRORS))
    feedback: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=_MAX_FEEDBACK))


_REGISTRY = MetricsRegistry()


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def estimate_llm_cost_usd(input_tokens: int, output_tokens: int) -> float:
    # Conservative local estimate for free/low-cost providers. The exact value is
    # less important than consistent cost visibility for capstone observability.
    return round(((input_tokens / 1_000_000) * 0.05) + ((output_tokens / 1_000_000) * 0.08), 6)


def record_request() -> None:
    with _LOCK:
        _REGISTRY.request_count += 1


def record_agent_run(agent: str, duration_ms: float | None, data: dict[str, Any] | None = None) -> None:
    payload = data or {}
    with _LOCK:
        _REGISTRY.agent_runs[agent] += 1
        if duration_ms is not None:
            _REGISTRY.agent_latency_ms[agent].append(float(duration_ms))
        input_tokens = int(payload.get("estimated_input_tokens") or payload.get("llm_input_tokens") or 0)
        output_tokens = int(payload.get("estimated_output_tokens") or payload.get("llm_output_tokens") or 0)
        if input_tokens:
            _REGISTRY.estimated_input_tokens[agent] += input_tokens
        if output_tokens:
            _REGISTRY.estimated_output_tokens[agent] += output_tokens
        if input_tokens or output_tokens:
            _REGISTRY.estimated_cost_usd[agent] += estimate_llm_cost_usd(input_tokens, output_tokens)
        if "hit_count" in payload:
            _REGISTRY.retrieval_hit_count[agent] += int(payload.get("hit_count") or 0)
        if payload.get("cache_hit") is True:
            _REGISTRY.cache_hits[agent] += 1
        elif payload.get("cache_hit") is False:
            _REGISTRY.cache_misses[agent] += 1


def record_agent_error(agent: str, error_code: str = "agent_error", details: dict[str, Any] | None = None) -> None:
    with _LOCK:
        _REGISTRY.agent_errors[agent] += 1
        _REGISTRY.error_codes[error_code] += 1
        _REGISTRY.recent_errors.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "agent": agent,
                "error_code": error_code,
                "details": details or {},
            }
        )


def record_mcp_tool_call(tool: str, latency_ms: float, *, status: str, transport: str) -> None:
    key = f"{transport}:{tool}"
    with _LOCK:
        _REGISTRY.mcp_tool_runs[key] += 1
        _REGISTRY.mcp_tool_latency_ms[key].append(latency_ms)
        if status != "completed":
            _REGISTRY.mcp_tool_errors[key] += 1


def record_feedback(rating: int, comment: str, review_id: str | None = None) -> dict[str, Any]:
    item = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "rating": rating,
        "comment": comment,
        "review_id": review_id,
    }
    with _LOCK:
        _REGISTRY.feedback_count += 1
        _REGISTRY.feedback.append(item)
    return item


def snapshot_metrics() -> dict[str, Any]:
    with _LOCK:
        agent_latency = {
            agent: {
                "count": _REGISTRY.agent_runs[agent],
                "avg_ms": _avg(values),
                "max_ms": round(max(values), 2) if values else 0.0,
            }
            for agent, values in _REGISTRY.agent_latency_ms.items()
        }
        mcp_latency = {
            tool: {
                "count": _REGISTRY.mcp_tool_runs[tool],
                "avg_ms": _avg(values),
                "max_ms": round(max(values), 2) if values else 0.0,
                "errors": _REGISTRY.mcp_tool_errors[tool],
            }
            for tool, values in _REGISTRY.mcp_tool_latency_ms.items()
        }
        return {
            "requests": _REGISTRY.request_count,
            "feedback_count": _REGISTRY.feedback_count,
            "agent_runs": dict(_REGISTRY.agent_runs),
            "agent_errors": dict(_REGISTRY.agent_errors),
            "agent_latency": agent_latency,
            "estimated_input_tokens": dict(_REGISTRY.estimated_input_tokens),
            "estimated_output_tokens": dict(_REGISTRY.estimated_output_tokens),
            "estimated_cost_usd": {
                agent: round(value, 6)
                for agent, value in _REGISTRY.estimated_cost_usd.items()
            },
            "retrieval_hit_count": dict(_REGISTRY.retrieval_hit_count),
            "cache_hits": dict(_REGISTRY.cache_hits),
            "cache_misses": dict(_REGISTRY.cache_misses),
            "mcp_tools": mcp_latency,
            "error_codes": dict(_REGISTRY.error_codes),
            "recent_errors": list(_REGISTRY.recent_errors),
            "feedback_recent": list(_REGISTRY.feedback),
        }
