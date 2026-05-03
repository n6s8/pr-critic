# PR Critic - Architecture Blueprint

## System Overview

PR Critic is a pull request review system with a FastAPI backend, a LangGraph workflow, a local TF-IDF retriever, and a React dashboard.

Request flow:

1. `POST /review` accepts a diff source
2. `fetch_agent` calls the MCP client to load PR metadata and raw diff through `get_pull_request` and `get_pull_request_diff`
3. `planner_agent` decides review focus, expected issue types, and risk terms from the diff and safety flags
4. `rag_agent` retrieves compact local guidance snippets and caches the result in memory
5. `review_agent` applies smart diff filtering, adds compact repository signals, builds one bounded review packet, and generates the initial candidate for normal PRs; for huge PRs it emits a deterministic `large_pr_partial` candidate without an LLM review-generation call
6. `critic_initial` scores the initial candidate
7. Branching happens only if the initial score is below threshold and the request is not rate-limited, not in large-PR mode, and still within token budget
8. `branch_agent` creates bounded alternative candidates with different strategies
9. `critic_branch` scores only the new branch candidates
10. `false_positive_guard_agent` removes ungrounded issues and weak suggestions without changed-line evidence
11. `synthesis_agent` summarizes the grounded artifacts across candidates
12. `selector_agent` chooses the best candidate, synthesizes all grounded issues into the final review, and records `selector_reason`
13. The API returns the structured response contract for the frontend

The architecture is intentionally modest:

- Retrieval is local and deterministic, not vector-database based
- The graph runs per request with in-memory state
- Rate limiting and caches are in-memory
- The frontend renders completed backend responses, not simulated or streamed states

## MCP Integration

```text
fetch_agent
  -> GitHubMCPClient.call_tool("get_pull_request")
  -> GitHubMCPClient.call_tool("get_pull_request_diff")
      -> backend/mcp_server/github_tools.py
          -> mock/eval/raw-diff provider or GitHub REST provider
```

The fetch agent no longer calls GitHub REST directly. GitHub access is isolated behind a local MCP server boundary with two typed tools:

- `get_pull_request(pr_url)`: returns PR title, author, branches, files, language, and URL
- `get_pull_request_diff(pr_url)`: returns the unified diff

The default transport is `MCP_TRANSPORT=inprocess` so local tests and demos do not require launching a child process. The `stdio` transport path is implemented for environments that install and run the MCP SDK server process.

## Components

### Frontend

- React 18 + TypeScript + Vite
- Renders backend-owned metadata, diff content, retrieval snippets, review candidates, issues, and trace
- Uses backend status and trace to show degraded mode honestly
- Does not parse logs or invent missing data

### Backend API

- FastAPI
- Endpoints:
  - `POST /review`
  - `GET /review/mock-prs`
  - `GET /health`
  - `GET /metrics`
  - `POST /feedback`
- Normalizes trace events and returns the response contract consumed by the frontend
- Returns proper HTTP failures for upstream fetch errors and empty-candidate conditions

### Orchestration

- LangGraph
- Shared state: `PRCriticState`
- Nodes:
  - `fetch`
  - `planner`
  - `rag`
  - `review`
  - `critic`
  - `branch`
  - `critic_branch`
  - `guard`
  - `synthesis`
  - `selector`

### Retrieval

- Strategy: TF-IDF over a local corpus
- Retrieval budget:
  - `top_k=2`
  - compact snippets only
- If retrieval is unavailable, the system returns empty retrieval evidence instead of fabricated guidance

## Agent Design

