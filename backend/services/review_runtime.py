"""Execution helpers that keep the sync graph usable while exposing async wrappers."""
from __future__ import annotations

from copy import deepcopy

from starlette.concurrency import run_in_threadpool

from backend.graph.contracts import PRCriticState
from backend.graph.workflow import compiled_graph
from backend.observability.context import request_context_scope


def run_review_pipeline(initial_state: PRCriticState) -> PRCriticState:
    working_state = deepcopy(initial_state)
    request_context = working_state.get("request_context", {})

    with request_context_scope(**request_context):
        result = compiled_graph.invoke(working_state)

    return result


async def run_review_pipeline_async(initial_state: PRCriticState) -> PRCriticState:
    return await run_in_threadpool(run_review_pipeline, initial_state)
