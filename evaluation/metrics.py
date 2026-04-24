"""
evaluation/metrics.py

Pure functions that compute evaluation quality from expected issues and the
selected review output. No I/O and no LLM calls live here.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any


_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize(text: str) -> str:
    return _NORMALIZE_RE.sub(" ", str(text or "").lower()).strip()


def _matches_keyword(keyword: str, text: str) -> bool:
    normalized_keyword = _normalize(keyword)
    normalized_text = _normalize(text)
    if not normalized_keyword or not normalized_text:
        return False
    return (
        normalized_keyword in normalized_text
        or normalized_text in normalized_keyword
    )


def _dedupe_texts(items: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = str(item or "").strip()
        normalized = _normalize(cleaned)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(cleaned)
    return unique


def evaluate_issue_quality(
    expected_issues: list[str],
    found_issues: list[str],
    review_text: str,
) -> dict[str, Any]:
    """
    Compare the expected scenario issues to the issues found in the final review.

    Recall is measured against the full review text so we capture issue mentions
    that appear in suggestions or rationale, not only in extracted bullets.
    Precision and false positives are measured against the structured found issue
    list because that is what the system explicitly surfaced as findings.
    """
    expected = _dedupe_texts(expected_issues)
    found = _dedupe_texts(found_issues)
    review_blob = "\n".join([review_text, *found])

    matched_expected = [
        issue for issue in expected
        if _matches_keyword(issue, review_blob)
    ]
    unmatched_expected = [
        issue for issue in expected
        if issue not in matched_expected
    ]

    matched_found = [
        issue for issue in found
        if any(_matches_keyword(expected_issue, issue) for expected_issue in expected)
    ]
    false_positive_issues = [
        issue for issue in found
        if issue not in matched_found
    ]

    if not found:
        precision = 1.0 if not expected else 0.0
    else:
        precision = len(matched_found) / len(found)

    if not expected:
        recall = 1.0
    else:
        recall = len(matched_expected) / len(expected)

    if precision == 0.0 and recall == 0.0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "matched_expected_issues": matched_expected,
        "unmatched_expected_issues": unmatched_expected,
        "matched_found_issues": matched_found,
        "false_positive_issues": false_positive_issues,
        "matched_expected_count": len(matched_expected),
        "matched_found_count": len(matched_found),
        "false_positives": len(false_positive_issues),
        "found_issue_count": len(found),
        "expected_issue_count": len(expected),
    }


def make_run_result(
    scenario_id: str,
    scenario_name: str,
    category: str,
    expected_issues: list[str],
    review_score: float,
    precision: float,
    recall: float,
    f1: float,
    false_positives: int,
    found_issues: list[str],
    matched_expected_issues: list[str],
    unmatched_expected_issues: list[str],
    matched_found_issues: list[str],
    false_positive_issues: list[str],
    triggered_branch: bool,
    n_candidates: int,
    selected_strategy: str,
    latency_ms: float,
    retrieval_sources: list[str],
    review_text: str,
    selector_reason: str = "",
    branch_improvement: float | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build a structured dict for one pipeline run."""
    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "category": category,
        "expected_issues": expected_issues,
        "review_score": round(review_score, 2),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positives": int(false_positives),
        "found_issues": found_issues,
        "matched_expected_issues": matched_expected_issues,
        "unmatched_expected_issues": unmatched_expected_issues,
        "matched_found_issues": matched_found_issues,
        "false_positive_issues": false_positive_issues,
        "triggered_branch": triggered_branch,
        "n_candidates": n_candidates,
        "selected_strategy": selected_strategy,
        "selector_reason": selector_reason,
        "branch_improvement": round(branch_improvement, 2) if branch_improvement is not None else None,
        "latency_ms": round(latency_ms, 1),
        "retrieval_sources": retrieval_sources,
        "review_preview": review_text[:400].replace("\n", " ") if review_text else "",
        "error": error,
    }


