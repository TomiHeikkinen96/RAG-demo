from __future__ import annotations

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


def ensure_search_inputs() -> None:
    if not INDEX_PATH.exists():
        print(f"Error: FAISS index not found at {INDEX_PATH}")
        sys.exit(1)

    if not METADATA_DB_PATH.exists():
        print(f"Error: metadata database not found at {METADATA_DB_PATH}")
        sys.exit(1)


def preview_text(text: str, limit: int = 300) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def main() -> None:
    ensure_search_inputs()
    initialize_metadata_db(METADATA_DB_PATH)

    index = faiss.read_index(str(INDEX_PATH))
    embedder = TextEmbedder(model_name=EMBEDDING_MODEL_NAME)
    ordered_chunk_ids = fetch_all_chunk_ids_for_index(METADATA_DB_PATH)

    query = input("Query: ").strip()
    if not query:
        print("Empty query. Exiting.")
        return

    query_embedding = embedder.embed_texts([query])
    faiss.normalize_L2(query_embedding)

    scores, indices = index.search(query_embedding.astype(np.float32), TOP_K)
    hit_indices = [int(idx) for idx in indices[0] if idx >= 0]
    if not hit_indices:
        print("No matches found.")
        return

    chunk_ids = [ordered_chunk_ids[hit_index] for hit_index in hit_indices if hit_index < len(ordered_chunk_ids)]
    rows = fetch_chunks_by_ids(METADATA_DB_PATH, chunk_ids)
    row_lookup = {row["chunk_id"]: row for row in rows}

    print()
    for score, hit_index in zip(scores[0], indices[0]):
        if hit_index < 0:
            continue

        if hit_index >= len(ordered_chunk_ids):
            continue

        row = row_lookup.get(ordered_chunk_ids[hit_index])
        if row is None:
            continue

        print(f"Score: {float(score):.2f}")
        print(f"File: {row['source_path']}")
        print(f"Page: {row['page_number']}")
        print("Text:")
        print(preview_text(row["chunk_text"]))
        print()


if __name__ == "__main__":
    main()
