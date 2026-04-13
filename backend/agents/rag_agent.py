"""
agents/rag_agent.py — Language-aware RAG Agent.

Retrieves relevant coding standards from the corpus using the detected
language to focus the query. Falls back to per-language placeholder
context when corpus is empty or unavailable.
"""
import time
from backend.graph.state import PRCriticState
from backend.observability.logger import log_start, log_end, log_error

# Per-language placeholder context — used when corpus is not built yet
_PLACEHOLDERS: dict[str, str] = {
    "Python": """
[PEP 8 — Python Style Guide]
- Use 4 spaces per indent. snake_case for functions/variables.
- Never use bare `except:`. Avoid mutable default arguments.
- Comparisons to None: use `is` / `is not`, not ==.
- Add docstrings to all public functions and classes.

[OWASP Top 10 — Security]
- A02: Never use MD5/SHA1 for passwords — use bcrypt/argon2.
- A03: Never interpolate user input into SQL — use parameterised queries.
- A07: Never hardcode secrets or API keys — use environment variables.
- A08: Never deserialize untrusted data with pickle.

[Clean Code]
- Functions do one thing. Keep under ~20 lines.
- Descriptive names. No single-letter vars outside loops.
- Never swallow exceptions silently.
""",

    "TypeScript": """
[TypeScript Best Practices]
- Always use explicit types for function parameters and return values.
- Avoid `any` — use `unknown` and narrow it properly.
- Enable strict mode in tsconfig.json.
- Use optional chaining (?.) and nullish coalescing (??) for null safety.

[React / Hooks]
- Include all used variables in useEffect dependency arrays.
- Never call hooks inside conditions or loops.
- Never use dangerouslySetInnerHTML with unsanitized user input (XSS risk).
- Use useCallback/useMemo to avoid unnecessary re-renders.

[Security]
- Never store auth tokens in localStorage — use httpOnly cookies.
- Validate all URLs before using them in href or src attributes.
- Handle all promise rejections — never leave floating promises.
""",

    "JavaScript": """
[JavaScript Best Practices]
- Prefer const over let. Never use var.
- Always handle promise rejections with try/catch or .catch().
- Avoid == ; always use ===.
- Never use eval() with user input.

[Security — OWASP]
- Never concatenate user input into HTML strings (XSS).
- Validate and sanitize all user input.
- Never hardcode secrets in frontend code.
""",

    "Go": """
[Go Best Practices]
- Always check and handle errors — never ignore them with _.
- Use defer for resource cleanup (Close, Unlock).
- Prefer errors.Is() / errors.As() for error comparison.
- Use context.Context for cancellation and timeout propagation.

[Security]
- Use parameterised queries (database/sql) — never concatenate SQL.
- Validate all inputs at API boundaries.
- Use crypto/rand for cryptographic randomness, not math/rand.
""",

    "Rust": """
[Rust Best Practices]
- Use Result<T, E> and ? operator for error propagation.
- Avoid unwrap() in production code — use expect() with a message or match.
- Prefer owned types over references when lifetime complexity grows.
- Use clippy lints to catch common issues.
""",

    "Java": """
[Java Best Practices]
- Use try-with-resources for AutoCloseable resources.
- Override equals() and hashCode() together.
- Prefer Optional<T> over null returns.
- Use PreparedStatement for all SQL — never concatenate.

[OWASP Security]
- A03: Use PreparedStatement for all SQL queries.
- A02: Use BCrypt for password hashing. Never MD5/SHA1.
- A07: Load secrets from environment — never hardcode.
""",

    "Unknown": """
[General Code Review Standards]
- Handle all error conditions explicitly.
- Never hardcode secrets, passwords, or API keys.
- Validate all user input at system boundaries.
- Use descriptive names. Add comments for non-obvious logic.
- Keep functions small and focused on one responsibility.
""",
}

# Language → specific query terms for better TF-IDF retrieval
_LANGUAGE_RAG_TERMS: dict[str, str] = {
    "Python":     "Python code review PEP8 style security OWASP exception handling",
    "TypeScript": "TypeScript JavaScript ESLint type safety React hooks security best practices",
    "JavaScript": "JavaScript ESLint code review security async promises best practices",
    "Go":         "Go Golang error handling interfaces concurrency best practices",
    "Rust":       "Rust memory safety ownership borrowing error handling",
    "Java":       "Java code review SOLID principles security OWASP best practices",
    "Kotlin":     "Kotlin Android coroutines null safety best practices",
    "C#":         "C# .NET LINQ async await security best practices",
    "Ruby":       "Ruby Rails code review security best practices",
    "PHP":        "PHP security OWASP injection XSS best practices",
}


def _build_query(diff: str, language: str) -> str:
    """Build a language-specific TF-IDF retrieval query."""
    lang_terms = _LANGUAGE_RAG_TERMS.get(language, "code review best practices security")

    # Extract key lines added in the diff as additional signal
    diff_lines = [
        line[1:].strip()
        for line in diff.split("\n")
        if line.startswith("+") and not line.startswith("+++") and line.strip() not in ("+", "")
    ]
    diff_sample = " ".join(diff_lines)[:200]

    return f"{lang_terms}\n{diff_sample}"


def _retrieve(diff: str, language: str) -> tuple[str, list[str], str]:
    """
    Try TF-IDF corpus first, fall back to per-language placeholder.
    Returns (context_text, sources, mode).
    """
    try:
        from backend.rag.tfidf_retriever import retrieve_context, get_collection_stats
        stats = get_collection_stats()
        if stats["total_chunks"] > 0:
            query = _build_query(diff, language)
            ctx, sources = retrieve_context(query, top_k=6)
            if ctx.strip():
                return ctx, sources, "tfidf"
    except Exception:
        pass

    placeholder = _PLACEHOLDERS.get(language, _PLACEHOLDERS["Unknown"])
    return placeholder, ["placeholder"], "placeholder"


def rag_agent(state: PRCriticState) -> dict:
    t0 = time.perf_counter()
    diff = state.get("pr_diff", "")
    lang = state.get("pr_metadata", {}).get("language", "Unknown")
    log_start("rag_agent", {"diff_length": len(diff), "language": lang})

    try:
        ctx, sources, mode = _retrieve(diff, lang)
        ev = log_end("rag_agent", {
            "mode": mode, "language": lang,
            "sources": sources, "context_length": len(ctx),
        }, (time.perf_counter() - t0) * 1000)
        return {
            "retrieved_context": ctx,
            "retrieval_sources": sources,
            "trace": state.get("trace", []) + [ev],
        }
    except Exception as exc:
        ev = log_error("rag_agent", str(exc))
        placeholder = _PLACEHOLDERS.get(lang, _PLACEHOLDERS["Unknown"])
        return {
            "retrieved_context": placeholder,
            "retrieval_sources": ["placeholder"],
            "trace": state.get("trace", []) + [ev],
        }