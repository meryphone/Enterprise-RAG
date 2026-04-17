"""Aplicación FastAPI — punto de entrada del backend."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.servicios.query import ejecutar_query

app = FastAPI(title="IntecsaRAG", version="0.1.0")


class QueryRequest(BaseModel):
    query: str
    proyecto_id: str | None = None
    empresa: str = "intecsa"
    tipo_doc: str | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/query")
async def query(req: QueryRequest) -> StreamingResponse:
    return StreamingResponse(
        ejecutar_query(
            query=req.query,
            proyecto_id=req.proyecto_id,
            empresa=req.empresa,
            tipo_doc=req.tipo_doc,
        ),
        media_type="text/event-stream",
    )
