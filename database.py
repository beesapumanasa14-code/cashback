"""SQLite persistence for offers, calculations, and local investigations."""

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CASHBACK_DB_PATH", PROJECT_DIR / "cashback.db"))
EVIDENCE_DIR = Path(os.environ.get("CASHBACK_EVIDENCE_DIR", PROJECT_DIR / "uploads" / "evidence"))


def connect(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """Open a database connection with foreign-key enforcement enabled."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db_path: str | Path = DB_PATH) -> None:
    """Create required tables and indexes if they do not already exist."""
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS offers (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                offer_text TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Unknown'
                    CHECK (status IN ('Unknown', 'Active', 'Expired')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_id TEXT REFERENCES offers(id) ON DELETE SET NULL,
                transaction_amount TEXT NOT NULL,
                estimated_cashback TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS investigations (
                id TEXT PRIMARY KEY,
                offer_description TEXT NOT NULL,
                merchant TEXT NOT NULL,
                transaction_date TEXT NOT NULL,
                transaction_amount TEXT NOT NULL,
                expected_cashback TEXT NOT NULL,
                actual_cashback TEXT,
                transaction_reference TEXT,
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Waiting for cashback'
                    CHECK (status IN ('Waiting for cashback', 'Investigation started', 'Resolved', 'Rejected by provider')),
                evidence_path TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_offers_updated ON offers(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_investigations_updated ON investigations(updated_at DESC);
            """
        )


def list_offers(db_path: str | Path = DB_PATH) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute("SELECT * FROM offers ORDER BY updated_at DESC").fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["analysis"] = json.loads(item.pop("analysis_json"))
        results.append(item)
    return results


def get_offer(offer_id: str, db_path: str | Path = DB_PATH) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        row = connection.execute("SELECT * FROM offers WHERE id = ?", (offer_id,)).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["analysis"] = json.loads(item.pop("analysis_json"))
    return item


def save_offer(
    title: str,
    offer_text: str,
    analysis: dict[str, Any],
    status: str = "Unknown",
    offer_id: str | None = None,
    db_path: str | Path = DB_PATH,
) -> str:
    if status not in ("Unknown", "Active", "Expired"):
        raise ValueError("Offer status must be Unknown, Active, or Expired.")
    if not title.strip() or not offer_text.strip():
        raise ValueError("Offer title and text are required.")
    identifier = offer_id or str(uuid.uuid4())
    payload = json.dumps(analysis, ensure_ascii=False)
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO offers (id, title, offer_text, analysis_json, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                offer_text = excluded.offer_text,
                analysis_json = excluded.analysis_json,
                status = excluded.status,
                updated_at = CURRENT_TIMESTAMP
            """,
            (identifier, title.strip(), offer_text.strip(), payload, status),
        )
    return identifier


def delete_offer(offer_id: str, db_path: str | Path = DB_PATH) -> None:
    with connect(db_path) as connection:
        connection.execute("DELETE FROM offers WHERE id = ?", (offer_id,))


def save_calculation(
    transaction_amount: Any,
    estimated_cashback: Any,
    offer_id: str | None = None,
    db_path: str | Path = DB_PATH,
) -> None:
    with connect(db_path) as connection:
        connection.execute(
            "INSERT INTO calculations (offer_id, transaction_amount, estimated_cashback) VALUES (?, ?, ?)",
            (offer_id, str(transaction_amount), None if estimated_cashback is None else str(estimated_cashback)),
        )


def get_dashboard_stats(db_path: str | Path = DB_PATH) -> dict[str, Any]:
    with connect(db_path) as connection:
        offer_stats = connection.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END) AS active FROM offers"
        ).fetchone()
        cashback = connection.execute(
            "SELECT COALESCE(SUM(CAST(estimated_cashback AS REAL)), 0) FROM calculations WHERE estimated_cashback IS NOT NULL"
        ).fetchone()[0]
        investigation_count = connection.execute("SELECT COUNT(*) FROM investigations").fetchone()[0]
        recent_offers = connection.execute(
            "SELECT title, updated_at FROM offers ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
        recent_investigations = connection.execute(
            "SELECT merchant, status, updated_at FROM investigations ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
    activity = [
        {"kind": "Saved offer", "description": row["title"], "updated_at": row["updated_at"]}
        for row in recent_offers
    ] + [
        {"kind": "Investigation", "description": f"{row['merchant']} — {row['status']}", "updated_at": row["updated_at"]}
        for row in recent_investigations
    ]
    return {
        "saved_offers": offer_stats["total"] or 0,
        "active_offers": offer_stats["active"] or 0,
        "estimated_cashback": cashback,
        "investigations": investigation_count,
        "recent_activity": sorted(activity, key=lambda item: item["updated_at"], reverse=True)[:5],
    }


def list_investigations(db_path: str | Path = DB_PATH) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute("SELECT * FROM investigations ORDER BY updated_at DESC").fetchall()
    return [dict(row) for row in rows]


def save_investigation(
    details: dict[str, Any],
    investigation_id: str | None = None,
    db_path: str | Path = DB_PATH,
) -> str:
    identifier = investigation_id or str(uuid.uuid4())
    required = ("offer_description", "merchant", "transaction_date", "transaction_amount", "expected_cashback")
    if any(not str(details.get(key, "")).strip() for key in required):
        raise ValueError("Offer, merchant, date, amount, and expected cashback are required.")
    statuses = ("Waiting for cashback", "Investigation started", "Resolved", "Rejected by provider")
    status = details.get("status", statuses[0])
    if status not in statuses:
        raise ValueError("Choose a supported investigation status.")
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO investigations (
                id, offer_description, merchant, transaction_date, transaction_amount,
                expected_cashback, actual_cashback, transaction_reference, notes, status, evidence_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                offer_description = excluded.offer_description,
                merchant = excluded.merchant,
                transaction_date = excluded.transaction_date,
                transaction_amount = excluded.transaction_amount,
                expected_cashback = excluded.expected_cashback,
                actual_cashback = excluded.actual_cashback,
                transaction_reference = excluded.transaction_reference,
                notes = excluded.notes,
                status = excluded.status,
                evidence_path = excluded.evidence_path,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                identifier, *(str(details.get(key) or "") for key in required),
                None if details.get("actual_cashback") in (None, "") else str(details["actual_cashback"]),
                details.get("transaction_reference") or None, details.get("notes") or "",
                status, details.get("evidence_path") or None,
            ),
        )
    return identifier


def delete_evidence_file(evidence_path: str | None, evidence_dir: str | Path = EVIDENCE_DIR) -> None:
    if not evidence_path:
        return
    base = Path(evidence_dir).resolve()
    candidate = Path(evidence_path).resolve()
    if candidate.is_relative_to(base) and candidate.is_file():
        candidate.unlink()


def delete_investigation(
    investigation_id: str,
    db_path: str | Path = DB_PATH,
    evidence_dir: str | Path = EVIDENCE_DIR,
) -> None:
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT evidence_path FROM investigations WHERE id = ?", (investigation_id,)
        ).fetchone()
        connection.execute("DELETE FROM investigations WHERE id = ?", (investigation_id,))
    if row:
        delete_evidence_file(row["evidence_path"], evidence_dir)
