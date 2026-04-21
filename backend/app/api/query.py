from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.rag.query import ejecutar_query

router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    proyecto_id: str | None = None
    empresa: str = "intecsa"
    tipo_doc: str | None = None


@router.post("/query")
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
