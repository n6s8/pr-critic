# PR Critic

Multi-agent system for automated pull request analysis.

---

## Overview

PR Critic analyzes pull requests using a structured multi-agent pipeline:

Fetch → RAG → Review → Critic → Branch → Select

Each step is handled by a dedicated agent. The system evaluates code changes, generates reviews, scores their quality, and dynamically decides whether additional analysis strategies are required.

---

## Architecture

Pipeline flow:

- Fetch — retrieves PR diff and metadata  
- RAG — enriches context with relevant best practices  
- Review — generates initial code review  
- Critic — evaluates review quality (0–10)  
- Branch — triggers additional strategies if score is below threshold  
- Select — chooses the best review  

Key features:

- Multi-agent orchestration (LangGraph)
- Structured state passing between agents
- Dynamic branching based on review quality
- Deterministic behavior in mock mode

---

## Project Structure

backend/        # core logic (agents, graph, config)
data/corpus/    # RAG data
evaluation/     # evaluation scenarios and metrics
scripts/        # utility scripts (evaluation runner)
tests/          # unit and integration tests

---

## Requirements

- Python 3.10+
- Groq API key (for live mode)

---

## Setup

pip install -r requirements.txt

Create `.env` file:

GROQ_API_KEY=your_key_here

---

## Running the Backend

uvicorn backend.api.main:app --reload --port 8000

Server will start at:

http://127.0.0.1:8000

---

## Running Tests

pytest -v

Expected:

- All tests pass
- Full pipeline coverage
- No crashes on edge cases

---

## Evaluation

Run evaluation in mock mode (no API calls):

python scripts/run_evaluation.py --mock

Run with real LLM:

python scripts/run_evaluation.py --delay 1.0

Run specific scenario:

python scripts/run_evaluation.py --scenario <name>

Run specific category:

python scripts/run_evaluation.py --categories security

Output:

evaluation/results.json

---

## Configuration

Main settings are defined in:

backend/config.py

Key parameters:

- branch_score_threshold — triggers branching
- max_branch_alternatives — number of strategies
- reasoning_model — LLM used for critic

---

## Notes

- Mock mode uses deterministic outputs for testing
- Live mode depends on external API (Groq)
- Evaluation layer is independent from pipeline logic

---

## Status

Backend and evaluation layer are complete and tested.
Frontend is not included in this version.
