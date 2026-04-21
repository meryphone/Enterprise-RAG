"""Aplicación FastAPI — punto de entrada del backend."""
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
    """Invalida el índice BM25 al arrancar para que se reconstruya con el esquema actual."""
    invalidar_cache_bm25()
    logger.info("Caché BM25 invalidada en startup.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{p}" for p in range(3000, 3010)],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(projects_router)
app.include_router(query_router)
