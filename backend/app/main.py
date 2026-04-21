"""FastAPI application entry point.

Registers API routers and CORS middleware. Business logic lives in
``app.ingestion``, ``app.rag``, and ``app.api``; this file only wires them up.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.projects import router as projects_router
from app.api.query import router as query_router
from app.rag.retrieval import invalidar_cache_bm25

logger = logging.getLogger(__name__)

app = FastAPI(title="IntecsaRAG", version="0.1.0")


@app.on_event("startup")
async def _limpiar_cache_bm25() -> None:
    """Invalidate the BM25 cache at startup so it is rebuilt with the current schema."""
    invalidar_cache_bm25()
    logger.info("BM25 cache invalidated at startup.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{p}" for p in range(3000, 3010)],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(projects_router)
app.include_router(query_router)
