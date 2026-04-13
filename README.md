# PR Critic

PR Critic is a multi-agent pull request review system. It fetches a PR diff, enriches it with retrieval context, generates review candidates, scores them, and returns a structured response for a React dashboard.

The repository contains:

- A FastAPI backend that runs the review pipeline
- A React + TypeScript frontend for inspection and triage
- Evaluation scripts and scenarios for repeatable testing

## What The System Does

Given a pull request diff URL, the backend executes a review workflow:

1. Fetch the diff and PR metadata
2. Retrieve supporting context from the local corpus
3. Generate a code review
4. Critique the review and score it
5. Branch into alternative strategies when needed
6. Select the best final review

The frontend renders the result as a review dashboard with score, strategies, issues, and execution trace.

## Backend Response Contract

The backend response shape is the source of truth for the frontend:

```json
{
  "score": 8.5,
  "strategies": [
    {
      "id": "initial",
      "name": "Balanced Review",
      "score": 8.5,
      "description": "Balanced review covering correctness, security, style, and maintainability."
    }
  ],
  "selected_strategy": "initial",
  "review": "## Summary\n...",
  "issues": [
    {
      "severity": "info",
      "file": "src/components/ChatWindow.tsx",
      "line": 81,
      "message": "Example issue message."
    }
  ],
  "trace": [
    {
      "agent": "fetch_agent",
      "level": "INFO",
      "message": "fetch_agent completed: language=TypeScript, diff_length=3268, in 2239ms",
      "timestamp": "2026-04-13T15:54:06.892849+00:00"
    }
  ]
}
```

## Architecture

### Review Pipeline

- `fetch_agent`: loads PR diff and metadata
- `rag_agent`: retrieves relevant guidance from local reference data
- `review_agent`: produces the initial review text
- `critic_agent`: scores the review and decides whether branching is needed
- `branch_agent`: generates alternate review strategies when the score is below threshold
- `selector_agent`: picks the final review to return

### Backend

- Framework: FastAPI
- Orchestration: LangGraph
- Models: LangChain integrations
- Observability: trace events emitted through the workflow

### Frontend

- Framework: React 18
- Build tool: Vite
- Language: TypeScript
- Styling: Tailwind CSS and component-level utility classes

## Repository Layout

```text
backend/
  agents/           Individual review pipeline agents
  api/              FastAPI app and API helpers
  graph/            Workflow state and LangGraph assembly
  mcp/              GitHub access and mock implementations
  observability/    Logging helpers
  rag/              Retrieval components

data/               Retrieval corpus and local reference material
evaluation/         Evaluation scenarios, metrics, and result outputs
frontend/           React dashboard
scripts/            Developer utilities, including evaluation runner
tests/              Automated tests
```

## Requirements

- Python 3.11 or later
- Node.js 18 or later
- npm
- `GROQ_API_KEY` for live LLM execution

## Setup

### 1. Install backend dependencies

From the repository root:

```bash
pip install -e ".[dev]"
```

### 2. Configure environment

Create a `.env` file in the repository root:

```env
GROQ_API_KEY=your_api_key
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

## Running The Project

### Start the backend

From the repository root:

```bash
uvicorn backend.api.main:app --reload --port 8000
```

Default local address:

```text
http://127.0.0.1:8000
```

### Start the frontend

In a separate terminal:

```bash
cd frontend
npm run dev
```

Default local address:

```text
http://127.0.0.1:5173
```

## API Endpoints

### `POST /review`

Runs the full review pipeline for a pull request diff URL.

Request body:

```json
{
  "pr_url": "https://github.com/org/repo/pull/123.diff"
}
```

### `GET /review/mock-prs`

Returns the list of built-in mock PRs available for local testing.

### `GET /health`

Returns service health and basic runtime metadata.

## Local Development Workflow

### Run tests

From the repository root:

```bash
pytest -v
```

### Run evaluation in mock mode

Mock mode does not require live model calls.

```bash
python scripts/run_evaluation.py --mock
```

### Run evaluation in live mode

```bash
python scripts/run_evaluation.py --delay 1.0
```

### Run a specific scenario

```bash
python scripts/run_evaluation.py --scenario sec/sql-injection
```

### Run selected categories

```bash
python scripts/run_evaluation.py --categories security,style
```

Evaluation results are written to:

```text
evaluation/results.json
```

## Configuration

Runtime settings are defined in `backend/config.py`.

Key settings include:

- Branch score threshold
- Maximum number of branch alternatives
- Generation and reasoning model selection
- GitHub integration behavior

## Notes

- The backend is the owner of the response contract consumed by the frontend.
- The frontend should use only the documented fields in the response payload.
- Mock mode is intended for deterministic local testing and evaluation.
- Live mode depends on valid external model credentials.

## Troubleshooting

### Backend starts but `/review` fails

Check:

- `.env` exists in the repository root
- `GROQ_API_KEY` is set for live mode
- The PR diff URL is reachable and valid

### Frontend loads but shows no data

Check:

- Backend is running on port `8000`
- Frontend dev server is running on port `5173`
- Browser network requests to `/review` are succeeding

### Evaluation run fails

Check:

- Python environment is active
- Project dependencies are installed
- Use `--mock` first to validate the pipeline locally

## Current Scope

This repository is structured for iterative work on:

- Backend review quality
- Branching and strategy selection
- Frontend review UX
- Evaluation coverage and repeatability

The intended outcome is a production-oriented developer tool, not a demo-only prototype.
