"""SQLite user store for local authentication."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import bcrypt

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "auth.sqlite"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the users table if it does not exist."""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                email            TEXT    UNIQUE NOT NULL,
                hashed_password  TEXT    NOT NULL,
                full_name        TEXT    NOT NULL,
                role             TEXT    NOT NULL DEFAULT 'user'
            )
        """)


def get_user_by_email(email: str) -> dict[str, Any] | None:
    """Return user dict or None if not found."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT email, hashed_password, full_name, role FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    return dict(row) if row else None


def create_user(email: str, full_name: str, role: str, hashed_password: str) -> None:
    """Insert a user. Silently skips if email already exists."""
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (email, full_name, role, hashed_password) VALUES (?,?,?,?)",
            (email, full_name, role, hashed_password),
        )


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(12)).decode()
