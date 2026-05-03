"""
Language-aware RAG agent with in-memory context caching.

Retrieval is visible to both the prompt layer and the frontend through
structured hits, not just a flattened text blob. If the local corpus is
unavailable, the agent returns no retrieval context instead of fabricated data.
"""
from __future__ import annotations

import time

from backend.config import settings
from backend.graph.state import RagAgentInput, RagAgentOutput, RetrievalHit
from backend.observability.logger import log_end, log_error, log_start, log_structured
from backend.utils.cache import TTLCache, build_cache_key

_LANGUAGE_RAG_TERMS: dict[str, str] = {
    "Python": "Python code review PEP8 style security OWASP exception handling",
    "TypeScript": "TypeScript JavaScript ESLint type safety React hooks security best practices",
    "JavaScript": "JavaScript ESLint code review security async promises best practices",
    "Go": "Go Golang error handling interfaces concurrency best practices",
    "Rust": "Rust memory safety ownership borrowing error handling",
    "Java": "Java code review SOLID principles security OWASP best practices",
    "Kotlin": "Kotlin Android coroutines null safety best practices",
    "C#": "C# .NET LINQ async await security best practices",
    "Ruby": "Ruby Rails code review security best practices",
    "PHP": "PHP security OWASP injection XSS best practices",
}

_RAG_CACHE: TTLCache[tuple[str, list[str], list[RetrievalHit], str]] = TTLCache(
    "rag_context",
    settings.caches.rag_ttl_seconds,
    max_size=128,
)
_RAG_TOP_K = 2
_RAG_SNIPPET_CHARS = 180


def _build_query(diff: str, language: str, review_plan: dict | None = None) -> str:
    lang_terms = _LANGUAGE_RAG_TERMS.get(language, "code review best practices security")
    plan = review_plan or {}
    focus_terms = " ".join(
        [
            str(plan.get("focus", "")),
            " ".join(str(item) for item in plan.get("risk_terms", [])),
            " ".join(str(item) for item in plan.get("expected_issue_types", [])),
        ]
    )
    normalized_diff = diff.lower()
    risk_terms: list[str] = []
    if "md5" in normalized_diff or "sha1" in normalized_diff or "hashlib" in normalized_diff:
        risk_terms.extend(["password hashing", "crypto", "owasp"])
    if "password" in normalized_diff or "token" in normalized_diff or "secret" in normalized_diff:
        risk_terms.extend(["authentication", "credential security"])
    if "select " in normalized_diff or "insert " in normalized_diff or "query" in normalized_diff:
        risk_terms.extend(["sql injection", "database security"])

    diff_lines = [
        line[1:].strip()
        for line in diff.split("\n")
        if line.startswith("+") and not line.startswith("+++") and line.strip() not in ("+", "")
    ]
    diff_sample = " ".join(diff_lines)[:180]
    return f"{lang_terms}\n{focus_terms}\n{' '.join(risk_terms)}\n{diff_sample}".strip()


def _compact_snippet(text: str, *, max_chars: int = _RAG_SNIPPET_CHARS) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3].rstrip()}..."


def _build_compact_context(hits: list[dict]) -> tuple[str, list[RetrievalHit]]:
    compact_hits: list[RetrievalHit] = []
    for hit in hits[:_RAG_TOP_K]:
        compact_hits.append(
            {
                "source": hit["source"],
                "section": hit["section"],
                "snippet": _compact_snippet(hit["text"]),
                "relevance": hit["relevance"],
            }
        )

    context = "\n".join(
        f"[{hit['source']}:{hit['section']}] {hit['snippet']}"
        for hit in compact_hits
    )
    return context, compact_hits


def _retrieve(diff: str, language: str, review_plan: dict | None = None) -> tuple[str, list[str], list[RetrievalHit], str]:
    try:
        from backend.rag.tfidf_retriever import build_corpus, get_collection_stats, retrieve_hits

        stats = get_collection_stats()
        if stats["total_chunks"] == 0:
            build_corpus()
            stats = get_collection_stats()
        if stats["total_chunks"] > 0:
            query = _build_query(diff, language, review_plan)
            hits = retrieve_hits(query, top_k=_RAG_TOP_K)
            if hits:
                context, compact_hits = _build_compact_context(hits)
                sources = sorted({hit["source"] for hit in compact_hits})
                return (
                    context,
                    sources,
                    compact_hits,
                    "tfidf",
                )
            return "", [], [], "empty"
    except Exception as exc:
        log_structured(
            "WARNING",
            "rag_retrieval_fallback",
            agent="rag_agent",
            language=language,
            error_type=type(exc).__name__,
            error=str(exc),
        )
    return "", [], [], "unavailable"


def rag_agent(state: RagAgentInput) -> RagAgentOutput:
    started_at = time.perf_counter()
    diff = state.get("pr_diff", "")
    language = state.get("pr_metadata", {}).get("language", "Unknown")
    trace = list(state.get("trace", []))
    start_event = log_start("rag_agent", {"diff_length": len(diff), "language": language})

    try:
        request_cache_key = state.get("request_cache_key", "")
        review_plan = state.get("review_plan", {})
        cache_key = build_cache_key(
            request_cache_key or diff,
            language,
            review_plan.get("focus", "balanced") if isinstance(review_plan, dict) else "balanced",
            ",".join(review_plan.get("expected_issue_types", [])) if isinstance(review_plan, dict) else "",
            "rag",
        )
        (context, sources, hits, mode), cache_hit = _RAG_CACHE.get_or_compute(
            cache_key,
            lambda: _retrieve(diff, language, review_plan),
        )
        end_event = log_end(
            "rag_agent",
            {
                "mode": mode,
                "language": language,
                "sources": sources,
                "context_length": len(context),
                "hit_count": len(hits),
                "top_k": _RAG_TOP_K,
                "snippet_chars": _RAG_SNIPPET_CHARS,
                "cache_hit": cache_hit,
                "review_focus": review_plan.get("focus", "balanced") if isinstance(review_plan, dict) else "balanced",
            },
            (time.perf_counter() - started_at) * 1000,
        )
        return {
            "retrieved_context": context,
            "retrieval_sources": sources,
            "retrieval_hits": hits,
            "rate_limited": bool(state.get("rate_limited", False)),
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "repo_signals": state.get("repo_signals"),
            "request_cache_key": request_cache_key,
            "branch_skipped_reason": str(state.get("branch_skipped_reason", "")),
            "review_plan": review_plan,
            "safety_flags": state.get("safety_flags", {}),
            "agent_messages": list(state.get("agent_messages", [])) + [
                {
                    "agent": "rag_agent",
                    "artifact_type": "RetrievalArtifact",
                    "summary": {
                        "sources": sources,
                        "hit_count": len(hits),
                        "mode": mode,
                    },
                }
            ],
            "trace": trace + [start_event, end_event],
        }
    except Exception as exc:
        error_event = log_error("rag_agent", str(exc))
        return {
            "retrieved_context": "",
            "retrieval_sources": [],
            "retrieval_hits": [],
            "rate_limited": bool(state.get("rate_limited", False)),
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "repo_signals": state.get("repo_signals"),
            "request_cache_key": str(state.get("request_cache_key", "")),
            "branch_skipped_reason": str(state.get("branch_skipped_reason", "")),
            "review_plan": state.get("review_plan", {}),
            "safety_flags": state.get("safety_flags", {}),
            "agent_messages": state.get("agent_messages", []),
            "trace": trace + [start_event, error_event],
        }
