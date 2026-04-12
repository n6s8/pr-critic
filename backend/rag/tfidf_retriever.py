"""
TF-IDF retriever — fully offline, no model downloads required.

Works identically in CI, local dev, and sandboxed environments.
For production with internet access, swap to vector_store.py
(ChromaDB + ONNX embeddings) — the retrieve_context() signature
is identical.
"""
import json
import math
import re
import string
from collections import Counter
from pathlib import Path
from typing import Optional

from backend.config import settings

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
    return [t for t in text.split() if t not in _STOPWORDS and len(t) > 2]


def _chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        end = start + CHUNK_SIZE
        if end < len(text):
            nl = text.rfind("\n", start + CHUNK_SIZE // 2, end)
            if nl != -1:
                end = nl
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

    docs = []
    for i, section in enumerate(re.split(r"\n---\n", content)):
        section = section.strip()
        if not section:
            continue
        m = re.match(r"SECTION:\s*(.+)\n", section)
        section_name = m.group(1).strip() if m else "general"
        for j, chunk in enumerate(_chunk_text(section)):
            docs.append({
                "id": f"{path.stem}_{i:03d}_{j:03d}",
                "text": chunk,
                "source": path.stem,
                "category": category,
                "section": section_name,
            })
    return docs


def build_corpus(corpus_dir: str = "data/corpus",
                 force_rebuild: bool = False) -> int:
    _INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not force_rebuild and _INDEX_PATH.exists():
        return len(json.loads(_INDEX_PATH.read_text())["docs"])

    all_docs: list[dict] = []
    for f in sorted(Path(corpus_dir).glob("*.txt")):
        all_docs.extend(_parse_file(f))

    if not all_docs:
        raise ValueError(f"No .txt files found in {corpus_dir}")

    # Build TF-IDF index
    tf: dict[str, Counter] = {d["id"]: Counter(_tokenize(d["text"])) for d in all_docs}
    df: Counter = Counter()
    for counts in tf.values():
        for term in counts:
            df[term] += 1
    N = len(all_docs)
    index: dict[str, dict[str, float]] = {}
    for doc in all_docs:
        total = sum(tf[doc["id"]].values()) or 1
        for term, count in tf[doc["id"]].items():
            tfidf = (count / total) * (math.log((N + 1) / (df[term] + 1)) + 1)
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


def retrieve_context(query: str, top_k: int = 5,
                     category_filter: Optional[str] = None) -> tuple[str, list[str]]:
    docs, index = _load()
    if not docs:
        return "", []

    terms = _tokenize(query)
    if not terms:
        return "", []

    scores: Counter = Counter()
    for term in terms:
        if term in index:
            for doc_id, score in index[term].items():
                scores[doc_id] += score

    doc_map = {d["id"]: d for d in docs}
    if category_filter:
        scores = Counter({
            k: v for k, v in scores.items()
            if doc_map.get(k, {}).get("category") == category_filter
        })

    parts, seen = [], set()
    for doc_id, _ in scores.most_common(top_k):
        doc = doc_map[doc_id]
        rel = round(scores[doc_id], 3)
        label = f"[{doc['source'].upper()} — {doc['section']}] (relevance: {rel})"
        parts.append(f"{label}\n{doc['text']}")
        seen.add(doc["source"])

    return "\n\n---\n\n".join(parts), sorted(seen)


def get_collection_stats() -> dict:
    docs, _ = _load()
    return {
        "total_chunks": len(docs),
        "retriever": "tfidf_local",
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }