"""
evaluation/metrics.py

Pure functions that compute metrics from evaluation results.
No I/O, no LLM calls — easy to unit-test independently.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


# ── Per-run result schema ─────────────────────────────────────────────────────

def make_run_result(
    scenario_id: str,
    scenario_name: str,
    category: str,
    expected_issues: list[str],
    score: float,
    triggered_branch: bool,
    n_candidates: int,
    selected_strategy: str,
    latency_ms: float,
    retrieval_sources: list[str],
    review_text: str,
    error: str | None = None,
) -> dict[str, Any]:
    """Build a structured dict for one pipeline run."""
    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "category": category,
        "expected_issues": expected_issues,
        "score": round(score, 2),
        "triggered_branch": triggered_branch,
        "n_candidates": n_candidates,
        "selected_strategy": selected_strategy,
        "latency_ms": round(latency_ms, 1),
        "retrieval_sources": retrieval_sources,
        # Abbreviated review (first 400 chars) — keeps JSON readable
        "review_preview": review_text[:400].replace("\n", " ") if review_text else "",
        "error": error,
    }


# ── Summary computation ───────────────────────────────────────────────────────

def compute_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute aggregate metrics from a list of run results.
    Skips errored runs in numeric aggregates.
    """
    successful = [r for r in results if r["error"] is None]
    total = len(results)
    n_ok = len(successful)

    if n_ok == 0:
        return {"error": "all runs failed", "total": total}

    scores = [r["score"] for r in successful]
    latencies = [r["latency_ms"] for r in successful]
    branched = [r for r in successful if r["triggered_branch"]]

    # Score distribution buckets: 0-3, 4-5, 6-7, 8-10
    def _bucket(s: float) -> str:
        if s < 4:   return "0-3 (poor)"
        if s < 6:   return "4-5 (weak)"
        if s < 8:   return "6-7 (adequate)"
        return "8-10 (good)"

    score_dist = Counter(_bucket(s) for s in scores)

    # Strategy distribution
    strategy_dist = Counter(r["selected_strategy"] for r in successful)

    # Per-category averages
    category_scores: dict[str, list[float]] = {}
    for r in successful:
        category_scores.setdefault(r["category"], []).append(r["score"])
    category_avg = {
        cat: round(sum(v) / len(v), 2)
        for cat, v in category_scores.items()
    }

    # Branching rate per category
    category_branch: dict[str, list[bool]] = {}
    for r in successful:
        category_branch.setdefault(r["category"], []).append(r["triggered_branch"])
    category_branch_rate = {
        cat: round(sum(v) / len(v) * 100, 1)
        for cat, v in category_branch.items()
    }

    return {
        "total_scenarios": total,
        "successful_runs": n_ok,
        "failed_runs": total - n_ok,

        "avg_score": round(sum(scores) / n_ok, 2),
        "min_score": round(min(scores), 2),
        "max_score": round(max(scores), 2),

        "branching_rate_pct": round(len(branched) / n_ok * 100, 1),
        "branched_count": len(branched),

        "avg_latency_ms": round(sum(latencies) / n_ok, 1),
        "min_latency_ms": round(min(latencies), 1),
        "max_latency_ms": round(max(latencies), 1),

        "score_distribution": dict(score_dist),
        "strategy_distribution": dict(strategy_dist),
        "most_common_strategy": strategy_dist.most_common(1)[0][0] if strategy_dist else "N/A",

        "category_avg_score": category_avg,
        "category_branching_rate_pct": category_branch_rate,
    }


def format_summary_table(summary: dict[str, Any]) -> str:
    """Return a plain-text summary table for stdout."""
    lines = [
        "=" * 52,
        "  PR CRITIC — EVALUATION SUMMARY",
        "=" * 52,
        f"  Scenarios run        : {summary.get('total_scenarios', 0)}",
        f"  Successful           : {summary.get('successful_runs', 0)}",
        f"  Failed               : {summary.get('failed_runs', 0)}",
        "-" * 52,
        f"  Avg score (0–10)     : {summary.get('avg_score', 'N/A')}",
        f"  Score range          : {summary.get('min_score')} – {summary.get('max_score')}",
        f"  Branching rate       : {summary.get('branching_rate_pct')}%",
        f"  Avg latency          : {summary.get('avg_latency_ms')} ms",
        f"  Most common strategy : {summary.get('most_common_strategy')}",
        "-" * 52,
        "  Score distribution:",
    ]
    for bucket, count in sorted(summary.get("score_distribution", {}).items()):
        lines.append(f"    {bucket:<20} : {count}")

    lines += ["-" * 52, "  Strategy distribution:"]
    for strategy, count in sorted(
        summary.get("strategy_distribution", {}).items(),
        key=lambda x: -x[1],
    ):
        lines.append(f"    {strategy:<20} : {count}")

    lines += ["-" * 52, "  Per-category avg score:"]
    for cat, avg in sorted(summary.get("category_avg_score", {}).items()):
        branch_rate = summary.get("category_branching_rate_pct", {}).get(cat, 0)
        lines.append(f"    {cat:<14} : {avg:.2f}  (branch {branch_rate}%)")

    lines.append("=" * 52)
    return "\n".join(lines)
