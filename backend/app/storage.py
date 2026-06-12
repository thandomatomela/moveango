import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "moveango.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quote_number TEXT UNIQUE NOT NULL,
                customer_name TEXT,
                customer_phone TEXT,
                pickup TEXT,
                dropoff TEXT,
                service_type TEXT,
                load_type TEXT,
                amount REAL,
                status TEXT DEFAULT 'Draft',
                pdf_url TEXT,
                customer_distance_km REAL,
                operational_distance_km REAL,
                dead_mileage_km REAL,
                billing_distance_km REAL,
                recommended_vehicle TEXT,
                helpers_required INTEGER,
                internal_breakdown TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()

def save_quote(quote: dict):
    now = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO quotes (
                quote_number,
                customer_name,
                customer_phone,
                pickup,
                dropoff,
                service_type,
                load_type,
                amount,
                status,
                pdf_url,
                customer_distance_km,
                operational_distance_km,
                dead_mileage_km,
                billing_distance_km,
                recommended_vehicle,
                helpers_required,
                internal_breakdown,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            quote.get("quote_number"),
            quote.get("customer_name"),
            quote.get("customer_phone"),
            quote.get("pickup"),
            quote.get("dropoff"),
            quote.get("customer_service_label") or quote.get("service_type"),
            quote.get("load_type"),
            quote.get("estimated_quote"),
            quote.get("status", "Draft"),
            quote.get("pdf_url"),
            quote.get("distance_km"),
            quote.get("operational_distance_km"),
            quote.get("dead_mileage_km"),
            quote.get("chargeable_distance_km"),
            quote.get("recommended_vehicle"),
            quote.get("helpers_required"),
            str(quote.get("breakdown", {})),
            now,
            now
        ))
        conn.commit()

def list_quotes(limit: int = 100, search: Optional[str] = None):
    with get_connection() as conn:
        if search:
            q = f"%{search}%"
            rows = conn.execute("""
                SELECT * FROM quotes
                WHERE quote_number LIKE ?
                   OR customer_name LIKE ?
                   OR customer_phone LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (q, q, q, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM quotes
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()

        return [dict(row) for row in rows]

def get_quote(quote_number: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM quotes WHERE quote_number = ?",
            (quote_number,)
        ).fetchone()
        return dict(row) if row else None

def update_quote_status(quote_number: str, status: str):
    now = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        conn.execute("""
            UPDATE quotes
            SET status = ?, updated_at = ?
            WHERE quote_number = ?
        """, (status, now, quote_number))
        conn.commit()

    return get_quote(quote_number)
