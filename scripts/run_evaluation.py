#!/usr/bin/env python
"""
scripts/run_evaluation.py

Run the full LangGraph pipeline on every evaluation scenario,
collect metrics, and save results to evaluation/results.json.

Usage:
  python scripts/run_evaluation.py                    # run all scenarios
  python scripts/run_evaluation.py --mock             # mock LLM calls (no API key needed)
  python scripts/run_evaluation.py --scenario sec/sql-injection
  python scripts/run_evaluation.py --categories security,style
  python scripts/run_evaluation.py --output path/to/out.json
  python scripts/run_evaluation.py --delay 1.5
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

# Force UTF-8 output on Windows so any unicode in print() doesn't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("GROQ_API_KEY", "eval_placeholder")

from evaluation.scenarios import SCENARIOS
from evaluation.metrics import make_run_result, compute_summary, format_summary_table
from backend.config import settings


# ── LLM mock helpers ──────────────────────────────────────────────────────────

def _mock_review_response() -> MagicMock:
    m = MagicMock()
    m.content = (
        "## Summary\nMocked review for evaluation.\n\n"
        "## Issues Found\n- MAJOR: Example issue detected\n\n"
        "## Suggestions\n- Fix the identified issue.\n\n"
        "## Verdict: REQUEST_CHANGES"
    )
    return m


def _mock_critic_response(score: float) -> MagicMock:
    m = MagicMock()
    m.content = json.dumps({
        "score": score,
        "rationale": "Mocked critic evaluation",
        "issues_identified": ["example issue"],
    })
    return m


def _mock_selector_response() -> MagicMock:
    m = MagicMock()
    m.content = json.dumps({
        "best_index": 0,
        "rationale": "Mocked selection: first candidate",
    })
    return m


# ── Single scenario runner ────────────────────────────────────────────────────

def run_scenario(scenario: dict, use_mock: bool = False) -> dict:
    """
    Run one scenario through the full pipeline and return a result dict.
    Never raises — all exceptions are caught and recorded in result["error"].
    """
    from backend.graph.workflow import compiled_graph
    from backend.graph.state import PRCriticState

    scenario_id = scenario["id"]
    print(f"  [{scenario['category']:12s}] {scenario['name'][:55]:<55}", end=" ", flush=True)

    initial: PRCriticState = {
        "pr_url": scenario_id,
        "pr_diff": scenario["diff"],
        "pr_metadata": {
            "title": scenario["name"],
            "author": "eval_bot",
            "base_branch": "main",
            "head_branch": "eval",
            "files_changed": ["eval_file.py"],
            "language": "Python",
        },
        "retrieved_context": "",
        "retrieval_sources": [],
        "candidates": [],
        "trigger_branch": False,
        "best_candidate": None,
        "selector_rationale": "",
        "trace": [],
    }

    t0 = time.perf_counter()
    error_msg: str | None = None

    try:
        if use_mock:
            category_scores = {
                "security": 5.0,
                "style": 6.5,
                "design": 6.0,
                "edge": 7.5,
                "adversarial": 7.0,
            }
            base_score = category_scores.get(scenario["category"], 6.0)
            idx = next(
                (i for i, s in enumerate(SCENARIOS) if s["id"] == scenario_id), 0
            )
            score = max(1.0, min(10.0, base_score + (idx % 3) * 0.5))

            _critic_call_count = 0

            def side_effect_critic(*args, **kwargs):
                nonlocal _critic_call_count
                _critic_call_count += 1
                if _critic_call_count == 1:
                    return _mock_critic_response(score)
                return _mock_critic_response(score + 2.0)

            with (
                patch("backend.agents.review_agent._llm") as mock_rev,
                patch("backend.agents.critic_agent._llm") as mock_crit,
                patch("backend.agents.branch_agent._llm") as mock_branch,
                patch("backend.agents.selector_agent._llm") as mock_sel,
            ):
                mock_rev.invoke.return_value = _mock_review_response()
                mock_branch.invoke.return_value = _mock_review_response()
                mock_crit.invoke.side_effect = side_effect_critic
                mock_sel.invoke.return_value = _mock_selector_response()
                result = compiled_graph.invoke(initial)
        else:
            result = compiled_graph.invoke(initial)

    except Exception as exc:
        # Save immediately — Python 3 deletes `exc` at end of except block
        error_msg = str(exc)

    latency_ms = (time.perf_counter() - t0) * 1000

    if error_msg is not None:
        print(f"[ERR] {error_msg[:60]}")
        return make_run_result(
            scenario_id=scenario_id,
            scenario_name=scenario["name"],
            category=scenario["category"],
            expected_issues=scenario["expected_issues"],
            score=0.0,
            triggered_branch=False,
            n_candidates=0,
            selected_strategy="error",
            latency_ms=latency_ms,
            retrieval_sources=[],
            review_text="",
            error=error_msg,
        )

    best = result.get("best_candidate") or {}
    run = make_run_result(
        scenario_id=scenario_id,
        scenario_name=scenario["name"],
        category=scenario["category"],
        expected_issues=scenario["expected_issues"],
        score=best.get("score", 0.0),
        triggered_branch=result.get("trigger_branch", False),
        n_candidates=len(result.get("candidates", [])),
        selected_strategy=best.get("strategy", "unknown"),
        latency_ms=latency_ms,
        retrieval_sources=result.get("retrieval_sources", []),
        review_text=best.get("review", ""),
    )

    status = (
        f"score={run['score']:.1f}  "
        f"branch={'Y' if run['triggered_branch'] else 'N'}  "
        f"{run['latency_ms']:.0f}ms"
    )
    print(f"[OK]  {status}")
    return run


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="PR Critic evaluation runner")
    parser.add_argument("--mock", action="store_true",
                        help="Mock all LLM calls (no API key needed, fast)")
    parser.add_argument("--scenario", type=str, default=None)
    parser.add_argument("--categories", type=str, default=None)
    parser.add_argument("--output", type=str, default="evaluation/results.json")
    parser.add_argument("--delay", type=float, default=0.0)
    args = parser.parse_args()

    scenarios = SCENARIOS
    if args.scenario:
        scenarios = [s for s in scenarios if args.scenario in s["id"]]
        if not scenarios:
            print(f"No scenario matching '{args.scenario}'")
            sys.exit(1)
    if args.categories:
        allowed = {c.strip() for c in args.categories.split(",")}
        scenarios = [s for s in scenarios if s["category"] in allowed]
        if not scenarios:
            print(f"No scenarios in categories: {allowed}")
            sys.exit(1)

    mode = "MOCK" if args.mock else "LIVE (requires GROQ_API_KEY)"
    print(f"\nPR Critic Evaluation -- {mode}")
    print(f"Scenarios : {len(scenarios)}")
    print(f"Output    : {args.output}")
    print("-" * 52)

    results: list[dict] = []

    for i, scenario in enumerate(scenarios, 1):
        print(f"[{i:02d}/{len(scenarios):02d}] ", end="", flush=True)

        # Outer safety net — run_scenario should never raise, but just in case
        try:
            result = run_scenario(scenario, use_mock=args.mock)
        except Exception as exc:
            fatal_msg = str(exc)
            print(f"[FATAL] {fatal_msg[:80]}")
            result = make_run_result(
                scenario_id=scenario["id"],
                scenario_name=scenario["name"],
                category=scenario["category"],
                expected_issues=scenario["expected_issues"],
                score=0.0,
                triggered_branch=False,
                n_candidates=0,
                selected_strategy="error",
                latency_ms=0.0,
                retrieval_sources=[],
                review_text="",
                error=f"FATAL: {fatal_msg}",
            )

        results.append(result)

        if args.delay > 0 and i < len(scenarios):
            time.sleep(args.delay)

    summary = compute_summary(results)

    output = {
        "meta": {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "mode": "mock" if args.mock else "live",
            "total_scenarios": len(scenarios),
            "groq_generation_model": settings.generation_model,
            "groq_reasoning_model": settings.reasoning_model,
        },
        "summary": summary,
        "results": results,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print(format_summary_table(summary))
    print(f"\nResults saved -> {out_path}")

    if summary.get("failed_runs", 0) > 0 or summary.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
