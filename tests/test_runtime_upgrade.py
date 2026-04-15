import asyncio
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test_key")

from backend.api.main import app
from backend.graph.state import build_initial_state, build_request_context
from backend.observability.context import get_request_id
from backend.services.review_runtime import run_review_pipeline_async
from backend.utils.cache import TTLCache


def test_build_initial_state_keeps_request_context():
    request_context = build_request_context(
        "req-123",
        execution_mode="async_threadpool",
        route_path="/review",
    )

    state = build_initial_state("mock://pr/security-issue", request_context=request_context)

    assert state["pr_url"] == "mock://pr/security-issue"
    assert state["request_context"]["request_id"] == "req-123"
    assert state["request_context"]["execution_mode"] == "async_threadpool"
    assert state["trace"] == []


def test_run_review_pipeline_async_preserves_request_context_and_isolates_input():
    initial = build_initial_state(
        "mock://pr/security-issue",
        request_context=build_request_context("req-456", execution_mode="async_threadpool"),
    )
    captured: dict[str, str] = {}

    def fake_invoke(state):
        request_id = get_request_id()
        captured["request_id"] = request_id or "missing"
        state["trace"].append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "agent": "runtime_test",
                "event": "end",
                "data": {},
                "request_id": request_id or "missing",
            }
        )
        return state

    with patch("backend.services.review_runtime.compiled_graph.invoke", side_effect=fake_invoke):
        result = asyncio.run(run_review_pipeline_async(initial))

    assert captured["request_id"] == "req-456"
    assert initial["trace"] == []
    assert result["trace"][0]["request_id"] == "req-456"


def test_ttl_cache_returns_isolated_copies():
    cache: TTLCache[dict[str, list[int]]] = TTLCache("test_cache", ttl_seconds=60)
    cache.set("item", {"values": [1]})

    hit, cached = cache.get("item")

    assert hit is True
    assert cached is not None
    cached["values"].append(2)

    second_hit, second_cached = cache.get("item")

    assert second_hit is True
    assert second_cached == {"values": [1]}


def test_ttl_cache_single_flight_computes_once_for_concurrent_requests():
    cache: TTLCache[dict[str, int]] = TTLCache("single_flight", ttl_seconds=60)
    barrier = threading.Barrier(3)
    counter_lock = threading.Lock()
    call_count = 0
    results: list[tuple[dict[str, int], bool]] = []

    def factory() -> dict[str, int]:
        nonlocal call_count
        with counter_lock:
            call_count += 1
        time.sleep(0.1)
        return {"value": 1}

    def worker() -> None:
        barrier.wait()
        results.append(cache.get_or_compute("shared-key", factory))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()

    barrier.wait()

    for thread in threads:
        thread.join()

    assert call_count == 1
    assert len(results) == 2
    assert sorted(result[1] for result in results) == [False, True]
    assert all(result[0] == {"value": 1} for result in results)


def test_review_endpoint_propagates_request_id_without_changing_response_shape():
    captured: dict[str, dict] = {}
    best_candidate = {
        "review": "## Issues Found\n- [CRITICAL] auth.py:5 SQL injection\n\n## Verdict\nREQUEST_CHANGES",
        "strategy": "initial",
        "score": 8.5,
        "score_rationale": "Strong coverage",
        "issues": [],
    }

    async def fake_run(initial_state):
        captured["initial_state"] = initial_state
        return {
            **initial_state,
            "pr_metadata": {
                "files_changed": ["auth.py"],
                "language": "Python",
            },
            "candidates": [best_candidate],
            "best_candidate": best_candidate,
            "trace": [
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "agent": "fetch_agent",
                    "event": "end",
                    "data": {"language": "Python", "diff_length": 42},
                    "request_id": initial_state["request_context"]["request_id"],
                }
            ],
        }

    async def exercise_route():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/review", json={"pr_url": "mock://pr/security-issue"})

    with patch("backend.api.main.run_review_pipeline_async", side_effect=fake_run):
        response = asyncio.run(exercise_route())

    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]
    assert captured["initial_state"]["request_context"]["request_id"] == request_id
    assert captured["initial_state"]["request_context"]["execution_mode"] == "async_threadpool"

    payload = response.json()
    assert set(payload) == {"score", "strategies", "selected_strategy", "review", "issues", "trace"}
    assert payload["selected_strategy"] == "initial"
    assert payload["score"] == 8.5
    assert len(payload["issues"]) == 1
    assert payload["trace"][0]["agent"] == "fetch_agent"
