"""Aplicación FastAPI — punto de entrada del backend.

Endpoints definidos en CLAUDE.md:
    POST /query    — recibe pregunta, scope opcional e historial.
                     Devuelve respuesta en streaming SSE.
    GET  /projects — lista de proyectos disponibles.
    POST /ingest   — recibe PDF + metadatos. Solo accesible por administrador.
    GET  /health   — estado del sistema.

TODO (Fase 1 → 4): implementar endpoints a medida que avanza el pipeline.
"""
from fastapi import FastAPI

app = FastAPI(title="IntecsaRAG", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
