#!/usr/bin/env python
"""
Run the LangGraph pipeline on the evaluation scenarios and measure real review
quality against the expected issues.

Usage:
  python scripts/run_evaluation.py
  python scripts/run_evaluation.py --mock
  python scripts/run_evaluation.py --scenario sec/sql-injection
  python scripts/run_evaluation.py --categories security,style
  python scripts/run_evaluation.py --output path/to/out.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Force UTF-8 output on Windows so print() never crashes on Unicode output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("GROQ_API_KEY", "evaluation_local")

from backend.api.issue_extractor import extract_issues
from backend.config import settings
from backend.graph.state import build_initial_state
from evaluation.metrics import (
    compute_summary,
    evaluate_issue_quality,
    format_summary_table,
    make_run_result,
)
from evaluation.scenarios import SCENARIOS


_DIFF_BLOCK_RE = re.compile(r"```diff\s*([\s\S]*?)```", re.IGNORECASE)
_FILE_HEADER_RE = re.compile(r"^\+\+\+\s+b/(.+)$")
_DEF_RE = re.compile(r"^\+def\s+([A-Za-z_]\w*)\((.*?)\)(?:\s*->\s*[^:]+)?:")


def _mock_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(content=content)


def _extract_diff_from_prompt(prompt: str) -> str:
    match = _DIFF_BLOCK_RE.search(prompt)
    if match:
        return match.group(1).strip()
    return prompt


def _iterate_added_lines(diff: str):
    current_file = "unknown"
    new_line = 0

    for raw_line in diff.replace("\r\n", "\n").split("\n"):
        file_match = _FILE_HEADER_RE.match(raw_line)
        if file_match:
            current_file = file_match.group(1).strip()
            continue

        if raw_line.startswith("@@"):
            header = raw_line.split("@@", 2)[1].strip()
            plus_part = next((part for part in header.split() if part.startswith("+")), "+0")
            try:
                new_line = int(plus_part[1:].split(",", 1)[0])
            except ValueError:
                new_line = 0
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            yield current_file, new_line, raw_line[1:]
            new_line += 1
            continue

        if raw_line.startswith("-") and not raw_line.startswith("---"):
            continue

        new_line += 1


def _heuristic_findings(diff: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    added_lines = list(_iterate_added_lines(diff))
    added_text = "\n".join(line for _, _, line in added_lines)

    def add(
        severity: str,
        file_path: str,
        line_no: int,
        message: str,
        *,
        suggestion: str,
        kind: str,
        keywords: list[str],
        tags: list[str],
    ) -> None:
        key = (kind, file_path)
        if key in seen:
            return
        seen.add(key)
        findings.append(
            {
                "severity": severity,
                "file": file_path,
                "line": line_no,
                "message": message,
                "suggestion": suggestion,
                "kind": kind,
                "keywords": keywords,
                "tags": tags,
            }
        )

    for file_path, line_no, line in added_lines:
        line_lower = line.lower()
        stripped = line.strip()

        if (
            "select" in line_lower
            and "{" in line
            and ("f\"" in line or "f'" in line or "execute(f" in line_lower)
        ) or "where name='{user_input}'" in line_lower:
            add(
                "CRITICAL",
                file_path,
                line_no,
                "SQL injection risk from interpolated user input; use parameterized queries.",
                suggestion="Bind parameters instead of formatting user-controlled values into SQL.",
                kind="sql_injection",
                keywords=["sql injection", "parameterized", "owasp"],
                tags=["security"],
            )

        if "hashlib.md5(" in line_lower:
            add(
                "CRITICAL",
                file_path,
                line_no,
                "MD5 is not appropriate for password hashing; use a password-specific KDF such as bcrypt or Argon2.",
                suggestion="Replace MD5 with bcrypt or Argon2 and store a salted hash.",
                kind="md5_password",
                keywords=["md5", "bcrypt", "cryptographic", "password", "owasp"],
                tags=["security", "python"],
            )

        if (
            any(token in stripped for token in ("SECRET", "API_KEY", "STRIPE_SECRET", "DATABASE_URL"))
            and "=" in stripped
            and ('"' in stripped or "'" in stripped)
        ):
            add(
                "CRITICAL",
                file_path,
                line_no,
                "Hardcoded secret or credential is committed in source control.",
                suggestion="Move secrets to environment-backed configuration and rotate exposed credentials.",
                kind="hardcoded_secret",
                keywords=["hardcoded", "secret", "environment", "token", "owasp"],
                tags=["security"],
            )

        if "os.system(" in line_lower or "os.popen(" in line_lower:
            add(
                "CRITICAL",
                file_path,
                line_no,
                "Shell command is built from input without validation, which creates command injection risk.",
                suggestion="Use subprocess with an argument list and validate the input before execution.",
                kind="command_injection",
                keywords=["command injection", "subprocess", "os.system", "shell", "owasp"],
                tags=["security", "python"],
            )

        if "pickle.loads(" in line_lower:
            add(
                "CRITICAL",
                file_path,
                line_no,
                "Untrusted pickle deserialization can execute arbitrary code.",
                suggestion="Do not unpickle user-controlled data; prefer a safe format such as JSON.",
                kind="pickle_deserialization",
                keywords=["pickle", "deserialization", "untrusted", "json", "owasp"],
                tags=["security", "python"],
            )

        if "random.choice(" in line_lower or "random.randint(" in line_lower:
            add(
                "MAJOR",
                file_path,
                line_no,
                "Security-sensitive token generation uses random instead of a cryptographically secure source.",
                suggestion="Use the secrets module for session IDs and reset tokens.",
                kind="insecure_random",
                keywords=["random", "secrets", "cryptographic", "token", "predictable"],
                tags=["security", "python"],
            )

        if stripped == "except:":
            add(
                "MAJOR",
                file_path,
                line_no,
                "Bare except hides real failures and swallows unexpected exceptions.",
                suggestion="Catch specific exception types and log or propagate the error.",
                kind="bare_except",
                keywords=["bare except", "exception", "specific", "pep 8"],
                tags=["style", "python"],
            )

        if "== None" in line or "!= None" in line:
            add(
                "MINOR",
                file_path,
                line_no,
                "Compare against None with 'is' / 'is not' instead of equality operators.",
                suggestion="Use 'is None' and 'is not None' for identity checks.",
                kind="none_comparison",
                keywords=["none", "is not", "comparison", "pep 8"],
                tags=["style", "python"],
            )

        function_match = _DEF_RE.match(raw_line := f"+{line}")
        if function_match:
            signature = function_match.group(2)
            if ":" not in signature and "->" not in raw_line:
                add(
                    "MINOR",
                    file_path,
                    line_no,
                    "Public function is missing type annotations, which makes the API contract harder to use safely.",
                    suggestion="Add parameter and return annotations for public functions.",
                    kind="missing_type_hints",
                    keywords=["type", "annotation", "hints", "pep 8"],
                    tags=["style", "python"],
                )

        if re.search(r"def\s+\w+\([^)]*=\[\]", line) or re.search(r"def\s+\w+\([^)]*=\{\}", line):
            add(
                "MAJOR",
                file_path,
                line_no,
                "Mutable default argument will be shared across calls.",
                suggestion="Default to None and create a new container inside the function.",
                kind="mutable_default",
                keywords=["mutable", "default", "none", "pep 8"],
                tags=["style", "python"],
            )

    if "request.args.get(\"id\")" in added_text and ".query.get(doc_id)" in added_text:
        add(
            "CRITICAL",
            "api/documents.py",
            5,
            "Object is fetched directly from a request parameter without an authorization check.",
            suggestion="Verify the current user is allowed to access the requested record before returning it.",
            kind="broken_access_control",
            keywords=["access control", "authorization", "permission", "current_user", "owasp"],
            tags=["security"],
        )

    if "stripe.create_charge" in added_text and "email.send" in added_text and "slack.post" in added_text:
        add(
            "MAJOR",
            "services/order.py",
            1,
            "process_order handles validation, pricing, payment, persistence, and notifications in one function.",
            suggestion="Split the flow into smaller units so each step can be tested and changed independently.",
            kind="god_function",
            keywords=["single responsibility", "too many", "refactor", "extract"],
            tags=["design"],
        )

    if "item_type == 1" in added_text and "qty > 10" in added_text:
        add(
            "MINOR",
            "pricing/rules.py",
            2,
            "Pricing rules rely on magic numbers and commented-out dead code instead of named constants.",
            suggestion="Replace sentinel values with named constants and remove stale commented code.",
            kind="magic_numbers",
            keywords=["magic number", "constant", "dead code", "naming"],
            tags=["design"],
        )

    if added_text.count('errors.append("Invalid email")') >= 2:
        add(
            "MINOR",
            "validators/forms.py",
            1,
            "Validation logic is duplicated across functions instead of being shared.",
            suggestion="Extract the repeated checks into a shared helper to keep the rules consistent.",
            kind="duplicate_code",
            keywords=["duplicate", "dry", "refactor", "repeated"],
            tags=["design"],
        )

    return findings


def _keywords_for_diff(diff: str) -> list[str]:
    keywords: list[str] = []
    seen: set[str] = set()
    for finding in _heuristic_findings(diff):
        for keyword in finding["keywords"]:
            if keyword not in seen:
                seen.add(keyword)
                keywords.append(keyword)
    return keywords


def _filter_findings(findings: list[dict[str, object]], strategy: str) -> list[dict[str, object]]:
    def priority(finding: dict[str, object]) -> tuple[int, int]:
        tags = finding["tags"]
        severity = str(finding["severity"])
        security_rank = 0 if "security" in tags else 1
        severity_rank = {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2}.get(severity, 3)
        return (security_rank, severity_rank)

    ordered_findings = sorted(findings, key=priority)

    if strategy == "security_focus":
        filtered = [finding for finding in ordered_findings if "security" in finding["tags"]]
    elif strategy == "correctness_focus":
        filtered = [
            finding for finding in ordered_findings
            if "design" in finding["tags"] or "style" in finding["tags"]
        ]
    elif strategy == "python_idioms":
        filtered = [
            finding for finding in ordered_findings
            if "python" in finding["tags"] or "style" in finding["tags"]
        ]
    elif strategy == "typescript_idioms":
        filtered = [finding for finding in ordered_findings if "typescript" in finding["tags"]]
    else:
        filtered = ordered_findings[:1] if len(ordered_findings) > 1 else ordered_findings

    if filtered:
        return filtered
    if strategy == "initial":
        return ordered_findings[:1] if len(ordered_findings) > 1 else ordered_findings
    return ordered_findings


def _render_review(diff: str, strategy: str) -> str:
    findings = _filter_findings(_heuristic_findings(diff), strategy)
    if not diff.strip():
        return (
            "## Summary\nNo diff content was provided, so there is nothing concrete to review.\n\n"
            "## Issues Found\nNone.\n\n"
            "## Suggestions\nResubmit the request with a unified diff.\n\n"
            "## Verdict\nCOMMENT\nNo review is possible without diff content."
        )

    if not findings:
        return (
            "## Summary\nThe visible diff is small and I do not see a concrete defect in the changed lines.\n\n"
            "## Issues Found\nNone.\n\n"
            "## Suggestions\nKeep the review scoped to the current change and add tests if behavior changed.\n\n"
            "## Verdict\nAPPROVE\nNo actionable issue is visible in the provided diff."
        )

    issue_lines = [
        f"- [{finding['severity']}] {finding['file']}:{finding['line']} {finding['message']}"
        for finding in findings
    ]
    suggestion_lines = [
        f"- {finding['suggestion']}"
        for finding in findings
    ]
    summary = (
        "This change introduces concrete risks in the modified code."
        if strategy == "initial"
        else f"This {strategy.replace('_', ' ')} pass found issues the initial review could miss."
    )
    return (
        f"## Summary\n{summary}\n\n"
        f"## Issues Found\n{chr(10).join(issue_lines)}\n\n"
        f"## Suggestions\n{chr(10).join(suggestion_lines)}\n\n"
        "## Verdict\nREQUEST_CHANGES\nThe diff contains actionable issues that should be fixed before merge."
    )


def _mock_review_invoke(messages: list[object]) -> SimpleNamespace:
    prompt = getattr(messages[-1], "content", "")
    system = getattr(messages[0], "content", "")
    diff = _extract_diff_from_prompt(prompt)

    strategy = "initial"
    if "security-focused" in system:
        strategy = "security_focus"
    elif "correctness-focused" in system:
        strategy = "correctness_focus"
    elif "TypeScript and React reviewer" in system:
        strategy = "typescript_idioms"
    elif "Python reviewer" in system:
        strategy = "python_idioms"

    return _mock_response(_render_review(diff, strategy))


def _mock_critic_invoke(messages: list[object]) -> SimpleNamespace:
    prompt = getattr(messages[-1], "content", "")
    diff = _extract_diff_from_prompt(prompt)
    review_match = re.search(r"## Review To Evaluate\s*(.*)$", prompt, re.DOTALL)
    review_text = review_match.group(1).strip() if review_match else prompt
    issues = extract_issues(review_text)
    quality = evaluate_issue_quality(
        _keywords_for_diff(diff),
        [issue["message"] for issue in issues],
        review_text,
    )
    if not diff.strip():
        score = 10.0 if not issues else 2.0
    else:
        score = round(quality["f1"] * 10, 1)
    payload = {
        "score": score,
        "rationale": (
            f"precision={quality['precision']:.2f}, "
            f"recall={quality['recall']:.2f}, "
            f"false_positives={quality['false_positives']}"
        ),
        "issues_identified": [issue["message"] for issue in issues],
    }
    return _mock_response(json.dumps(payload))


def _mock_selector_invoke(messages: list[object]) -> SimpleNamespace:
    prompt = getattr(messages[-1], "content", "")
    matches = re.findall(r"\[(\d+)\]\s+strategy=([^\s]+)\s+score=(\d+(?:\.\d+)?)", prompt)
    if not matches:
        return _mock_response(json.dumps({"best_index": 0, "rationale": "Single candidate"}))

    ranked = sorted(
        ((int(index), strategy, float(score)) for index, strategy, score in matches),
        key=lambda item: (-item[2], item[0]),
    )
    best_index, best_strategy, best_score = ranked[0]
    return _mock_response(
        json.dumps(
            {
                "best_index": best_index,
                "rationale": f"Selected {best_strategy} because it had the highest critic score ({best_score:.1f}).",
            }
        )
    )


def _invoke_pipeline(initial_state: dict, use_mock: bool) -> dict:
    from backend.graph.workflow import compiled_graph

    if not use_mock:
        return compiled_graph.invoke(initial_state)

    review_mock = SimpleNamespace(invoke=_mock_review_invoke)
    branch_mock = SimpleNamespace(invoke=_mock_review_invoke)
    critic_mock = SimpleNamespace(invoke=_mock_critic_invoke)
    selector_mock = SimpleNamespace(invoke=_mock_selector_invoke)

    with (
        patch("backend.agents.review_agent._llm", review_mock),
        patch("backend.agents.branch_agent._llm", branch_mock),
        patch("backend.agents.critic_agent._llm", critic_mock),
        patch("backend.agents.selector_agent._llm", selector_mock),
    ):
        return compiled_graph.invoke(initial_state)


def run_scenario(scenario: dict, use_mock: bool = False) -> dict:
    """Run one scenario through the full pipeline."""
    scenario_id = scenario["id"]
    print(f"  [{scenario['category']:12s}] {scenario['name'][:55]:<55}", end=" ", flush=True)

    initial = build_initial_state(scenario_id)
    started_at = time.perf_counter()
    error_msg: str | None = None
    result: dict | None = None

    try:
        result = _invoke_pipeline(initial, use_mock=use_mock)
    except Exception as exc:
        error_msg = str(exc)

    latency_ms = (time.perf_counter() - started_at) * 1000

    if error_msg is not None or result is None:
        print(f"[ERR] {(error_msg or 'unknown error')[:60]}")
        return make_run_result(
            scenario_id=scenario_id,
            scenario_name=scenario["name"],
            category=scenario["category"],
            expected_issues=scenario["expected_issues"],
            review_score=0.0,
            precision=0.0,
            recall=0.0,
            f1=0.0,
            false_positives=0,
            found_issues=[],
            matched_expected_issues=[],
            unmatched_expected_issues=scenario["expected_issues"],
            matched_found_issues=[],
            false_positive_issues=[],
            triggered_branch=False,
            n_candidates=0,
            selected_strategy="error",
            latency_ms=latency_ms,
            retrieval_sources=[],
            review_text="",
            error=error_msg or "unknown error",
        )

    candidates = result.get("candidates", [])
    selected_index = result.get("selected_index")
    selected_candidate = (
        candidates[selected_index]
        if isinstance(selected_index, int) and 0 <= selected_index < len(candidates)
        else {}
    )
    score_lookup = {
        score["candidate_index"]: score
        for score in result.get("scores", [])
    }
    selected_score = score_lookup.get(selected_index or 0, {})
    review_text = str(selected_candidate.get("review", ""))
    files_changed = list(result.get("pr_metadata", {}).get("files_changed", []))
    issues = extract_issues(review_text, files_changed)
    found_issue_messages = [issue["message"] for issue in issues]
    quality = evaluate_issue_quality(
        scenario["expected_issues"],
        found_issue_messages,
        review_text,
    )

    run = make_run_result(
        scenario_id=scenario_id,
        scenario_name=scenario["name"],
        category=scenario["category"],
        expected_issues=scenario["expected_issues"],
        review_score=float(selected_score.get("score", 0.0)),
        precision=quality["precision"],
        recall=quality["recall"],
        f1=quality["f1"],
        false_positives=quality["false_positives"],
        found_issues=found_issue_messages,
        matched_expected_issues=quality["matched_expected_issues"],
        unmatched_expected_issues=quality["unmatched_expected_issues"],
        matched_found_issues=quality["matched_found_issues"],
        false_positive_issues=quality["false_positive_issues"],
        triggered_branch=bool(result.get("branch_taken", False)),
        n_candidates=len(candidates),
        selected_strategy=str(selected_candidate.get("strategy", "unknown")),
        latency_ms=latency_ms,
        retrieval_sources=result.get("retrieval_sources", []),
        review_text=review_text,
        selector_reason=str(result.get("selector_reason", "")),
        branch_improvement=result.get("branch_improvement"),
    )

    branch_delta = (
        f"  delta={run['branch_improvement']:+.1f}"
        if run.get("branch_improvement") is not None
        else ""
    )
    status = (
        f"P={run['precision']:.2f}  "
        f"R={run['recall']:.2f}  "
        f"F1={run['f1']:.2f}  "
        f"FP={run['false_positives']}  "
        f"branch={'Y' if run['triggered_branch'] else 'N'}  "
        f"strategy={run['selected_strategy']}"
        f"{branch_delta}"
        f"  "
        f"{run['latency_ms']:.0f}ms"
    )
    print(f"[OK]  {status}")
    return run


def main() -> None:
    parser = argparse.ArgumentParser(description="PR Critic evaluation runner")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic local mocks for LLM calls while keeping real evaluation metrics.",
    )
    parser.add_argument("--scenario", type=str, default=None)
    parser.add_argument("--categories", type=str, default=None)
    parser.add_argument("--output", type=str, default="evaluation/results.json")
    parser.add_argument("--delay", type=float, default=0.0)
    args = parser.parse_args()

    scenarios = SCENARIOS
    if args.scenario:
        scenarios = [scenario for scenario in scenarios if args.scenario in scenario["id"]]
        if not scenarios:
            print(f"No scenario matching '{args.scenario}'")
            sys.exit(1)
    if args.categories:
        allowed = {category.strip() for category in args.categories.split(",")}
        scenarios = [scenario for scenario in scenarios if scenario["category"] in allowed]
        if not scenarios:
            print(f"No scenarios in categories: {allowed}")
            sys.exit(1)

    mode = "MOCK" if args.mock else "LIVE (requires GROQ_API_KEY)"
    print(f"\nPR Critic Evaluation -- {mode}")
    print(f"Scenarios : {len(scenarios)}")
    print(f"Output    : {args.output}")
    print("-" * 56)

    results: list[dict] = []

    for index, scenario in enumerate(scenarios, 1):
        print(f"[{index:02d}/{len(scenarios):02d}] ", end="", flush=True)
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
                review_score=0.0,
                precision=0.0,
                recall=0.0,
                f1=0.0,
                false_positives=0,
                found_issues=[],
                matched_expected_issues=[],
                unmatched_expected_issues=scenario["expected_issues"],
                matched_found_issues=[],
                false_positive_issues=[],
                triggered_branch=False,
                n_candidates=0,
                selected_strategy="error",
                latency_ms=0.0,
                retrieval_sources=[],
                review_text="",
                error=f"FATAL: {fatal_msg}",
            )
        results.append(result)

        if args.delay > 0 and index < len(scenarios):
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
