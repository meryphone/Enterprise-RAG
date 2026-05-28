"""Orquestador de POST /query: retrieval → expansión → streaming SSE."""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from openai import AsyncOpenAI

from app.config import SETTINGS
from app.ingestion.prompts import SYSTEM_PROMPT
from app.rag.context_builder import (
    construir_contexto,
    construir_fuentes,
    expandir_parents,
    fusionar_partes_tabla,
)
from app.rag.retrieval import recuperar
from app.rag.vector_store import get_chroma, nombre_coleccion

# Re-exports para retrocompatibilidad (tests y scripts/eval_trulens importan estos nombres).
_construir_contexto = construir_contexto
_expandir_parents = expandir_parents

logger = logging.getLogger(__name__)

_openai_async_client: AsyncOpenAI | None = None


def _get_openai_async_client() -> AsyncOpenAI:
    global _openai_async_client
    if _openai_async_client is None:
        if not SETTINGS.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY no configurada.")
        _openai_async_client = AsyncOpenAI(api_key=SETTINGS.openai_api_key)
    return _openai_async_client


async def _stream_respuesta(
    query: str,
    contexto: str,
    fuentes: list[dict],
) -> AsyncGenerator[str, None]:
    """Emite eventos SSE en orden: tokens → sources → done (o error)."""
    client = _get_openai_async_client()
    stream = await client.chat.completions.create(
        model=SETTINGS.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Contexto:\n\n{contexto}\n\nPregunta: {query}"},
        ],
        temperature=0.0,
        stream=True,
    )

    try:
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"
    except Exception as exc:
        logger.error("Error durante el streaming de GPT-4o: %s", exc)
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
    finally:
        yield f"data: {json.dumps({'type': 'sources', 'sources': fuentes})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"


async def ejecutar_query(
    query: str,
    proyecto_id: str | None,
    empresa: str = "intecsa",
) -> AsyncGenerator[str, None]:
    """Punto de entrada para el endpoint POST /query."""
    coleccion = nombre_coleccion(empresa, proyecto_id)
    chunks = recuperar(query, proyecto_id, empresa)

    if not chunks:
        contexto = "(No se han encontrado fragmentos relevantes en la documentación indexada.)"
        async for evento in _stream_respuesta(query, contexto, []):
            yield evento
        return

    chunks = expandir_parents(chunks, coleccion)
    chunks = fusionar_partes_tabla(chunks)
    contexto = construir_contexto(chunks)
    fuentes = construir_fuentes(chunks)
    async for evento in _stream_respuesta(query, contexto, fuentes):
        yield evento
