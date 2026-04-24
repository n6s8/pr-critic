"""
TF-IDF retriever that works fully offline.

The retriever exposes both prompt-ready context text and structured retrieval
hits so the backend can make grounding visible to the frontend.
"""
from __future__ import annotations

import json
import math
import re
import string
from collections import Counter
from pathlib import Path
from typing import Optional

_INDEX_PATH = Path("data/tfidf_index.json")
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "not", "if", "this", "that", "it",
    "its", "use", "used", "using", "always", "never", "also", "each",
}


def _tokenize(text: str) -> list[str]:
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    return [token for token in text.split() if token not in _STOPWORDS and len(token) > 2]


def _chunk_text(text: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        if end < len(text):
            newline = text.rfind("\n", start + CHUNK_SIZE // 2, end)
            if newline != -1:
                end = newline
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - CHUNK_OVERLAP
    return chunks


def _parse_file(path: Path) -> list[dict]:
    content = path.read_text(encoding="utf-8")
    category = "general"
    for line in content.strip().split("\n")[:5]:
        if line.startswith("Category:"):
            category = line.split(":", 1)[1].strip()

    docs: list[dict] = []
    for section_index, section in enumerate(re.split(r"\n---\n", content)):
        section = section.strip()
        if not section:
            continue
        match = re.match(r"SECTION:\s*(.+)\n", section)
        section_name = match.group(1).strip() if match else "general"
        for chunk_index, chunk in enumerate(_chunk_text(section)):
            docs.append({
                "id": f"{path.stem}_{section_index:03d}_{chunk_index:03d}",
                "text": chunk,
                "source": path.stem,
                "category": category,
                "section": section_name,
            })
    return docs


def build_corpus(corpus_dir: str = "data/corpus", force_rebuild: bool = False) -> int:
    _INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not force_rebuild and _INDEX_PATH.exists():
        return len(json.loads(_INDEX_PATH.read_text(encoding="utf-8"))["docs"])

    all_docs: list[dict] = []
    for corpus_file in sorted(Path(corpus_dir).glob("*.txt")):
        all_docs.extend(_parse_file(corpus_file))

    if not all_docs:
        raise ValueError(f"No .txt files found in {corpus_dir}")

    term_frequencies: dict[str, Counter] = {
        doc["id"]: Counter(_tokenize(doc["text"])) for doc in all_docs
    }
    document_frequency: Counter = Counter()
    for counts in term_frequencies.values():
        for term in counts:
            document_frequency[term] += 1

    total_docs = len(all_docs)
    index: dict[str, dict[str, float]] = {}
    for doc in all_docs:
        total_terms = sum(term_frequencies[doc["id"]].values()) or 1
        for term, count in term_frequencies[doc["id"]].items():
            tfidf = (count / total_terms) * (math.log((total_docs + 1) / (document_frequency[term] + 1)) + 1)
            index.setdefault(term, {})[doc["id"]] = tfidf

    _INDEX_PATH.write_text(
        json.dumps({"docs": all_docs, "index": index}, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(all_docs)


def _load() -> tuple[list[dict], dict]:
    if not _INDEX_PATH.exists():
        return [], {}
    data = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    return data["docs"], data["index"]


def retrieve_hits(
    query: str,
    top_k: int = 5,
    category_filter: Optional[str] = None,
) -> list[dict]:
    docs, index = _load()
    if not docs:
        return []

    terms = _tokenize(query)
    if not terms:
        return []

    scores: Counter = Counter()
    for term in terms:
        if term in index:
            for doc_id, score in index[term].items():
                scores[doc_id] += score

    doc_map = {doc["id"]: doc for doc in docs}
    if category_filter:
        scores = Counter({
            doc_id: score
            for doc_id, score in scores.items()
            if doc_map.get(doc_id, {}).get("category") == category_filter
        })

    hits: list[dict] = []
    for doc_id, _ in scores.most_common(top_k):
        doc = doc_map[doc_id]
        hits.append({
            "source": doc["source"],
            "section": doc["section"],
            "text": doc["text"],
            "relevance": round(scores[doc_id], 3),
        })

    return hits


def retrieve_context(
    query: str,
    top_k: int = 5,
    category_filter: Optional[str] = None,
) -> tuple[str, list[str], list[dict]]:
    hits = retrieve_hits(query, top_k=top_k, category_filter=category_filter)
    if not hits:
        return "", [], []

    parts = [
        f"[{hit['source'].upper()} - {hit['section']}] (relevance: {hit['relevance']})\n{hit['text']}"
        for hit in hits
    ]
    sources = sorted({hit["source"] for hit in hits})
    return "\n\n---\n\n".join(parts), sources, hits


def get_collection_stats() -> dict:
    docs, _ = _load()
    return {
        "total_chunks": len(docs),
        "retriever": "tfidf_local",
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }
