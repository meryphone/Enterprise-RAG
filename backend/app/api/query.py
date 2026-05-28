"""Endpoint de query — emite respuestas RAG por Server-Sent Events."""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import require_auth
from app.rag.query import ejecutar_query

router = APIRouter()


class QueryRequest(BaseModel):
    """Cuerpo de la petición para POST /query."""
    query: str
    proyecto_id: str | None = None
    empresa: str = "intecsa"


@router.post("/query", dependencies=[Depends(require_auth)])
async def query(req: QueryRequest) -> StreamingResponse:
    """Ejecuta una query RAG y emite la respuesta como SSE.

    Tipos de evento emitidos en orden: ``token`` (texto incremental, varios),
    ``sources`` (array JSON de citas, tras el último token), ``done`` (fin del stream),
    ``error`` (en caso de fallo, en lugar de done).

    Args:
        req: Parámetros de la query — texto de la pregunta y scope.

    Returns:
        StreamingResponse con media_type ``text/event-stream``.
    """
    return StreamingResponse(
        ejecutar_query(
            query=req.query,
            proyecto_id=req.proyecto_id,
            empresa=req.empresa,
        ),
        media_type="text/event-stream",
    )
