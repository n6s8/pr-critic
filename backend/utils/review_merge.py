from __future__ import annotations

import re


_HEADING_SPLIT_RE = re.compile(r"\n(?=##\s+)")
_VERDICT_RE = re.compile(r"\b(APPROVE|REQUEST_CHANGES|COMMENT)\b", re.IGNORECASE)


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines:
        cleaned = line.strip()
        normalized = re.sub(r"\s+", " ", cleaned.lower())
        if not cleaned or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(cleaned)
    return deduped


def _parse_sections(review_text: str) -> dict[str, list[str]]:
    normalized = review_text.replace("\r\n", "\n").strip()
    if not normalized:
        return {}

    sections: dict[str, list[str]] = {}
    for chunk in _HEADING_SPLIT_RE.split(normalized):
        chunk = chunk.strip()
        if not chunk:
            continue
        if not chunk.startswith("## "):
            sections.setdefault("review", []).append(chunk)
            continue
        heading, *body = chunk.split("\n")
        key = heading.replace("## ", "").strip().lower()
        sections[key] = [line.strip() for line in body if line.strip()]
    return sections


def _collect_bullets(sections: list[dict[str, list[str]]], key: str) -> list[str]:
    lines: list[str] = []
    for section in sections:
        for line in section.get(key, []):
            if line.lower() == "none.":
                continue
            lines.append(line if line.startswith("- ") else f"- {line}")
    return _dedupe_lines(lines)


def _collect_summaries(sections: list[dict[str, list[str]]]) -> list[str]:
    summaries: list[str] = []
    for section in sections:
        summary_lines = section.get("summary", [])
        if summary_lines:
            summaries.append(" ".join(summary_lines))
    return _dedupe_lines(summaries)


def _merge_verdict(sections: list[dict[str, list[str]]], issues: list[str]) -> tuple[str, str]:
    verdict_tokens: list[str] = []
    verdict_reasons: list[str] = []

    for section in sections:
        verdict_lines = section.get("verdict", [])
        if not verdict_lines:
            continue
        joined = " ".join(verdict_lines)
        match = _VERDICT_RE.search(joined)
        if match:
            verdict_tokens.append(match.group(1).upper())
        cleaned_reason = _VERDICT_RE.sub("", joined).strip(" -:.")
        if cleaned_reason:
            verdict_reasons.append(cleaned_reason)

    if issues or "REQUEST_CHANGES" in verdict_tokens:
        return "REQUEST_CHANGES", (
            verdict_reasons[0]
            if verdict_reasons
            else "The combined review across all diff chunks found actionable issues."
        )
    if verdict_tokens and all(token == "APPROVE" for token in verdict_tokens):
        return "APPROVE", (
            verdict_reasons[0]
            if verdict_reasons
            else "No actionable issue was found across the reviewed diff chunks."
        )
    return "COMMENT", (
        verdict_reasons[0]
        if verdict_reasons
        else "The review completed across all diff chunks and needs human inspection."
    )


def merge_chunk_reviews(
    chunk_reviews: list[str],
    *,
    strategy: str,
    chunk_count: int,
    included_files: list[str],
) -> str:
    sections = [_parse_sections(review) for review in chunk_reviews if review.strip()]
    if not sections:
        return (
            "## Summary\nNo review text was generated for the diff chunks.\n\n"
            "## Issues Found\nNone.\n\n"
            "## Suggestions\nRetry the analysis.\n\n"
            "## Verdict\nCOMMENT\nChunk aggregation produced no usable review."
        )

    summaries = _collect_summaries(sections)
    issues = _collect_bullets(sections, "issues found")
    suggestions = _collect_bullets(sections, "suggestions")
    verdict, verdict_reason = _merge_verdict(sections, issues)

    strategy_label = strategy.replace("_", " ")
    summary_lines = [
        f"Reviewed {chunk_count} diff chunks covering {len(included_files)} file(s) with the {strategy_label} strategy."
    ]
    if summaries:
        summary_lines.append(summaries[0])

    return (
        "## Summary\n"
        + " ".join(summary_lines)
        + "\n\n## Issues Found\n"
        + ("\n".join(issues) if issues else "None.")
        + "\n\n## Suggestions\n"
        + ("\n".join(suggestions) if suggestions else "- Add more context or retry the analysis if the diff was incomplete.")
        + "\n\n## Verdict\n"
        + f"{verdict}\n{verdict_reason}"
    )
