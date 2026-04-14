"""Structured JSON logging and local trace persistence."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings


class JsonFormatter(logging.Formatter):
    """Render application logs as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for field in ("agent", "event", "request_id", "path", "method", "status_code"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            payload.update(extra)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def _log_file() -> Path:
    path = Path(settings.log_dir)
    path.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return path / f"pr_critic_{date}.jsonl"


def configure_logging() -> None:
    root = logging.getLogger()
    if any(getattr(handler, "_pr_critic_json", False) for handler in root.handlers):
        return

    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(JsonFormatter())
    stream_handler._pr_critic_json = True  # type: ignore[attr-defined]

    root.handlers = [stream_handler]


configure_logging()
_log = logging.getLogger("pr_critic")


def _write(event: dict) -> dict:
    with open(_log_file(), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    level = logging.ERROR if event["event"] == "error" else logging.INFO
    _log.log(
        level,
        f"{event['agent']}.{event['event']}",
        extra={
            "agent": event["agent"],
            "event": event["event"],
            "extra": event.get("data", {}),
        },
    )
    return event


def record(agent: str, event_type: str, data: dict[str, Any],
           duration_ms: float | None = None) -> dict:
    event: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "event": event_type,
        "data": data,
    }
    if duration_ms is not None:
        event["duration_ms"] = round(duration_ms, 2)
    return _write(event)


def log_structured(level: str, message: str, **fields: Any) -> None:
    level_no = getattr(logging, level.upper(), logging.INFO)
    _log.log(level_no, message, extra={"extra": fields})


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_start(agent: str, inputs: dict) -> dict:
    return record(agent, "start", inputs)


def log_end(agent: str, outputs: dict, duration_ms: float) -> dict:
    return record(agent, "end", outputs, duration_ms)


def log_error(agent: str, error: str) -> dict:
    return record(agent, "error", {"error": error})


def log_routing(decision: str, reason: str) -> dict:
    return record("router", "routing_decision", {"decision": decision, "reason": reason})
