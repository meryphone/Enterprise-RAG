"""Idempotent seeding of the IntecsaRAG beta users.

All user data (email, name, password) is read from env vars loaded from
.env.seed at startup. Safe to call multiple times — INSERT OR IGNORE skips
existing emails.

Per-slot env vars (N = 1..4):
  SEED_EMAIL_<N>, SEED_NAME_<N>, SEED_ROLE_<N>, SEED_PWD_<N>

Slots without SEED_EMAIL_<N> are skipped. A slot with SEED_EMAIL_<N> set but
missing any of the other vars fails fast — partial slots are configuration
errors, not intentional omissions.
"""
from __future__ import annotations

import logging
import os

from app.auth.models import create_user, hash_password, init_db

logger = logging.getLogger(__name__)

_SLOTS = ["1", "2", "3", "4"]


def run() -> None:
    """Create DB tables and insert users if they don't already exist."""
    init_db()
    creados = 0
    for n in _SLOTS:
        email = os.environ.get(f"SEED_EMAIL_{n}")
        if not email:
            continue
        name = os.environ.get(f"SEED_NAME_{n}")
        role = os.environ.get(f"SEED_ROLE_{n}")
        pwd = os.environ.get(f"SEED_PWD_{n}")
        if not all([name, role, pwd]):
            missing = [
                k for k, v in {
                    f"SEED_NAME_{n}": name,
                    f"SEED_ROLE_{n}": role,
                    f"SEED_PWD_{n}": pwd,
                }.items() if not v
            ]
            raise RuntimeError(
                f"Slot {n} (SEED_EMAIL_{n}={email}) tiene variables faltantes: "
                f"{', '.join(missing)}. Completa el slot o elimina SEED_EMAIL_{n}."
            )
        create_user(email, name, role, hash_password(pwd))
        creados += 1
    logger.info("Seed: %d usuario(s) procesado(s).", creados)
