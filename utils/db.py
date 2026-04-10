from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def sqlite_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_metadata_db(db_path: Path) -> None:
    with sqlite_connection(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                file_type TEXT NOT NULL,
                title TEXT,
                chunk_text TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                page_number INTEGER,
                section_heading TEXT,
                embedding_model TEXT NOT NULL,
                ingestion_timestamp TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chunks_document_id
            ON chunks(document_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chunks_source_path
            ON chunks(source_path)
            """
        )


def initialize_file_tracking_db(db_path: Path) -> None:
    with sqlite_connection(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                file_path TEXT PRIMARY KEY,
                file_hash TEXT NOT NULL,
                last_processed TEXT NOT NULL
            )
            """
        )


def get_file_record(db_path: Path, file_path: str) -> Optional[sqlite3.Row]:
    with sqlite_connection(db_path) as connection:
        return connection.execute(
            "SELECT file_path, file_hash, last_processed FROM files WHERE file_path = ?",
            (file_path,),
        ).fetchone()


def upsert_file_record(db_path: Path, file_path: str, file_hash: str) -> None:
    with sqlite_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO files(file_path, file_hash, last_processed)
            VALUES (?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                file_hash = excluded.file_hash,
                last_processed = excluded.last_processed
            """,
            (file_path, file_hash, utc_now_iso()),
        )


def clear_file_tracking_db(db_path: Path) -> None:
    with sqlite_connection(db_path) as connection:
        connection.execute("DELETE FROM files")


def insert_chunk_rows(db_path: Path, rows: list[dict]) -> None:
    if not rows:
        return

    with sqlite_connection(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO chunks(
                chunk_id,
                document_id,
                source_path,
                file_type,
                title,
                chunk_text,
                chunk_index,
                page_number,
                section_heading,
                embedding_model,
                ingestion_timestamp
            )
            VALUES (
                :chunk_id,
                :document_id,
                :source_path,
                :file_type,
                :title,
                :chunk_text,
                :chunk_index,
                :page_number,
                :section_heading,
                :embedding_model,
                :ingestion_timestamp
            )
            """,
            rows,
        )


def delete_document_chunks(db_path: Path, document_id: str) -> None:
    with sqlite_connection(db_path) as connection:
        connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))


def clear_metadata_db(db_path: Path) -> None:
    with sqlite_connection(db_path) as connection:
        connection.execute("DELETE FROM chunks")


def count_chunks(db_path: Path) -> int:
    with sqlite_connection(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) AS count FROM chunks").fetchone()
        return int(row["count"])


def fetch_all_chunks_for_index(db_path: Path) -> list[sqlite3.Row]:
    with sqlite_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT chunk_id, chunk_text
            FROM chunks
            ORDER BY source_path, chunk_index
            """
        ).fetchall()


def fetch_all_chunk_ids_for_index(db_path: Path) -> list[str]:
    with sqlite_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT chunk_id
            FROM chunks
            ORDER BY source_path, chunk_index
            """
        ).fetchall()
    return [row["chunk_id"] for row in rows]


def fetch_chunks_by_ids(db_path: Path, chunk_ids: list[str]) -> list[sqlite3.Row]:
    if not chunk_ids:
        return []

    placeholders = ",".join("?" for _ in chunk_ids)
    order_by = "CASE chunk_id " + " ".join(
        f"WHEN ? THEN {index}" for index, _ in enumerate(chunk_ids)
    ) + " END"
    parameters = chunk_ids + chunk_ids

    with sqlite_connection(db_path) as connection:
        return connection.execute(
            f"""
            SELECT
                chunk_id,
                source_path,
                page_number,
                chunk_text,
                title,
                section_heading
            FROM chunks
            WHERE chunk_id IN ({placeholders})
            ORDER BY {order_by}
            """,
            parameters,
        ).fetchall()


def get_distinct_embedding_models(db_path: Path) -> list[str]:
    with sqlite_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT DISTINCT embedding_model FROM chunks ORDER BY embedding_model"
        ).fetchall()
    return [row["embedding_model"] for row in rows if row["embedding_model"]]
