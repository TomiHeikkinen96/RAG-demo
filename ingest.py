from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import uuid4

import numpy as np

try:
    import faiss
except ImportError as exc:
    raise ImportError(
        "FAISS is required for indexing. Install dependencies with "
        "`pip install -r requirements.txt`."
    ) from exc

from chunkers.pdf_chunker import PDFChunker
from processing.embedder import TextEmbedder
from processing.pdf_loader import load_pdf_pages
from utils.db import (
    clear_file_tracking_db,
    clear_metadata_db,
    count_chunks,
    delete_document_chunks,
    fetch_all_file_records,
    fetch_all_chunks_for_index,
    get_distinct_embedding_models,
    mark_file_deleted,
    initialize_file_tracking_db,
    initialize_metadata_db,
    insert_chunk_rows,
    record_file_seen,
    replace_index_entries,
    upsert_file_record,
    utc_now_iso,
    get_file_record,
)
from utils.hashing import sha256_file

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
STORAGE_DIR = PROJECT_ROOT / "storage"
INDEX_PATH = STORAGE_DIR / "index.faiss"
METADATA_DB_PATH = STORAGE_DIR / "metadata.sqlite"
FILE_TRACKING_DB_PATH = STORAGE_DIR / "files_ingested.sqlite"
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

CHUNKERS = {
    ".pdf": PDFChunker(),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local PDF-only RAG index.")
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Clear FAISS and SQLite storage before ingesting.",
    )
    return parser.parse_args()


