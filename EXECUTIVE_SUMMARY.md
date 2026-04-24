# Executive Summary - PR Critic

## Overview

PR Critic is a pull request review system built around a real multi-agent workflow rather than a single review prompt. It fetches a diff, retrieves language-aware guidance from a local corpus, generates review candidates, scores them independently, and returns the selected review together with retrieval evidence and a structured execution trace.

The goal is narrow and concrete: automate the mechanical part of code review well enough to be credible, testable, and inspectable.

## What Makes This System Different

- Real evaluation: the evaluation runner compares `expected_issues` against detected issues and reports precision, recall, F1, and false positives.
- Multi-agent selection: the system keeps explicit candidate state, scores each candidate independently, and records `selector_reason` for the final decision.
- Explainable RAG: the backend returns the retrieved sources and snippets that grounded the review.

## Technical Shape

- Backend: FastAPI + LangGraph
- Retrieval: local TF-IDF corpus
- Frontend: React + TypeScript
- Output contract: metadata, raw diff, retrieval hits, candidates, selected review, extracted issues, and structured trace

## Why The Architecture Matters

The main engineering decision in this project is the separation between generation, scoring, branching, and selection.

- `review_agent` creates the initial candidate
- `critic_agent` scores candidates independently
- `branch_agent` only runs when the initial score is below threshold
- `selector_agent` chooses the best candidate and records why it won

That split makes the system easier to reason about, test, and evaluate than a single opaque review call.

## Evaluation Position

The evaluation framework is intentionally direct. It does not assign synthetic quality points by scenario category. Instead, it checks whether the final selected review surfaced the expected issues and penalizes extra findings through false positives.

This makes the evaluation narrower than a human benchmark, but much more defensible than a demo-style "looks good" score.

## Limitations

- The retrieval corpus is still small and local
- There is no GitHub webhook or GitHub App integration
- Large PR handling is basic diff chunking, not deep file prioritization

## Trade-offs

- TF-IDF was chosen over a vector database because the corpus is small and deterministic behavior matters more than retrieval sophistication at this scale
- Local scenario-based evaluation was chosen over human labeling because it is repeatable and cheap to run, even though it is less comprehensive

## Summary

This project is strongest when judged as an engineering system, not as an AI demo. Its value comes from explicit state, visible evidence, defensible evaluation, and an honest contract between backend and frontend.
