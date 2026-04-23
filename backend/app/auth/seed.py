"""Idempotent seeding of the IntecsaRAG beta users.

All user data (email, name, password) is read from env vars loaded from
.env.seed at startup. Safe to call multiple times — INSERT OR IGNORE skips
existing emails.

Required env vars per user slot (1–4):
  SEED_EMAIL_<N>, SEED_NAME_<N>, SEED_ROLE_<N>, SEED_PWD_<N>
"""
from __future__ import annotations

import os

from app.auth.models import create_user, hash_password, init_db

_SLOTS = ["1", "2", "3", "4"]


def run() -> None:
    """Create DB tables and insert users if they don't already exist."""
    init_db()
    for n in _SLOTS:
        email = os.environ.get(f"SEED_EMAIL_{n}")
        name = os.environ.get(f"SEED_NAME_{n}")
        role = os.environ.get(f"SEED_ROLE_{n}")
        pwd = os.environ.get(f"SEED_PWD_{n}")
        if not all([email, name, role, pwd]):
            missing = [k for k, v in {
                f"SEED_EMAIL_{n}": email,
                f"SEED_NAME_{n}": name,
                f"SEED_ROLE_{n}": role,
                f"SEED_PWD_{n}": pwd,
            }.items() if not v]
            raise RuntimeError(
                f"Missing env vars: {', '.join(missing)}. "
                "Add them to .env.seed and load it before starting the server."
            )
        create_user(email, name, role, hash_password(pwd))
