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
                paragraph_index INTEGER,
                paragraph_text TEXT,
                section_heading TEXT,
                embedding_model TEXT NOT NULL,
                ingestion_timestamp TEXT NOT NULL
            )
            """
        )
        _ensure_column_exists(connection, "chunks", "paragraph_index", "INTEGER")
        _ensure_column_exists(connection, "chunks", "paragraph_text", "TEXT")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS indexes (
                index_version TEXT PRIMARY KEY,
                embedding_model TEXT NOT NULL,
                built_at TEXT NOT NULL,
                chunk_count INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS indexed_chunks (
                vector_id INTEGER PRIMARY KEY,
                chunk_id TEXT NOT NULL UNIQUE,
                index_version TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                indexed_at TEXT NOT NULL,
                FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
                FOREIGN KEY (index_version) REFERENCES indexes(index_version)
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
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_indexed_chunks_chunk_id
            ON indexed_chunks(chunk_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_indexed_chunks_index_version
            ON indexed_chunks(index_version)
            """
        )


def _ensure_column_exists(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing_columns:
        return

    connection.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
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
        _ensure_column_exists(
            connection,
            "files",
            "last_seen",
            "TEXT",
        )
        _ensure_column_exists(
            connection,
            "files",
            "is_present",
            "INTEGER NOT NULL DEFAULT 1",
        )
        _ensure_column_exists(
            connection,
            "files",
            "deleted_at",
            "TEXT",
        )

        connection.execute(
            """
            UPDATE files
            SET last_seen = COALESCE(last_seen, last_processed),
                is_present = COALESCE(is_present, 1)
            """
        )


def get_file_record(db_path: Path, file_path: str) -> Optional[sqlite3.Row]:
    with sqlite_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT
                file_path,
                file_hash,
                last_processed,
                last_seen,
                is_present,
                deleted_at
            FROM files
            WHERE file_path = ?
            """,
            (file_path,),
        ).fetchone()


def fetch_all_file_records(db_path: Path) -> list[sqlite3.Row]:
    with sqlite_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT
                file_path,
                file_hash,
                last_processed,
                last_seen,
                is_present,
                deleted_at
            FROM files
            ORDER BY file_path
            """
        ).fetchall()


def record_file_seen(db_path: Path, file_path: str, file_hash: str) -> None:
    timestamp = utc_now_iso()
    with sqlite_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO files(
                file_path,
                file_hash,
                last_processed,
                last_seen,
                is_present,
                deleted_at
            )
            VALUES (?, ?, ?, ?, 1, NULL)
            ON CONFLICT(file_path) DO UPDATE SET
                file_hash = excluded.file_hash,
                last_seen = excluded.last_seen,
                is_present = 1,
                deleted_at = NULL
            """,
            (file_path, file_hash, timestamp, timestamp),
        )


def upsert_file_record(db_path: Path, file_path: str, file_hash: str) -> None:
    timestamp = utc_now_iso()
    with sqlite_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO files(
                file_path,
                file_hash,
                last_processed,
                last_seen,
                is_present,
                deleted_at
            )
            VALUES (?, ?, ?, ?, 1, NULL)
            ON CONFLICT(file_path) DO UPDATE SET
                file_hash = excluded.file_hash,
                last_processed = excluded.last_processed,
                last_seen = excluded.last_seen,
                is_present = 1,
                deleted_at = NULL
            """,
            (file_path, file_hash, timestamp, timestamp),
        )


def mark_file_deleted(db_path: Path, file_path: str) -> None:
    with sqlite_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE files
            SET is_present = 0,
                deleted_at = ?,
                last_seen = ?
            WHERE file_path = ?
            """,
            (utc_now_iso(), utc_now_iso(), file_path),
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
                paragraph_index,
                paragraph_text,
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
                :paragraph_index,
                :paragraph_text,
                :section_heading,
                :embedding_model,
                :ingestion_timestamp
            )
            """,
            rows,
        )


def delete_document_chunks(db_path: Path, document_id: str) -> None:
    with sqlite_connection(db_path) as connection:
        connection.execute(
            """
            DELETE FROM indexed_chunks
            WHERE chunk_id IN (
                SELECT chunk_id
                FROM chunks
                WHERE document_id = ?
            )
            """,
            (document_id,),
        )
        connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))


def clear_metadata_db(db_path: Path) -> None:
    with sqlite_connection(db_path) as connection:
        connection.execute("DELETE FROM indexed_chunks")
        connection.execute("DELETE FROM indexes")
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
            ORDER BY source_path, chunk_index, chunk_id
            """
        ).fetchall()


def replace_index_entries(
    db_path: Path,
    index_version: str,
    embedding_model: str,
    rows: list[dict],
) -> None:
    built_at = utc_now_iso()
    with sqlite_connection(db_path) as connection:
        connection.execute("DELETE FROM indexed_chunks")
        connection.execute(
            """
            INSERT INTO indexes(index_version, embedding_model, built_at, chunk_count)
            VALUES (?, ?, ?, ?)
            """,
            (index_version, embedding_model, built_at, len(rows)),
        )
        if rows:
            connection.executemany(
                """
                INSERT INTO indexed_chunks(
                    vector_id,
                    chunk_id,
                    index_version,
                    embedding_model,
                    indexed_at
                )
                VALUES (
                    :vector_id,
                    :chunk_id,
                    :index_version,
                    :embedding_model,
                    :indexed_at
                )
                """,
                rows,
            )


def fetch_chunks_by_vector_ids(db_path: Path, vector_ids: list[int]) -> list[sqlite3.Row]:
    if not vector_ids:
        return []

    placeholders = ",".join("?" for _ in vector_ids)
    order_by = "CASE indexed_chunks.vector_id " + " ".join(
        f"WHEN ? THEN {index}" for index, _ in enumerate(vector_ids)
    ) + " END"
    parameters = vector_ids + vector_ids

    with sqlite_connection(db_path) as connection:
        return connection.execute(
            f"""
            SELECT
                indexed_chunks.vector_id,
                indexed_chunks.index_version,
                chunks.chunk_id,
                chunks.source_path,
                chunks.page_number,
                chunks.paragraph_index,
                chunks.chunk_text,
                chunks.paragraph_text,
                chunks.title,
                chunks.section_heading
            FROM indexed_chunks
            JOIN chunks ON chunks.chunk_id = indexed_chunks.chunk_id
            WHERE indexed_chunks.vector_id IN ({placeholders})
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
