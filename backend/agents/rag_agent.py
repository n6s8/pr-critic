"""
RAG Agent — retrieves relevant coding standards for the diff.

Priority order:
  1. TF-IDF local index (built by scripts/build_corpus.py)
  2. Static placeholder (graceful fallback if corpus not built)
"""
import time
from backend.graph.state import PRCriticState
from backend.observability.logger import log_start, log_end, log_error

_PLACEHOLDER = """
[PEP 8]
- Use 4 spaces per indent. Use snake_case for names.
- Never bare except. Avoid mutable default args.
- Comparisons to None: use `is` / `is not`.

[OWASP Top 10]
- A02: Never MD5/SHA1 for passwords — use bcrypt/argon2.
- A03: Never interpolate user input into SQL — use parameterised queries.
- A07: Never hardcode secrets. Use environment variables.

[Clean Code]
- Functions do one thing. Keep under ~20 lines.
- Descriptive names. No single-letter vars outside loops.
- Never swallow exceptions silently.
- Docstrings on all public functions.
"""


def _retrieve(diff: str, language: str) -> tuple[str, list[str], str]:
    try:
        from backend.rag.tfidf_retriever import retrieve_context, get_collection_stats
        stats = get_collection_stats()
        if stats["total_chunks"] > 0:
            query = f"Python code review. Language: {language}.\n{diff[:800]}"
            ctx, sources = retrieve_context(query, top_k=6)
            if ctx.strip():
                return ctx, sources, "tfidf"
    except Exception:
        pass
    return _PLACEHOLDER, ["placeholder"], "placeholder"


def rag_agent(state: PRCriticState) -> dict:
    t0 = time.perf_counter()
    diff = state.get("pr_diff", "")
    lang = state.get("pr_metadata", {}).get("language", "Python")
    log_start("rag_agent", {"diff_length": len(diff), "language": lang})

    try:
        ctx, sources, mode = _retrieve(diff, lang)
        ev = log_end("rag_agent", {
            "mode": mode, "sources": sources, "context_length": len(ctx),
        }, (time.perf_counter() - t0) * 1000)
        return {
            "retrieved_context": ctx,
            "retrieval_sources": sources,
            "trace": state.get("trace", []) + [ev],
        }
    except Exception as exc:
        ev = log_error("rag_agent", str(exc))
        return {
            "retrieved_context": _PLACEHOLDER,
            "retrieval_sources": ["placeholder"],
            "trace": state.get("trace", []) + [ev],
        }