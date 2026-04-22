"""Idempotent seeding of the four IntecsaRAG beta users.

Reads plaintext passwords from env vars (loaded from .env.seed at startup).
Safe to call multiple times — INSERT OR IGNORE skips existing emails.
"""
from __future__ import annotations

import os

from app.auth.models import create_user, hash_password, init_db

_USERS = [
    ("user1@empresa.com",     "Usuario Beta 1",      "user",  "SEED_PWD_JOSE_CAPILLA"),
    ("user2@empresa.com",    "Usuario Beta 2",   "user",  "SEED_PWD_JOSE_GONZALEZ"),
    ("user3@empresa.com", "Usuario Beta 3",          "user",  "SEED_PWD_EDUARDO_MARTINEZ"),
    ("admin@empresa.com",    "Admin Beta",             "admin", "SEED_PWD_MARIA_CAPILLA"),
]


def run() -> None:
    """Create DB tables and insert users if they don't already exist."""
    init_db()
    for email, full_name, role, env_key in _USERS:
        pwd = os.environ.get(env_key)
        if not pwd:
            raise RuntimeError(
                f"Missing env var {env_key}. "
                "Add it to .env.seed and load it before starting the server."
            )
        create_user(email, full_name, role, hash_password(pwd))
