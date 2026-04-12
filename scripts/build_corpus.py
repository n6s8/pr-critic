#!/usr/bin/env python
"""
Build the TF-IDF retrieval index from corpus text files.

Usage:
  python scripts/build_corpus.py             # build (skip if exists)
  python scripts/build_corpus.py --rebuild   # force rebuild
  python scripts/build_corpus.py --stats     # show stats
  python scripts/build_corpus.py --test-query "sql injection"
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("GROQ_API_KEY", "not_needed_for_corpus_build")

from backend.rag.tfidf_retriever import build_corpus, get_collection_stats, retrieve_context


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--stats", action="store_true")
    p.add_argument("--test-query", type=str)
    args = p.parse_args()

    if args.stats:
        for k, v in get_collection_stats().items():
            print(f"  {k}: {v}")
        return

    print("Building corpus...")
    count = build_corpus(force_rebuild=args.rebuild)
    print(f"Done: {count} chunks indexed")
    for k, v in get_collection_stats().items():
        print(f"  {k}: {v}")

    if args.test_query:
        ctx, sources = retrieve_context(args.test_query, top_k=3)
        print(f"\nQuery: '{args.test_query}'")
        print(f"Sources: {sources}")
        print(f"\n{ctx[:600]}")


if __name__ == "__main__":
    main()