def ensure_directories() -> None:
    if not DATA_DIR.exists():
        print(f"Error: data directory not found at {DATA_DIR}")
        sys.exit(1)

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def discover_pdf_files() -> list[Path]:
    return sorted(path for path in DATA_DIR.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")


def reset_storage() -> None:
    print("Force rebuild requested. Clearing existing storage.")
    clear_metadata_db(METADATA_DB_PATH)
    clear_file_tracking_db(FILE_TRACKING_DB_PATH)
    if INDEX_PATH.exists():
        INDEX_PATH.unlink()


def detect_files_to_process(pdf_paths: list[Path]) -> tuple[list[dict], list[dict]]:
    process_queue: list[dict] = []
    seen_files: list[dict] = []

    for pdf_path in pdf_paths:
        file_hash = sha256_file(pdf_path)
        seen_files.append({"path": pdf_path, "hash": file_hash})
        record = get_file_record(FILE_TRACKING_DB_PATH, str(pdf_path))

        if record is None:
            process_queue.append({"path": pdf_path, "hash": file_hash, "status": "NEW"})
            continue

        if not record["is_present"]:
            process_queue.append({"path": pdf_path, "hash": file_hash, "status": "RESTORED"})
            continue

        if record["file_hash"] != file_hash:
            process_queue.append({"path": pdf_path, "hash": file_hash, "status": "CHANGED"})

    return process_queue, seen_files


def detect_deleted_files(pdf_paths: list[Path]) -> list[Path]:
    current_paths = {str(path) for path in pdf_paths}
    deleted_paths: list[Path] = []

    for record in fetch_all_file_records(FILE_TRACKING_DB_PATH):
        file_path = record["file_path"]
        if record["is_present"] and file_path not in current_paths:
            deleted_paths.append(Path(file_path))

    return deleted_paths


def confirm_run(change_count: int, total_count: int, deleted_count: int) -> None:
    print(
        f"Found {change_count} ingestion changes "
        f"({deleted_count} deletions) across {total_count} current PDFs."
    )
    if change_count == 0:
        print("Nothing to do.")
        sys.exit(0)

    response = input("Proceed? (y/n) ").strip().lower()
    if response != "y":
        print("Ingestion cancelled.")
        sys.exit(0)


def ensure_model_consistency(force_rebuild: bool) -> None:
    existing_models = get_distinct_embedding_models(METADATA_DB_PATH)
    if not existing_models:
        return

    if existing_models == [EMBEDDING_MODEL_NAME]:
        return

    if force_rebuild:
        return

    print("Warning: metadata contains embeddings from a different model.")
    print(f"Existing models: {', '.join(existing_models)}")
    print(f"Requested model: {EMBEDDING_MODEL_NAME}")
    print("Run again with --force-rebuild to rebuild the index safely.")
    sys.exit(1)


def process_pdf(
    pdf_path: Path,
    file_hash: str,
    embedder: TextEmbedder,
) -> int:
    print(f"Processing: {pdf_path}")
    pages = load_pdf_pages(pdf_path)
    chunker = CHUNKERS[".pdf"]
    chunks = chunker.chunk_pages(pages)
    print(f"Created {len(chunks)} chunks.")

    if not chunks:
        document_id = str(pdf_path)
        delete_document_chunks(METADATA_DB_PATH, document_id)
        upsert_file_record(FILE_TRACKING_DB_PATH, str(pdf_path), file_hash)
        return 0

    document_id = str(pdf_path)
    delete_document_chunks(METADATA_DB_PATH, document_id)

    chunk_texts = [chunk["chunk_text"] for chunk in chunks]
    print(f"Embedding {len(chunk_texts)} chunks on {embedder.device}.")
    embeddings = embedder.embed_texts(chunk_texts)

    rows = []
    ingestion_timestamp = utc_now_iso()
    for chunk, _embedding in zip(chunks, embeddings):
        rows.append(
            {
                "chunk_id": str(uuid4()),
                "document_id": document_id,
                "source_path": str(pdf_path),
                "file_type": ".pdf",
                "title": chunk["title"],
                "chunk_text": chunk["chunk_text"],
                "chunk_index": chunk["chunk_index"],
                "page_number": chunk["page_number"],
                "paragraph_index": chunk["paragraph_index"],
                "paragraph_text": chunk["paragraph_text"],
                "section_heading": chunk["section_heading"],
                "embedding_model": EMBEDDING_MODEL_NAME,
                "ingestion_timestamp": ingestion_timestamp,
            }
        )

    insert_chunk_rows(METADATA_DB_PATH, rows)
    upsert_file_record(FILE_TRACKING_DB_PATH, str(pdf_path), file_hash)
    return len(rows)


def delete_missing_documents(deleted_paths: list[Path]) -> int:
    for deleted_path in deleted_paths:
        print(f"Deleting removed source: {deleted_path}")
        delete_document_chunks(METADATA_DB_PATH, str(deleted_path))
        mark_file_deleted(FILE_TRACKING_DB_PATH, str(deleted_path))
    return len(deleted_paths)


def record_current_files_seen(seen_files: list[dict]) -> None:
    for file_info in seen_files:
        record_file_seen(
            FILE_TRACKING_DB_PATH,
            str(file_info["path"]),
            file_info["hash"],
        )


def rebuild_faiss_index(embedder: TextEmbedder) -> None:
    all_chunks = fetch_all_chunks_for_index(METADATA_DB_PATH)
    if not all_chunks:
        print("No chunks stored. Skipping FAISS rebuild.")
        if INDEX_PATH.exists():
            INDEX_PATH.unlink()
        replace_index_entries(
            METADATA_DB_PATH,
            index_version=str(uuid4()),
            embedding_model=EMBEDDING_MODEL_NAME,
            rows=[],
        )
        return

    print(f"Rebuilding FAISS index from {len(all_chunks)} stored chunks.")
    texts = [row["chunk_text"] for row in all_chunks]
    embeddings = embedder.embed_texts(texts)
    faiss.normalize_L2(embeddings)

    index = faiss.IndexIDMap2(faiss.IndexFlatIP(embeddings.shape[1]))
    vector_ids = np.arange(len(all_chunks), dtype=np.int64)
    index.add_with_ids(embeddings, vector_ids)
    faiss.write_index(index, str(INDEX_PATH))

    index_version = str(uuid4())
    indexed_at = utc_now_iso()
    replace_index_entries(
        METADATA_DB_PATH,
        index_version=index_version,
        embedding_model=EMBEDDING_MODEL_NAME,
        rows=[
            {
                "vector_id": int(vector_id),
                "chunk_id": row["chunk_id"],
                "index_version": index_version,
                "embedding_model": EMBEDDING_MODEL_NAME,
                "indexed_at": indexed_at,
            }
            for vector_id, row in zip(vector_ids.tolist(), all_chunks)
        ],
    )
    print(f"Saved FAISS index to {INDEX_PATH}")


def main() -> None:
    args = parse_args()
    ensure_directories()
    initialize_metadata_db(METADATA_DB_PATH)
    initialize_file_tracking_db(FILE_TRACKING_DB_PATH)

    if args.force_rebuild:
        reset_storage()

    ensure_model_consistency(force_rebuild=args.force_rebuild)

    pdf_paths = discover_pdf_files()
    files_to_process, seen_files = detect_files_to_process(pdf_paths)
    deleted_paths = detect_deleted_files(pdf_paths)
    confirm_run(len(files_to_process) + len(deleted_paths), len(pdf_paths), len(deleted_paths))
    record_current_files_seen(seen_files)

    embedder = TextEmbedder(model_name=EMBEDDING_MODEL_NAME)

    processed_files = 0
    processed_chunks = 0
    deleted_files = delete_missing_documents(deleted_paths)

    for index, file_info in enumerate(files_to_process, start=1):
        pdf_path = file_info["path"]
        status = file_info["status"]
        print(f"[{index}/{len(files_to_process)}] {status}: {pdf_path}")
        processed_chunks += process_pdf(pdf_path, file_info["hash"], embedder)
        processed_files += 1

    rebuild_faiss_index(embedder)
    total_chunks = count_chunks(METADATA_DB_PATH)
    print("Ingestion complete.")
    print(f"Processed files: {processed_files}")
    print(f"Deleted files: {deleted_files}")
    print(f"New chunks this run: {processed_chunks}")
    print(f"Total stored chunks: {total_chunks}")


if __name__ == "__main__":
    main()
