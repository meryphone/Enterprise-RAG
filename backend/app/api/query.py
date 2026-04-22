"""Query endpoint — streams RAG responses via Server-Sent Events."""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import require_auth
from app.rag.query import ejecutar_query

router = APIRouter()


class QueryRequest(BaseModel):
    """Request body for POST /query."""
    query: str
    proyecto_id: str | None = None
    empresa: str = "intecsa"
    tipo_doc: str | None = None


@router.post("/query", dependencies=[Depends(require_auth)])
async def query(req: QueryRequest) -> StreamingResponse:
    """Execute a RAG query and stream the response as SSE.

    Event types emitted in order: ``token`` (incremental text, multiple),
    ``sources`` (citations JSON array, after last token), ``done`` (stream end),
    ``error`` (on failure, instead of done).

    Args:
        req: Query parameters including question text, scope, and optional type filter.

    Returns:
        StreamingResponse with media_type ``text/event-stream``.
    """
    return StreamingResponse(
        ejecutar_query(
            query=req.query,
            proyecto_id=req.proyecto_id,
            empresa=req.empresa,
            tipo_doc=req.tipo_doc,
        ),
        media_type="text/event-stream",
    )
