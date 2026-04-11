from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
try:
    import faiss
except ImportError as exc:
    raise ImportError(
        "FAISS is required for search. Install dependencies with "
        "`pip install -r requirements.txt`."
    ) from exc

from processing.embedder import TextEmbedder
from utils.db import fetch_all_chunk_ids_for_index, fetch_chunks_by_ids, initialize_metadata_db

PROJECT_ROOT = Path(__file__).resolve().parent
STORAGE_DIR = PROJECT_ROOT / "storage"
INDEX_PATH = STORAGE_DIR / "index.faiss"
METADATA_DB_PATH = STORAGE_DIR / "metadata.sqlite"
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5
CANDIDATE_POOL = 50
# Heuristic weight for exact-term overlap in the reranker.
# Kept intentionally modest so lexical matches help reorder candidates
# without overpowering the embedding-based semantic retrieval signal.
LEXICAL_WEIGHT = 0.25
LOW_VALUE_SECTION_PATTERNS = (
    re.compile(r"\brevision history\b", re.IGNORECASE),
    re.compile(r"\bcontents\b", re.IGNORECASE),
    re.compile(r"\blist of tables\b", re.IGNORECASE),
    re.compile(r"\blist of figures\b", re.IGNORECASE),
)


def ensure_search_inputs() -> None:
    if not INDEX_PATH.exists():
        print(f"Error: FAISS index not found at {INDEX_PATH}")
        sys.exit(1)

    if not METADATA_DB_PATH.exists():
        print(f"Error: metadata database not found at {METADATA_DB_PATH}")
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search the local FAISS index using one or more queries."
    )
    parser.add_argument(
        "queries",
        nargs="*",
        help="Optional query strings. If omitted, the script prompts interactively.",
    )
    return parser.parse_args()


def preview_text(text: str, limit: int = 300) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def lexical_overlap_score(query: str, row: dict) -> float:
    query_tokens = {token for token in tokenize(query) if len(token) >= 3}
    if not query_tokens:
        return 0.0

    chunk_tokens = tokenize(row["chunk_text"])
    paragraph_tokens = tokenize(row["paragraph_text"] or "")
    matched_tokens = query_tokens & (chunk_tokens | paragraph_tokens)
    return len(matched_tokens) / len(query_tokens)


def low_value_section_penalty(row: dict) -> float:
    display_text = row["paragraph_text"] or row["chunk_text"]
    if any(pattern.search(display_text) for pattern in LOW_VALUE_SECTION_PATTERNS):
        return 0.12
    return 0.0


def rerank_components(query: str, semantic_score: float, row: dict) -> dict[str, float]:
    lexical_score = lexical_overlap_score(query, row)
    penalty = low_value_section_penalty(row)
    reranked_score = semantic_score + (LEXICAL_WEIGHT * lexical_score) - penalty
    return {
        "semantic_score": semantic_score,
        "lexical_score": lexical_score,
        "penalty": penalty,
        "rerank_score": reranked_score,
    }


def search_query(
    query: str,
    index: faiss.Index,
    embedder: TextEmbedder,
    ordered_chunk_ids: list[str],
) -> list[dict]:
    query_embedding = embedder.embed_texts([query])
    faiss.normalize_L2(query_embedding)

    scores, indices = index.search(query_embedding.astype(np.float32), CANDIDATE_POOL)
    hit_indices = [int(idx) for idx in indices[0] if idx >= 0]
    if not hit_indices:
        return []

    chunk_ids = [
        ordered_chunk_ids[hit_index]
        for hit_index in hit_indices
        if hit_index < len(ordered_chunk_ids)
    ]
    rows = fetch_chunks_by_ids(METADATA_DB_PATH, chunk_ids)
    row_lookup = {row["chunk_id"]: row for row in rows}
    ranked_results: list[dict] = []
    seen_paragraphs: set[tuple[str, int | None, int | None]] = set()

    for semantic_score, hit_index in zip(scores[0], indices[0]):
        if hit_index < 0 or hit_index >= len(ordered_chunk_ids):
            continue

        row = row_lookup.get(ordered_chunk_ids[hit_index])
        if row is None:
            continue

        paragraph_key = (
            row["source_path"],
            row["page_number"],
            row["paragraph_index"],
        )
        if paragraph_key in seen_paragraphs:
            continue

        seen_paragraphs.add(paragraph_key)
        scores = rerank_components(query, float(semantic_score), row)
        ranked_results.append(
            {
                "row": row,
                **scores,
            }
        )

    ranked_results.sort(key=lambda item: item["rerank_score"], reverse=True)
    return ranked_results[:TOP_K]


def print_results(query: str, ranked_results: list[dict]) -> None:
    print(f"Query: {query}")
    if not ranked_results:
        print("No matches found.")
        print()
        return

    print()
    for result in ranked_results:
        row = result["row"]
        print(f"Final Score: {result['rerank_score']:.2f}")
        print("---")
        print(f"Semantic Score: {result['semantic_score']:.2f}")
        print(f"Lexical Score: {result['lexical_score']:.2f}")
        print(f"Penalty: {result['penalty']:.2f}")
        print(f"Rerank Score: {result['rerank_score']:.2f}")
        print("---")
        print(f"File: {row['source_path']}")
        print(f"Page: {row['page_number']}")
        chunk_length = len(row["chunk_text"])
        paragraph_index = row["paragraph_index"]
        print(f"Chunk (length: {chunk_length}, paragraph index: {paragraph_index}):")
        print(preview_text(row["chunk_text"]))
        print("-----")
        display_text = row["paragraph_text"] or row["chunk_text"]
        print(f"Retrieved Text (length: {len(display_text)}):")
        print(preview_text(display_text))
        print()


def main() -> None:
    args = parse_args()
    ensure_search_inputs()
    initialize_metadata_db(METADATA_DB_PATH)

    index = faiss.read_index(str(INDEX_PATH))
    embedder = TextEmbedder(model_name=EMBEDDING_MODEL_NAME)
    ordered_chunk_ids = fetch_all_chunk_ids_for_index(METADATA_DB_PATH)

    queries = args.queries
    if not queries:
        query = input("Query: ").strip()
        if not query:
            print("Empty query. Exiting.")
            return
        queries = [query]

    for index_number, query in enumerate(queries):
        if index_number > 0:
            print("-" * 80)
        ranked_results = search_query(query, index, embedder, ordered_chunk_ids)
        print_results(query, ranked_results)


if __name__ == "__main__":
    main()
