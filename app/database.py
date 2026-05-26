import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "technologies.db"))

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS technologies (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    technology_type TEXT NOT NULL,
    modality_label  TEXT,
    modality_iri    TEXT,
    specimen_types  TEXT NOT NULL,
    access_type     TEXT NOT NULL,
    facility_name   TEXT NOT NULL,
    facility_country TEXT NOT NULL,
    contact_email   TEXT NOT NULL,
    modality_term   TEXT,
    ontology_terms  TEXT NOT NULL DEFAULT '[]',
    llm_context     TEXT NOT NULL,
    submitted_at    TEXT NOT NULL,
    ttl_path        TEXT
);
"""


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db_connection() as conn:
        conn.execute(CREATE_TABLE_SQL)


def insert_technology(record: dict) -> str:
    """
    Insert a technology record. Uses record['id'] if present, otherwise generates a UUID.
    Returns the record id used.
    """
    record_id = record.get("id") or str(uuid.uuid4())
    submitted_at = record.get("submitted_at") or datetime.now(timezone.utc).isoformat()

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO technologies (
                id, name, description, technology_type,
                modality_label, modality_iri, specimen_types, access_type,
                facility_name, facility_country, contact_email,
                modality_term, ontology_terms, llm_context, submitted_at, ttl_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                record["name"],
                record["description"],
                record["technology_type"],
                record.get("modality_label"),
                record.get("modality_iri"),
                json.dumps(record.get("specimen_types", [])),
                record["access_type"],
                record["facility_name"],
                record["facility_country"],
                str(record["contact_email"]),
                json.dumps(record.get("modality_term")) if record.get("modality_term") else None,
                json.dumps(record.get("ontology_terms", [])),
                record["llm_context"],
                submitted_at,
                record.get("ttl_path"),
            ),
        )
    return record_id


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["specimen_types"] = json.loads(d["specimen_types"]) if d["specimen_types"] else []
    d["ontology_terms"] = json.loads(d["ontology_terms"]) if d["ontology_terms"] else []
    if d.get("modality_term"):
        d["modality_term"] = json.loads(d["modality_term"])
    else:
        d["modality_term"] = None
    return d


def get_technology(record_id: str) -> dict | None:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM technologies WHERE id = ?", (record_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_all_technologies(limit: int = 20, offset: int = 0) -> list[dict]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM technologies ORDER BY submitted_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_technologies() -> int:
    with get_db_connection() as conn:
        result = conn.execute("SELECT COUNT(*) FROM technologies").fetchone()
    return result[0]


def search_technologies(q: str, limit: int = 20) -> list[dict]:
    """
    LIKE search across name, description, and llm_context.
    llm_context is particularly valuable: a single pass captures technology type,
    facility, specimen type, and modality all in prose form.
    """
    pattern = f"%{q}%"
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM technologies
            WHERE name LIKE ?
               OR description LIKE ?
               OR llm_context LIKE ?
            ORDER BY submitted_at DESC
            LIMIT ?
            """,
            (pattern, pattern, pattern, limit),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_ttl_path(record_id: str, ttl_path: str) -> None:
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE technologies SET ttl_path = ? WHERE id = ?",
            (ttl_path, record_id),
        )
