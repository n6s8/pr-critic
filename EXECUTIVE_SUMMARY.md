# Executive Summary - PR Critic

## Overview

PR Critic is a pull request review system built around a real multi-agent workflow rather than a single review prompt. It fetches a diff through an MCP GitHub tool boundary, plans the review focus, retrieves compact local guidance, generates review candidates, scores them independently, removes unsupported findings, and returns a synthesized review together with retrieval evidence and a structured execution trace.

The goal is deliberately narrow: provide a credible, inspectable diff review workflow rather than a general autonomous coding agent.

## What Makes The System Real

- The workflow is explicit: fetch, planner, retrieve, review, critic, optional branch, branch critic, false-positive guard, synthesis, selector
- GitHub integration is exposed through MCP tools: `get_pull_request` and `get_pull_request_diff`
- Every surviving issue is grounded in a changed file, line, code snippet, and source id
- The frontend renders backend-owned outputs only
- Failure and degraded states are explicit instead of being hidden behind fake success responses

## Current Execution Model

### Smart Diff Filtering

For normal PRs, the system does not send the full diff to the initial review prompt. It ranks files and hunks before the LLM call, prioritizing backend code, risky paths and patterns, and larger changes. Docs and low-signal config are deprioritized. Only the top review chunks are sent to the first pass.

### Token-Aware Prompting

The first review prompt is bounded. In practice the filtered diff packet stays around 900 tokens, and the total initial prompt stays in a controlled range, typically around 1000-1500 tokens once compact retrieval context and prompt overhead are included.

### Compact RAG

Retrieval remains part of the architecture, but it is deliberately small:

- `top_k=2`
- short snippets only
- structured evidence returned to the UI

### Grounding And False-Positive Control

The review is not accepted as-is. A guard agent validates every issue against changed lines and rejects weak generic suggestions. The selector then synthesizes grounded issues across candidates so branching improves coverage without losing evidence.

### Repository-Aware Signals

For GitHub PRs, the backend also collects lightweight repository signals:

- changed file types
- best-effort `flake8` findings for Python
- best-effort `eslint` findings for JS/TS

These signals are summarized and added to the initial review prompt without changing the graph structure.

### Adaptive Execution

Branching is not the default path. The branch path runs only when:

- the initial score is below threshold
- the request is not rate-limited
- the PR is not in large-PR mode
- enough token budget remains to justify more model calls

### Large PR Mode

Very large diffs trigger a stability-first mode. In that mode, branching and review-generation LLM calls are skipped, and the system returns an explicit `large_pr_partial` candidate with partial-coverage limitations instead of attempting broad multi-pass coverage.

### Honest Degraded Mode

If GitHub fetch fails, the API returns an error instead of a fake review. If the LLM is rate-limited, the pipeline returns an explicit fallback candidate and trace warnings instead of pretending a full review was produced.

## Evaluation Position

The evaluation framework is issue-level and structured:

- expected issues are defined as `{ file, type, description }`
- detected issues are extracted from the selected review
- metrics include precision, recall, F1, and false positives

This is materially better than keyword scoring, but it is still not a human benchmark. The scenarios are local and synthetic, not sampled from production PR history.

Current deterministic mock evaluation results:

- 20/20 successful scenarios
- average precision: 1.0
- average recall: 1.0
- average F1: 1.0
- false positives: 0

CI reflects that split:

- mock evaluation validates the workflow and issue-level scoring logic
- a live evaluation sanity job can run when real model credentials are configured
- a separate real-world dataset of public GitHub PRs is available for non-synthetic evaluation of false-positive control on real diffs

## Strengths

- Clear separation of responsibilities across review, scoring, branching, and selection
- Real MCP integration for PR metadata and diff access
- Evidence-grounded issue contract with citations/source ids
- Bounded token usage and explicit rate-limit handling
- Security controls for input validation, prompt injection detection, PII masking, and optional API-key auth
- Observability via structured JSON logs, agent latency, estimated token/cost metrics, MCP metrics, `/metrics`, `/health`, and `/feedback`
- Frontend state that reflects real backend outputs and degraded modes
- Inspectable retrieval and trace data

## Limitations

- The system reviews a prioritized subset of the diff rather than full repository context
- Large PRs are intentionally partial-analysis mode
- Retrieval is local and limited
- Caches and rate limiting are in-memory
- Repository-aware signals are best-effort, not guaranteed
- Evaluation is narrower than a human-labeled benchmark on real pull requests

## Bottom Line

This project is a strong capstone-grade AI engineering system: it demonstrates real MCP integration, multi-agent orchestration, local RAG, evidence-grounded review output, safety controls, observability, tests, and repeatable evaluation. It is scoped as a capstone system, but the architecture and quality gates are credible foundations for a production PR review assistant.
