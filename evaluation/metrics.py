"""
Issue-level evaluation metrics for PR Critic.

The evaluation compares structured expected issues to structured detected
issues, then computes precision / recall / F1 over matched issue pairs.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, TypedDict

from backend.utils.issues import (
    classify_issue_type,
    description_similarity,
    file_paths_match,
    normalize_file_path,
)


class EvaluationIssue(TypedDict):
    file: str
    type: str
    description: str


def _normalize_issue(issue: dict[str, Any]) -> EvaluationIssue:
    return {
        "file": normalize_file_path(str(issue.get("file") or "unknown")),
        "type": classify_issue_type(
            str(issue.get("description") or issue.get("message") or ""),
            str(issue.get("type") or issue.get("issue_type") or ""),
        ),
        "description": str(issue.get("description") or issue.get("message") or "").strip(),
    }


def _dedupe_issues(issues: list[dict[str, Any]]) -> list[EvaluationIssue]:
    deduped: list[EvaluationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        normalized = _normalize_issue(issue)
        key = (
            normalized["file"],
            normalized["type"],
            re.sub(r"\s+", " ", normalized["description"].lower()),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _issue_match_score(expected: EvaluationIssue, detected: EvaluationIssue) -> float:
    if expected["type"] == "unknown" or detected["type"] == "unknown":
        return 0.0
    if expected["type"] != detected["type"]:
        return 0.0

    same_file = file_paths_match(expected["file"], detected["file"])
    if not same_file and "unknown" not in {expected["file"], detected["file"]}:
        return 0.0

    similarity = description_similarity(expected["description"], detected["description"])
    file_score = 1.0 if same_file else 0.35
    return 0.7 + (0.2 * file_score) + (0.1 * similarity)


def _match_issues(
    expected_issues: list[EvaluationIssue],
    detected_issues: list[EvaluationIssue],
) -> list[tuple[int, int, float]]:
    scored_pairs: list[tuple[int, int, float]] = []
    for expected_index, expected in enumerate(expected_issues):
        for detected_index, detected in enumerate(detected_issues):
            score = _issue_match_score(expected, detected)
            if score > 0:
                scored_pairs.append((expected_index, detected_index, score))

    scored_pairs.sort(key=lambda item: (-item[2], item[0], item[1]))
    matched_expected: set[int] = set()
    matched_detected: set[int] = set()
    matches: list[tuple[int, int, float]] = []

    for expected_index, detected_index, score in scored_pairs:
        if expected_index in matched_expected or detected_index in matched_detected:
            continue
        matched_expected.add(expected_index)
        matched_detected.add(detected_index)
        matches.append((expected_index, detected_index, score))

    return matches


def evaluate_issue_quality(
    expected_issues: list[dict[str, Any]],
    detected_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = _dedupe_issues(expected_issues)
    detected = _dedupe_issues(detected_issues)
    matches = _match_issues(expected, detected)

    matched_expected_indexes = {expected_index for expected_index, _, _ in matches}
    matched_detected_indexes = {detected_index for _, detected_index, _ in matches}

    matched_expected = [expected[index] for index in sorted(matched_expected_indexes)]
    unmatched_expected = [
        issue for index, issue in enumerate(expected)
        if index not in matched_expected_indexes
    ]
    matched_detected = [detected[index] for index in sorted(matched_detected_indexes)]
    false_positive_issues = [
        issue for index, issue in enumerate(detected)
        if index not in matched_detected_indexes
    ]

    if not detected:
        precision = 1.0 if not expected else 0.0
    else:
        precision = len(matches) / len(detected)

    recall = 1.0 if not expected else len(matches) / len(expected)
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
        "matched_detected_issues": matched_detected,
        "false_positive_issues": false_positive_issues,
        "matched_issue_count": len(matches),
        "false_positives": len(false_positive_issues),
        "detected_issue_count": len(detected),
        "expected_issue_count": len(expected),
    }


def make_run_result(
    scenario_id: str,
    scenario_name: str,
    category: str,
    expected_issues: list[dict[str, Any]],
    review_score: float,
    precision: float,
    recall: float,
    f1: float,
    false_positives: int,
    detected_issues: list[dict[str, Any]],
    matched_expected_issues: list[dict[str, Any]],
    unmatched_expected_issues: list[dict[str, Any]],
    matched_detected_issues: list[dict[str, Any]],
    false_positive_issues: list[dict[str, Any]],
    triggered_branch: bool,
    n_candidates: int,
    selected_strategy: str,
    latency_ms: float,
    retrieval_sources: list[str],
    review_text: str,
    selector_reason: str = "",
    branch_improvement: float | None = None,
    repo_signals: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "category": category,
        "expected_issues": _dedupe_issues(expected_issues),
        "review_score": round(review_score, 2),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positives": int(false_positives),
        "detected_issues": _dedupe_issues(detected_issues),
        "matched_expected_issues": _dedupe_issues(matched_expected_issues),
        "unmatched_expected_issues": _dedupe_issues(unmatched_expected_issues),
        "matched_detected_issues": _dedupe_issues(matched_detected_issues),
        "false_positive_issues": _dedupe_issues(false_positive_issues),
        "triggered_branch": triggered_branch,
        "n_candidates": n_candidates,
        "selected_strategy": selected_strategy,
        "selector_reason": selector_reason,
        "branch_improvement": round(branch_improvement, 2) if branch_improvement is not None else None,
        "latency_ms": round(latency_ms, 1),
        "retrieval_sources": retrieval_sources,
        "repo_signals": repo_signals or {},
        "review_preview": review_text[:400].replace("\n", " ") if review_text else "",
        "error": error,
    }


def compute_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
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
            "avg_false_positives": round(sum(values["false_positives"]) / len(values["false_positives"]), 2),
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
        "avg_branch_improvement": round(sum(branch_improvements) / len(branch_improvements), 2) if branch_improvements else None,
        "avg_latency_ms": round(sum(latencies) / successful_count, 1),
        "min_latency_ms": round(min(latencies), 1),
        "max_latency_ms": round(max(latencies), 1),
        "quality_distribution": dict(quality_dist),
        "strategy_distribution": dict(strategy_dist),
        "most_common_strategy": strategy_dist.most_common(1)[0][0] if strategy_dist else "N/A",
        "category_metrics": per_category,
    }


def format_summary_table(summary: dict[str, Any]) -> str:
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
