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


def _build_query(diff: str, language: str) -> str:
    lang_terms = _LANGUAGE_RAG_TERMS.get(language, "code review best practices security")
    diff_lines = [
        line[1:].strip()
        for line in diff.split("\n")
        if line.startswith("+") and not line.startswith("+++") and line.strip() not in ("+", "")
    ]
    diff_sample = " ".join(diff_lines)[:300]
    return f"{lang_terms}\n{diff_sample}"


def _retrieve(diff: str, language: str) -> tuple[str, list[str], list[RetrievalHit], str]:
    try:
        from backend.rag.tfidf_retriever import build_corpus, get_collection_stats, retrieve_context

        stats = get_collection_stats()
        if stats["total_chunks"] == 0:
            build_corpus()
            stats = get_collection_stats()
        if stats["total_chunks"] > 0:
            query = _build_query(diff, language)
            context, sources, hits = retrieve_context(query, top_k=6)
            if context.strip():
                return (
                    context,
                    sources,
                    [
                        {
                            "source": hit["source"],
                            "section": hit["section"],
                            "snippet": hit["text"],
                            "relevance": hit["relevance"],
                        }
                        for hit in hits
                    ],
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
        cache_key = build_cache_key(language, diff)
        (context, sources, hits, mode), cache_hit = _RAG_CACHE.get_or_compute(
            cache_key,
            lambda: _retrieve(diff, language),
        )
        end_event = log_end(
            "rag_agent",
            {
                "mode": mode,
                "language": language,
                "sources": sources,
                "context_length": len(context),
                "hit_count": len(hits),
                "cache_hit": cache_hit,
            },
            (time.perf_counter() - started_at) * 1000,
        )
        return {
            "retrieved_context": context,
            "retrieval_sources": sources,
            "retrieval_hits": hits,
            "trace": trace + [start_event, end_event],
        }
    except Exception as exc:
        error_event = log_error("rag_agent", str(exc))
        return {
            "retrieved_context": "",
            "retrieval_sources": [],
            "retrieval_hits": [],
            "trace": trace + [start_event, error_event],
        }
