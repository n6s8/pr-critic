"""
evaluation/metrics.py

Pure functions that compute metrics from evaluation results.
No I/O and no LLM calls, so they are easy to unit-test independently.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


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
        "review_preview": review_text[:400].replace("\n", " ") if review_text else "",
        "error": error,
    }


def compute_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute aggregate metrics from a list of run results.
    Errored runs are excluded from numeric aggregates, but still counted in success rate.
    """
    successful = [result for result in results if result["error"] is None]
    total = len(results)
    successful_count = len(successful)
    success_rate_pct = round((successful_count / total) * 100, 1) if total else 0.0

    if successful_count == 0:
        return {
            "error": "all runs failed",
            "total": total,
            "total_scenarios": total,
            "successful_runs": 0,
            "failed_runs": total,
            "success_rate_pct": success_rate_pct,
        }

    scores = [result["score"] for result in successful]
    latencies = [result["latency_ms"] for result in successful]
    branched = [result for result in successful if result["triggered_branch"]]

    def _bucket(score: float) -> str:
        if score < 4:
            return "0-3 (poor)"
        if score < 6:
            return "4-5 (weak)"
        if score < 8:
            return "6-7 (adequate)"
        return "8-10 (good)"

    score_dist = Counter(_bucket(score) for score in scores)
    strategy_dist = Counter(result["selected_strategy"] for result in successful)

    category_scores: dict[str, list[float]] = {}
    for result in successful:
        category_scores.setdefault(result["category"], []).append(result["score"])
    category_avg = {
        category: round(sum(values) / len(values), 2)
        for category, values in category_scores.items()
    }

    category_branch: dict[str, list[bool]] = {}
    for result in successful:
        category_branch.setdefault(result["category"], []).append(result["triggered_branch"])
    category_branch_rate = {
        category: round(sum(values) / len(values) * 100, 1)
        for category, values in category_branch.items()
    }

    return {
        "total_scenarios": total,
        "successful_runs": successful_count,
        "failed_runs": total - successful_count,
        "success_rate_pct": success_rate_pct,
        "avg_score": round(sum(scores) / successful_count, 2),
        "min_score": round(min(scores), 2),
        "max_score": round(max(scores), 2),
        "branching_rate_pct": round(len(branched) / successful_count * 100, 1),
        "branched_count": len(branched),
        "avg_latency_ms": round(sum(latencies) / successful_count, 1),
        "min_latency_ms": round(min(latencies), 1),
        "max_latency_ms": round(max(latencies), 1),
        "score_distribution": dict(score_dist),
        "strategy_distribution": dict(strategy_dist),
        "most_common_strategy": strategy_dist.most_common(1)[0][0] if strategy_dist else "N/A",
        "category_avg_score": category_avg,
        "category_branching_rate_pct": category_branch_rate,
    }


def format_summary_table(summary: dict[str, Any]) -> str:
    """Return a clean plain-text summary table for stdout and CI logs."""
    lines = [
        "=" * 52,
        "  PR CRITIC - EVALUATION SUMMARY",
        "=" * 52,
        f"  Scenarios run        : {summary.get('total_scenarios', 0)}",
        f"  Successful           : {summary.get('successful_runs', 0)}",
        f"  Failed               : {summary.get('failed_runs', 0)}",
        f"  Success rate         : {summary.get('success_rate_pct', 0)}%",
        "-" * 52,
        f"  Avg score (0-10)     : {summary.get('avg_score', 'N/A')}",
        f"  Score range          : {summary.get('min_score')} - {summary.get('max_score')}",
        f"  Branching rate       : {summary.get('branching_rate_pct')}%",
        f"  Avg latency          : {summary.get('avg_latency_ms')} ms",
        f"  Latency range        : {summary.get('min_latency_ms')} - {summary.get('max_latency_ms')} ms",
        f"  Most common strategy : {summary.get('most_common_strategy')}",
        "-" * 52,
        "  Score distribution:",
    ]
    for bucket, count in sorted(summary.get("score_distribution", {}).items()):
        lines.append(f"    {bucket:<20} : {count}")

    lines += ["-" * 52, "  Strategy distribution:"]
    for strategy, count in sorted(
        summary.get("strategy_distribution", {}).items(),
        key=lambda item: -item[1],
    ):
        lines.append(f"    {strategy:<20} : {count}")

    lines += ["-" * 52, "  Per-category avg score:"]
    for category, avg in sorted(summary.get("category_avg_score", {}).items()):
        branch_rate = summary.get("category_branching_rate_pct", {}).get(category, 0)
        lines.append(f"    {category:<14} : {avg:.2f}  (branch {branch_rate}%)")

    lines.append("=" * 52)
    return "\n".join(lines)
