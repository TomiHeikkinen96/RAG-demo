from __future__ import annotations

import argparse
from pathlib import Path

import faiss

from processing.embedder import TextEmbedder
from search_index import (
    EMBEDDING_MODEL_NAME,
    INDEX_PATH,
    METADATA_DB_PATH,
    ensure_search_inputs,
    preview_text,
    search_query,
)
from utils.db import fetch_all_chunk_ids_for_index, initialize_metadata_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a standardized batch of search queries against the local index."
    )
    parser.add_argument(
        "queries",
        nargs="*",
        help="Query strings to evaluate. If omitted, queries are loaded from --file.",
    )
    parser.add_argument(
        "--file",
        default="benchmark_queries.txt",
        help="Path to a text file containing one query per line.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of results to print for each query.",
    )
    return parser.parse_args()


def load_queries(args: argparse.Namespace) -> list[str]:
    if args.queries:
        return args.queries

    file_path = Path(args.file)
    if not file_path.is_absolute():
        file_path = Path(__file__).resolve().parent / file_path

    if not file_path.exists():
        raise SystemExit(
            f"Benchmark query file not found: {file_path}\n"
            "Provide queries as arguments or create the file."
        )

    with open(file_path, "r", encoding="utf-8") as handle:
        return [
            line.strip()
            for line in handle
            if line.strip() and not line.lstrip().startswith("#")
        ]


def main() -> None:
    args = parse_args()
    queries = load_queries(args)
    if not queries:
        raise SystemExit("No benchmark queries provided.")

    ensure_search_inputs()
    initialize_metadata_db(METADATA_DB_PATH)

    index = faiss.read_index(str(INDEX_PATH))
    embedder = TextEmbedder(model_name=EMBEDDING_MODEL_NAME)
    ordered_chunk_ids = fetch_all_chunk_ids_for_index(METADATA_DB_PATH)

    for query_index, query in enumerate(queries):
        if query_index > 0:
            print("=" * 80)

        print(f"Query: {query}")
        print()
        results = search_query(query, index, embedder, ordered_chunk_ids)
        if not results:
            print("No matches found.")
            print()
            continue

        for rank, result in enumerate(results[: args.top_k], start=1):
            row = result["row"]
            print(f"Rank: {rank}")
            print(f"Final Score: {result['rerank_score']:.2f}")
            print(f"Semantic Score: {result['semantic_score']:.2f}")
            print(f"Lexical Score: {result['lexical_score']:.2f}")
            print(f"Penalty: {result['penalty']:.2f}")
            print(f"File: {row['source_path']}")
            print(f"Page: {row['page_number']}")
            print("Chunk:")
            print(preview_text(row["chunk_text"], limit=220))
            print()


if __name__ == "__main__":
    main()