def compute_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute aggregate quality metrics from run results.

    Failed runs still affect success rate, but they are excluded from precision /
    recall / latency aggregates because no review quality could be measured.
    """
    successful = [result for result in results if result["error"] is None]
    total = len(results)
    successful_count = len(successful)
    success_rate_pct = round((successful_count / total) * 100, 1) if total else 0.0

    if successful_count == 0:
        return {
            "error": "all runs failed",
            "total_scenarios": total,
            "successful_runs": 0,
            "failed_runs": total,
            "success_rate_pct": success_rate_pct,
        }

    precisions = [result["precision"] for result in successful]
    recalls = [result["recall"] for result in successful]
    f1_scores = [result["f1"] for result in successful]
    review_scores = [result["review_score"] for result in successful]
    latencies = [result["latency_ms"] for result in successful]
    false_positive_counts = [result["false_positives"] for result in successful]
    branched = [result for result in successful if result["triggered_branch"]]
    branch_improvements = [
        float(result["branch_improvement"])
        for result in successful
        if result.get("branch_improvement") is not None
    ]

    def _quality_bucket(f1: float) -> str:
        if f1 < 0.25:
            return "0.00-0.24 (poor)"
        if f1 < 0.5:
            return "0.25-0.49 (weak)"
        if f1 < 0.75:
            return "0.50-0.74 (adequate)"
        return "0.75-1.00 (good)"

    quality_dist = Counter(_quality_bucket(f1) for f1 in f1_scores)
    strategy_dist = Counter(result["selected_strategy"] for result in successful)

    category_metrics: dict[str, dict[str, list[float]]] = {}
    for result in successful:
        bucket = category_metrics.setdefault(
            result["category"],
            {"precision": [], "recall": [], "f1": [], "false_positives": []},
        )
        bucket["precision"].append(result["precision"])
        bucket["recall"].append(result["recall"])
        bucket["f1"].append(result["f1"])
        bucket["false_positives"].append(float(result["false_positives"]))

    per_category = {
        category: {
            "avg_precision": round(sum(values["precision"]) / len(values["precision"]), 4),
            "avg_recall": round(sum(values["recall"]) / len(values["recall"]), 4),
            "avg_f1": round(sum(values["f1"]) / len(values["f1"]), 4),
            "avg_false_positives": round(
                sum(values["false_positives"]) / len(values["false_positives"]),
                2,
            ),
        }
        for category, values in category_metrics.items()
    }

    return {
        "total_scenarios": total,
        "successful_runs": successful_count,
        "failed_runs": total - successful_count,
        "success_rate_pct": success_rate_pct,
        "avg_precision": round(sum(precisions) / successful_count, 4),
        "avg_recall": round(sum(recalls) / successful_count, 4),
        "avg_f1": round(sum(f1_scores) / successful_count, 4),
        "avg_review_score": round(sum(review_scores) / successful_count, 2),
        "total_false_positives": int(sum(false_positive_counts)),
        "avg_false_positives": round(sum(false_positive_counts) / successful_count, 2),
        "perfect_recall_runs": sum(1 for value in recalls if value == 1.0),
        "zero_false_positive_runs": sum(1 for value in false_positive_counts if value == 0),
        "branching_rate_pct": round(len(branched) / successful_count * 100, 1),
        "branched_count": len(branched),
        "avg_branch_improvement": (
            round(sum(branch_improvements) / len(branch_improvements), 2)
            if branch_improvements
            else None
        ),
        "avg_latency_ms": round(sum(latencies) / successful_count, 1),
        "min_latency_ms": round(min(latencies), 1),
        "max_latency_ms": round(max(latencies), 1),
        "quality_distribution": dict(quality_dist),
        "strategy_distribution": dict(strategy_dist),
        "most_common_strategy": strategy_dist.most_common(1)[0][0] if strategy_dist else "N/A",
        "category_metrics": per_category,
    }


def format_summary_table(summary: dict[str, Any]) -> str:
    """Return a plain-text summary table for stdout and CI logs."""
    lines = [
        "=" * 56,
        "  PR CRITIC - EVALUATION SUMMARY",
        "=" * 56,
        f"  Scenarios run        : {summary.get('total_scenarios', 0)}",
        f"  Successful           : {summary.get('successful_runs', 0)}",
        f"  Failed               : {summary.get('failed_runs', 0)}",
        f"  Success rate         : {summary.get('success_rate_pct', 0)}%",
        "-" * 56,
        f"  Avg precision        : {summary.get('avg_precision', 'N/A')}",
        f"  Avg recall           : {summary.get('avg_recall', 'N/A')}",
        f"  Avg F1               : {summary.get('avg_f1', 'N/A')}",
        f"  Avg review score     : {summary.get('avg_review_score', 'N/A')}",
        f"  Total false positives: {summary.get('total_false_positives', 'N/A')}",
        f"  Avg false positives  : {summary.get('avg_false_positives', 'N/A')}",
        f"  Branching rate       : {summary.get('branching_rate_pct', 0)}%",
        f"  Perfect recall runs  : {summary.get('perfect_recall_runs', 0)}",
        f"  Zero FP runs         : {summary.get('zero_false_positive_runs', 0)}",
        f"  Avg branch delta     : {summary.get('avg_branch_improvement', 'N/A')}",
        f"  Avg latency          : {summary.get('avg_latency_ms', 'N/A')} ms",
        f"  Most common strategy : {summary.get('most_common_strategy', 'N/A')}",
        "-" * 56,
        "  F1 distribution:",
    ]
    for bucket, count in sorted(summary.get("quality_distribution", {}).items()):
        lines.append(f"    {bucket:<24} : {count}")

    lines += ["-" * 56, "  Strategy distribution:"]
    for strategy, count in sorted(
        summary.get("strategy_distribution", {}).items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"    {strategy:<24} : {count}")

    lines += ["-" * 56, "  Per-category quality:"]
    for category, metrics in sorted(summary.get("category_metrics", {}).items()):
        lines.append(
            "    "
            f"{category:<12} : "
            f"P={metrics['avg_precision']:.2f} "
            f"R={metrics['avg_recall']:.2f} "
            f"F1={metrics['avg_f1']:.2f} "
            f"FP={metrics['avg_false_positives']:.2f}"
        )

    lines.append("=" * 56)
    return "\n".join(lines)
