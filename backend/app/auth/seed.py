"""Idempotent seeding of the four IntecsaRAG beta users.

Reads plaintext passwords from env vars (loaded from .env.seed at startup).
Safe to call multiple times — INSERT OR IGNORE skips existing emails.
"""
from __future__ import annotations

import os

from app.auth.models import create_user, hash_password, init_db

_USERS = [
    ("jose.capilla@intecsaindustrial.com",     "Jose Maria Capilla Silvente",      "user",  "SEED_PWD_JOSE_CAPILLA"),
    ("jose.gonzalez@intecsaindustrial.com",    "Jose Javier Gonzalez Fernandez",   "user",  "SEED_PWD_JOSE_GONZALEZ"),
    ("eduardo.martinez@intecsaindustrial.com", "Eduardo Martinez Gracia",          "user",  "SEED_PWD_EDUARDO_MARTINEZ"),
    ("maria.capilla@intecsaindustrial.com",    "Maria Capilla Zapata",             "admin", "SEED_PWD_MARIA_CAPILLA"),
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