| Agent | Input | Output | Responsibility |
|---|---|---|---|
| `fetch_agent` | `pr_url` | `FetchArtifact`, `pr_diff`, `pr_metadata`, `request_cache_key`, `large_pr_mode`, `repo_signals` | Load diff and metadata through MCP tools, mask PII, detect prompt injection, then collect best-effort repository-aware signals |
| `planner_agent` | diff, metadata, safety flags | `review_plan` | Decide focus area, risk terms, and expected issue types |
| `rag_agent` | `pr_diff`, language, review plan | `RetrievalArtifact`, `retrieved_context`, `retrieval_sources`, `retrieval_hits` | Retrieve compact language-aware review guidance |
| `review_agent` | diff, metadata, retrieval context, repo signals | initial candidate or `large_pr_partial` candidate | Build the smart filtered diff packet, enforce prompt budget, generate the first grounded review candidate for normal PRs, and return an explicit partial-analysis candidate for huge PRs |
| `critic_initial` | diff, candidates, scores | updated `scores`, optional `branch_taken` | Score the initial candidate and decide whether branching is justified |
| `branch_agent` | diff, metadata, retrieval context, prior score | additional candidates | Generate bounded alternative candidates with different review strategies |
| `critic_branch` | diff, candidates, scores | updated `scores` | Score only branch candidates |
| `false_positive_guard_agent` | candidates, diff, retrieval hits | `CriticReport`, `candidate_grounded_issues` | Reject issues without changed-line evidence and suppress weak generic findings |
| `synthesis_agent` | grounded issues, retrieval sources | `FinalDecision` summary | Summarize grounded issue coverage, confidence, and limitations |
| `selector_agent` | candidates, scores, diff, grounded issues | `selected_index`, `selector_reason`, `branch_improvement`, final grounded review | Choose the best candidate and synthesize grounded issues across candidates |

## Execution Controls

### Smart Diff Filtering

The normal review prompt is not built from the full diff. The system ranks files and chunks before the LLM call.

- Hard limits:
  - `MAX_FILES = 10`
  - `MAX_CHUNKS = 5`
  - `MAX_LINES_PER_CHUNK = 200`
- Review packet behavior:
  - prioritizes backend code, risky paths and patterns, and larger code changes
  - deprioritizes markdown and low-signal config files
  - keeps the first review packet to the top 2-3 high-priority chunks

### Token-Aware Prompting

- Review diff packet budget: about 900 tokens
- Typical initial review prompt: around 1000-1500 tokens once compact RAG and prompt overhead are added
- Branching budget gate: branch routing is skipped when the initial review prompt is already too large
- Critic and selector also use filtered diff packets rather than raw diff excerpts

### Repository-Aware Signals

For GitHub PRs, the backend attempts a lightweight repository checkout and collects:

- changed file types
- basic lint findings from `flake8` for Python files when available
- basic lint findings from `eslint` for JS/TS files when available

These signals are compacted before being included in the initial review prompt. If checkout or linting is unavailable, the system records that honestly and continues without fabricating signals.

### Large PR Mode

When the raw diff exceeds the large-PR threshold:

- `large_pr_mode = true`
- branching is disabled
- review-generation LLM calls are skipped
- the selected candidate strategy is `large_pr_partial`
- the review remains partial and stability-focused
- the system still returns a selected review, issues, score, and trace

### Degraded Mode

When the LLM is rate-limited:

- the request state flips to `rate_limited = true`
- downstream LLM stages are skipped
- the system returns an explicit fallback candidate instead of crashing or fabricating a review

### Security Controls

- `ReviewRequest.pr_url` is validated before orchestration. Accepted sources are GitHub PR URLs, `mock://`, `eval://`, and bounded raw unified diffs.
- Non-GitHub HTTP(S) URLs are rejected to avoid SSRF-style fetch paths.
- Diff text is scanned for prompt-injection phrases such as "ignore previous instructions" and the flag is carried in `safety_flags`.
- Emails and secret values are masked before logs and prompts while preserving useful code shape such as `SECRET = "[REDACTED_SECRET]"`.
- `PR_CRITIC_API_KEY` enables simple API-key middleware for non-local deployments.

## Shared State

```python
pr_url: str
pr_diff: str
pr_metadata: dict
retrieved_context: str
retrieval_sources: list[str]
retrieval_hits: list[dict]
repo_signals: dict
candidates: list[dict]
scores: list[dict]
review_plan: dict
safety_flags: dict
agent_messages: list[dict]
candidate_grounded_issues: dict[str, list[dict]]
grounded_issues: list[dict]
synthesis_report: dict
branch_taken: bool
branch_improvement: float | None
selected_index: int | None
selector_reason: str
rate_limited: bool
large_pr_mode: bool
request_cache_key: str
branch_skipped_reason: str
llm_input_tokens: int
branch_budget_available: bool
trace: list[dict]
request_context: dict
```

Key invariants:

