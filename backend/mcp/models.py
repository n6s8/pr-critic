from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PullRequestMetadata:
    url: str
    title: str
    author: str
    base_branch: str
    head_branch: str
    files_changed: list[str]
    language: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PullRequestDiff:
    url: str
    diff: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MCPToolCallRecord:
    tool: str
    transport: str
    latency_ms: float
    status: str
