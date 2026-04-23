"""FastAPI application entry point."""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.projects import router as projects_router
from app.api.query import router as query_router
from app.auth.router import router as auth_router
from app.auth.seed import run as seed_users
from app.rag.retrieval import invalidar_cache_bm25

# Load .env.seed so seed passwords are available before the startup event.
# override=False: env vars already set (e.g. by tests) are not overwritten.
_seed_env = os.path.join(os.path.dirname(__file__), "..", ".env.seed")
load_dotenv(_seed_env, override=False)

logger = logging.getLogger(__name__)

app = FastAPI(title="IntecsaRAG", version="0.1.0")


@app.on_event("startup")
async def _startup() -> None:
    # TESTING=1 skips seeding so test fixtures can control the DB themselves.
    if os.environ.get("TESTING") != "1":
        seed_users()
    invalidar_cache_bm25()
    logger.info("Startup complete.")


_allowed_origins = [f"http://localhost:{p}" for p in range(3000, 3010)]
_cf_origin = os.environ.get("CLOUDFLARE_ORIGIN")
if _cf_origin:
    _allowed_origins.append(_cf_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(projects_router)
app.include_router(query_router)
