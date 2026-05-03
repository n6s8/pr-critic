# Real-World Evaluation

## Dataset

The repository includes a real-world dataset in [evaluation/real_world_cases.json](evaluation/real_world_cases.json).

The dataset is intentionally small, manual, and based on public GitHub PR URLs instead of synthetic `eval://` diffs. It now contains 8 cases:

- 5 clean or fix-oriented PRs where `expected_issues` is empty.
- 3 issue-detection PRs with manually curated ground-truth issues.
- 5 total expected real issues across validation, security, and error-handling cases.

Each case stores:

- `pr_url`
- `category`
- a short human description
- `expected_issues` with `file`, `type`, and `description`

## Validation Types

Clean PR validation checks false-positive control. These cases should produce no detected issues. A perfect clean-case score means the reviewer avoided inventing problems, but it does not prove bug-finding recall because there are no expected bugs.

Issue-detection validation checks recall on real bugs. These cases contain expected issues from the public PR diff, so precision, recall, F1, and false positives measure whether the selected review actually finds grounded defects.

Current issue-detection cases:

- [ishi-gupta/vuln-test-suite#59](https://github.com/ishi-gupta/vuln-test-suite/pull/59): weak MD5 password hashing remains in the changed line.
- [nisarg-vibhakar-ead/pr-review-playground#1](https://github.com/nisarg-vibhakar-ead/pr-review-playground/pull/1): missing validation plus obfuscated JavaScript in route code.
- [ZaidBuilds/Hey-Jarvis#143](https://github.com/ZaidBuilds/Hey-Jarvis/pull/143): broad `Exception` handlers still hide failures behind generic messages.

## Methodology

The evaluation path reuses the normal pipeline:

1. Fetch the live PR diff and metadata from GitHub.
2. Collect best-effort repository-aware signals.
3. Run the review pipeline with smart diff filtering.
4. Extract detected issues from the selected review.
5. Compare detected issues against `expected_issues`.
6. Compute precision, recall, F1, and false positives.

Two evaluation modes exist:

- Offline structural run: `python scripts/run_evaluation.py --mock --real-world`
- Live model run: `python scripts/run_evaluation.py --real-world`

The offline run uses live public PR diffs with deterministic local stand-ins for review, critic, and selector model stages. The live run uses the configured model provider when `GROQ_API_KEY` is available.

## Current Results

The checked-in artifact [evaluation/real_world_results.json](evaluation/real_world_results.json) was produced on April 25, 2026 with live GitHub PR diffs, mocked model stages, and real issue-level scoring.

### Summary

| Metric | Value |
|---|---:|
| Cases | 8 |
| Clean cases | 5 |
| Issue-detection cases | 3 |
| Expected issues | 5 |
| Success rate | 100.0% |
| Avg precision | 1.00 |
| Avg recall | 1.00 |
| Avg F1 | 1.00 |
| Total false positives | 0 |
| Branching rate | 12.5% |

### Per-Case Table

| PR | Category | Expected Issues | Precision | Recall | F1 | False Positives |
|---|---|---:|---:|---:|---:|---:|
| [supabase/auth#2480](https://github.com/supabase/auth/pull/2480) | `small` | 0 | 1.00 | 1.00 | 1.00 | 0 |
| [fastapi/fastapi-cli#182](https://github.com/fastapi/fastapi-cli/pull/182) | `backend_python` | 0 | 1.00 | 1.00 | 1.00 | 0 |
| [fastapi/fastapi#14400](https://github.com/fastapi/fastapi/pull/14400) | `backend_python` | 0 | 1.00 | 1.00 | 1.00 | 0 |
| [expressjs/express#6944](https://github.com/expressjs/express/pull/6944) | `backend_node` | 0 | 1.00 | 1.00 | 1.00 | 0 |
| [supabase/auth#2479](https://github.com/supabase/auth/pull/2479) | `security` | 0 | 1.00 | 1.00 | 1.00 | 0 |
| [ishi-gupta/vuln-test-suite#59](https://github.com/ishi-gupta/vuln-test-suite/pull/59) | `issue_security` | 1 | 1.00 | 1.00 | 1.00 | 0 |
| [nisarg-vibhakar-ead/pr-review-playground#1](https://github.com/nisarg-vibhakar-ead/pr-review-playground/pull/1) | `issue_validation` | 2 | 1.00 | 1.00 | 1.00 | 0 |
| [ZaidBuilds/Hey-Jarvis#143](https://github.com/ZaidBuilds/Hey-Jarvis/pull/143) | `issue_error_handling` | 2 | 1.00 | 1.00 | 1.00 | 0 |

## Honest Limitations

- The dataset is still small and manually curated.
- Ground truth is issue-level and practical, not a formal security audit of each repository.
- Public PRs can change, disappear, or become unavailable, so live runs may fail for reasons outside the project.
- The checked-in results use deterministic mocked model stages over real PR diffs, not a live provider response.
- Live-model results can vary with provider availability, rate limits, and model behavior.
- Smart diff filtering is intentional; it validates bounded review behavior, not full-repository exhaustive analysis.

## Why This Matters

The real-world layer now measures both sides of review credibility: avoiding fake findings on clean PRs and recalling real issue-level bugs on public PR diffs. It does not replace the curated synthetic scenarios, but it closes the previous gap where real-world evaluation mostly measured false positives.