- `candidates[index]` is the candidate reviewed by `scores[candidate_index=index]`
- `selected_index` always points into `candidates`
- `branch_taken` records that the graph took the branch route, not that branching necessarily improved the result
- `branch_improvement` is only populated when branching occurred and both baseline and selected scores exist
- `rate_limited` and `large_pr_mode` are request-level execution facts carried through the graph
- `repo_signals` is a best-effort summary, not a guarantee that repository checkout or linting succeeded
- `candidate_grounded_issues` stores only findings that include file, line, changed-line snippet, and source id
- `grounded_issues` is the final synthesized issue set returned by the API and rendered by the frontend

## API Contract

```json
{
  "language": "Python",
  "files_changed": ["auth/utils.py"],
  "diff_size": 412,
  "pr_metadata": {
    "title": "Security fix",
    "author": "octocat",
    "base_branch": "main",
    "head_branch": "fix/auth",
    "language": "Python",
    "files_changed": ["auth/utils.py"],
    "pr_url": "https://github.com/org/repo/pull/42"
  },
  "diff": "diff --git a/auth/utils.py ...",
  "retrieval": [
    {
      "source": "owasp_top10",
      "section": "A03 Injection",
      "snippet": "Use parameterized SQL queries.",
      "relevance": 0.94
    }
  ],
  "candidates": [
    {
      "index": 0,
      "id": "initial-0",
      "strategy": "initial",
      "review": "## Summary\n...",
      "score": 8.5,
      "score_rationale": "Strong coverage of the visible risks.",
      "critic_issues": ["sql injection", "md5"]
    }
  ],
  "selected_index": 0,
  "selected_review": {
    "index": 0,
    "id": "initial-0",
    "strategy": "initial",
    "review": "## Summary\n...",
    "score": 8.5,
    "score_rationale": "Strong coverage of the visible risks.",
    "critic_issues": ["sql injection", "md5"]
  },
  "score": 8.5,
  "selector_reason": "Selected the only candidate returned by the pipeline.",
  "branch_taken": false,
  "branch_improvement": null,
  "issues": [
    {
      "severity": "critical",
      "issue_type": "sql_injection",
      "file": "auth/utils.py",
      "line": 4,
      "message": "Use parameterized queries.",
      "code_snippet": "query = f\"SELECT * FROM users WHERE id = {user_id}\"",
      "source_id": "owasp_top10:A03 Injection"
    }
  ],
  "trace": [
    {
      "agent": "fetch_agent",
      "event": "end",
      "status": "completed",
      "timestamp": "2026-04-13T15:54:06.892849+00:00",
      "duration_ms": 23.0,
      "data": {
        "language": "Python",
        "diff_length": 412
      }
    }
  ]
}
```

## Evaluation Design

Per-run metrics:

- `precision`
- `recall`
- `f1`
- `false_positives`
- `review_score`
- `triggered_branch`
- `branch_improvement`
- `selected_strategy`

Summary metrics:

- `avg_precision`
- `avg_recall`
- `avg_f1`
- `total_false_positives`
- `branching_rate_pct`
- `avg_branch_improvement`
- `avg_latency_ms`
- MCP tool latency
- agent latency and estimated token/cost usage
- retrieval hit count and cache hits
- user feedback count and average rating

Important evaluation constraints:

- The matcher is issue-level, not keyword-based
- Scenarios are structured local diffs, not human-labeled production PRs
- Mock mode preserves the evaluation logic but replaces live model calls
- CI can run a live evaluation sanity subset when a real `GROQ_API_KEY` secret is configured

## Limitations

- The system analyzes a prioritized subset of the diff before the main review call, not the full PR surface
- Repository-aware signals are best-effort and depend on runtime access to external tools
- Large-PR mode is intentionally partial-analysis mode
- Retrieval is local and small in scope
- Caches and rate limiting are process-local; the cache API is prepared for a distributed backend, but Redis is not implemented yet
- There is no full repository analysis, no guaranteed static-analysis tool coverage across all languages, and no human-judged benchmark loop

## Trade-offs

- Local TF-IDF retrieval is simpler and more deterministic than a vector database for a small corpus
- Smart diff filtering reduces token load and rate-limit risk, but it also means low-priority files may be omitted from the first review pass
- Scenario-based evaluation is easy to repeat and inspect, but it is narrower than a benchmark on real reviewer decisions
