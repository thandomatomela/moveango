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


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def column_exists(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def ensure_column(conn, table_name: str, column_name: str, column_type: str):
    if not column_exists(conn, table_name, column_name):
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        )


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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_number TEXT UNIQUE NOT NULL,
                quote_number TEXT,
                customer_name TEXT,
                customer_phone TEXT,
                pickup TEXT,
                dropoff TEXT,
                service_type TEXT,
                amount REAL,
                status TEXT DEFAULT 'Booked',
                collection_date TEXT,
                collection_time TEXT,
                assigned_driver TEXT,
                assigned_helper TEXT,
                assigned_vehicle TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS staff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                role TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TEXT,
                updated_at TEXT
            )
        """)

        ensure_column(conn, "jobs", "assigned_vehicle", "TEXT")
        ensure_column(conn, "jobs", "assigned_driver", "TEXT")
        ensure_column(conn, "jobs", "assigned_helper", "TEXT")
        ensure_column(conn, "jobs", "notes", "TEXT")
        ensure_column(conn, "jobs", "collection_date", "TEXT")
        ensure_column(conn, "jobs", "collection_time", "TEXT")

        conn.commit()


def save_quote(quote: dict):
    now = now_iso()

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
            quote.get("billing_distance_km") or quote.get("chargeable_distance_km"),
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
    now = now_iso()

    with get_connection() as conn:
        conn.execute("""
            UPDATE quotes
            SET status = ?, updated_at = ?
            WHERE quote_number = ?
        """, (status, now, quote_number))
        conn.commit()

    return get_quote(quote_number)


def next_job_number():
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"MVJ-{stamp}"


def convert_quote_to_job(
    quote_number: str,
    collection_date: str = "",
    collection_time: str = "",
    assigned_driver: str = "",
    assigned_helper: str = "",
    assigned_vehicle: str = "",
    notes: str = ""
):
    quote = get_quote(quote_number)

    if not quote:
        return None

    now = now_iso()
    job_number = next_job_number()

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM jobs WHERE quote_number = ?",
            (quote_number,)
        ).fetchone()

        if existing:
            return dict(existing)

        conn.execute("""
            INSERT INTO jobs (
                job_number,
                quote_number,
                customer_name,
                customer_phone,
                pickup,
                dropoff,
                service_type,
                amount,
                status,
                collection_date,
                collection_time,
                assigned_driver,
                assigned_helper,
                assigned_vehicle,
                notes,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_number,
            quote.get("quote_number"),
            quote.get("customer_name"),
            quote.get("customer_phone"),
            quote.get("pickup"),
            quote.get("dropoff"),
            quote.get("service_type"),
            quote.get("amount"),
            "Booked",
            collection_date,
            collection_time,
            assigned_driver,
            assigned_helper,
            assigned_vehicle,
            notes,
            now,
            now
        ))

        conn.execute("""
            UPDATE quotes
            SET status = ?, updated_at = ?
            WHERE quote_number = ?
        """, ("Accepted", now, quote_number))

        conn.commit()

    return get_job(job_number)


def get_job(job_number: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_number = ?",
            (job_number,)
        ).fetchone()

        return dict(row) if row else None


def list_jobs(limit: int = 100, search: Optional[str] = None):
    with get_connection() as conn:
        if search:
            q = f"%{search}%"
            rows = conn.execute("""
                SELECT * FROM jobs
                WHERE job_number LIKE ?
                   OR quote_number LIKE ?
                   OR customer_name LIKE ?
                   OR customer_phone LIKE ?
                   OR assigned_driver LIKE ?
                   OR assigned_helper LIKE ?
                   OR assigned_vehicle LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (q, q, q, q, q, q, q, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM jobs
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()

        return [dict(row) for row in rows]


def update_job_status(job_number: str, status: str):
    now = now_iso()

    with get_connection() as conn:
        conn.execute("""
            UPDATE jobs
            SET status = ?, updated_at = ?
            WHERE job_number = ?
        """, (status, now, job_number))
        conn.commit()

    return get_job(job_number)


def update_job_details(
    job_number: str,
    collection_date: str = "",
    collection_time: str = "",
    assigned_driver: str = "",
    assigned_helper: str = "",
    assigned_vehicle: str = "",
    notes: str = ""
):
    now = now_iso()

    with get_connection() as conn:
        conn.execute("""
            UPDATE jobs
            SET collection_date = ?,
                collection_time = ?,
                assigned_driver = ?,
                assigned_helper = ?,
                assigned_vehicle = ?,
                notes = ?,
                updated_at = ?
            WHERE job_number = ?
        """, (
            collection_date,
            collection_time,
            assigned_driver,
            assigned_helper,
            assigned_vehicle,
            notes,
            now,
            job_number
        ))
        conn.commit()

    return get_job(job_number)


def create_staff_member(
    name: str,
    phone: str = "",
    role: str = "helper",
    status: str = "active"
):
    now = now_iso()

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO staff (
                name,
                phone,
                role,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            name,
            phone,
            role,
            status,
            now,
            now
        ))

        conn.commit()
        staff_id = cursor.lastrowid

    return get_staff_member(staff_id)


def get_staff_member(staff_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM staff WHERE id = ?",
            (staff_id,)
        ).fetchone()

        return dict(row) if row else None


def list_staff(
    role: Optional[str] = None,
    status: Optional[str] = "active"
):
    with get_connection() as conn:
        query = "SELECT * FROM staff WHERE 1 = 1"
        params = []

        if role:
            query += " AND role = ?"
            params.append(role)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY role, name"

        rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]


def update_staff_member(
    staff_id: int,
    name: str = "",
    phone: str = "",
    role: str = "",
    status: str = ""
):
    existing = get_staff_member(staff_id)

    if not existing:
        return None

    now = now_iso()

    updated_name = name or existing.get("name")
    updated_phone = phone or existing.get("phone")
    updated_role = role or existing.get("role")
    updated_status = status or existing.get("status")

    with get_connection() as conn:
        conn.execute("""
            UPDATE staff
            SET name = ?,
                phone = ?,
                role = ?,
                status = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            updated_name,
            updated_phone,
            updated_role,
            updated_status,
            now,
            staff_id
        ))
        conn.commit()

    return get_staff_member(staff_id)