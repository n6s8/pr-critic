"""
Custom JSON observability logger.
Every agent event is appended to a .jsonl file (one JSON object per line)
AND returned as a dict so agents can include it in state["trace"].
The trace is returned in the API response — no external service needed.
"""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
_log = logging.getLogger("pr_critic")


def _log_file() -> Path:
    p = Path(settings.log_dir)
    p.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return p / f"pr_critic_{date}.jsonl"


def _write(event: dict) -> dict:
    with open(_log_file(), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    level = logging.WARNING if event["event"] == "error" else logging.INFO
    _log.log(level, "[%s] %s %s", event["agent"], event["event"], event.get("data", {}))
    return event


def record(agent: str, event_type: str, data: dict[str, Any],
           duration_ms: float | None = None) -> dict:
    ev: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "event": event_type,
        "data": data,
    }
    if duration_ms is not None:
        ev["duration_ms"] = round(duration_ms, 2)
    return _write(ev)


def log_start(agent: str, inputs: dict) -> dict:
    return record(agent, "start", inputs)


def log_end(agent: str, outputs: dict, duration_ms: float) -> dict:
    return record(agent, "end", outputs, duration_ms)


def log_error(agent: str, error: str) -> dict:
    return record(agent, "error", {"error": error})


def log_routing(decision: str, reason: str) -> dict:
    return record("router", "routing_decision",
                  {"decision": decision, "reason": reason})