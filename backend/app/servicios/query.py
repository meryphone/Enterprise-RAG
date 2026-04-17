"""Orquestador de POST /query."""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from openai import AsyncOpenAI

from app.config import SETTINGS
from app.procesamiento.prompts import SYSTEM_PROMPT
from app.servicios.retrieval import ChunkRecuperado, recuperar
from app.servicios.vector_store import coleccion_parents, get_chroma, nombre_coleccion

logger = logging.getLogger(__name__)


def _expandir_parents(
    chunks: list[ChunkRecuperado],
    coleccion: str,
) -> list[ChunkRecuperado]:
    """Sustituye children por sus parents en una sola llamada a ChromaDB.

    Tablas (parent_id='') pasan tal cual. Deduplica por parent_id.
    """
    tablas: list[ChunkRecuperado] = []
    por_parent: dict[str, ChunkRecuperado] = {}  # parent_id → chunk original (para metadatos/scores)

    for chunk in chunks:
        pid = chunk.metadatos.get("parent_id", "")
        if pid == "":
            tablas.append(chunk)
        elif pid not in por_parent:
            por_parent[pid] = chunk

    resultado: list[ChunkRecuperado] = []

    if por_parent:
        chroma = get_chroma()
        col = chroma.get_collection(name=coleccion_parents(coleccion))
        data = col.get(ids=list(por_parent.keys()), include=["documents", "metadatas"])

        recuperados: dict[str, tuple[str, dict]] = {
            pid: (doc, meta)
            for pid, doc, meta in zip(
                data.get("ids", []),
                data.get("documents", []),
                data.get("metadatas", []) or [{}] * len(data.get("ids", [])),
            )
        }

        for pid, chunk_original in por_parent.items():
            if pid in recuperados:
                texto_parent, meta_parent = recuperados[pid]
                resultado.append(ChunkRecuperado(
                    chunk_id=pid,
                    texto=texto_parent,
                    metadatos=meta_parent or chunk_original.metadatos,
                    score=chunk_original.score,
                    score_vector=chunk_original.score_vector,
                    score_bm25=chunk_original.score_bm25,
                    score_fusion=chunk_original.score_fusion,
                ))
            else:
                logger.warning("Parent '%s' no encontrado en '%s__parents'. Usando child.", pid, coleccion)
                resultado.append(chunk_original)

    return resultado + tablas


def _construir_contexto(chunks: list[ChunkRecuperado]) -> str:
    """Numera y formatea los chunks para el LLM.

    Formato: [n] Documento: X | Sección: Y | Pág. Z
    """
    partes: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.metadatos
        nombre = meta.get("nombre_fichero", "")
        seccion = meta.get("seccion", "")
        p_ini = meta.get("pagina_inicio", -1)
        p_fin = meta.get("pagina_fin", -1)

        if p_ini == -1 or p_fin == -1:
            paginas = ""
        elif p_ini == p_fin:
            paginas = f"Pág. {p_ini}"
        else:
            paginas = f"Pág. {p_ini}-{p_fin}"

        cabecera_partes = [f"Documento: {nombre}"]
        if seccion:
            cabecera_partes.append(f"Sección: {seccion}")
        if paginas:
            cabecera_partes.append(paginas)

        cabecera = " | ".join(cabecera_partes)
        partes.append(f"[{i}] {cabecera}\n{chunk.texto}")

    return "\n\n".join(partes)


def _construir_fuentes(chunks: list[ChunkRecuperado]) -> list[dict]:
    fuentes = []
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.metadatos
        fuentes.append({
            "ref": i,
            "doc": meta.get("nombre_fichero", ""),
            "titulo": meta.get("titulo_documento", ""),
            "seccion": meta.get("seccion", ""),
            "pagina_inicio": meta.get("pagina_inicio", -1),
            "pagina_fin": meta.get("pagina_fin", -1),
            "score": round(chunk.score, 4),
            "es_anexo": bool(meta.get("dentro_de_anexo", False)),
        })
    return fuentes


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
    """Genera eventos SSE: tokens → sources → done."""
    client = _get_openai_async_client()

    stream = await client.chat.completions.create(
        model=SETTINGS.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Contexto:\n\n{contexto}\n\nPregunta: {query}"},
        ],
        stream=True,
    )

    try:
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"
    except Exception as exc:
        logger.error("Error en streaming GPT-4o: %s", exc)
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
    finally:
        yield f"data: {json.dumps({'type': 'sources', 'sources': fuentes})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"


async def ejecutar_query(
    query: str,
    proyecto_id: str | None,
    empresa: str = "intecsa",
    tipo_doc: str | None = None,
) -> AsyncGenerator[str, None]:
    """Punto de entrada para el endpoint POST /query."""
    coleccion = nombre_coleccion(empresa, proyecto_id)
    chunks = recuperar(query, proyecto_id, empresa, tipo_doc)

    if not chunks:
        yield f"data: {json.dumps({'type': 'token', 'content': 'No he encontrado documentación relevante para esta consulta.'})}\n\n"
        yield f"data: {json.dumps({'type': 'sources', 'sources': []})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    chunks_expandidos = _expandir_parents(chunks, coleccion)
    contexto = _construir_contexto(chunks_expandidos)
    fuentes = _construir_fuentes(chunks_expandidos)
    async for evento in _stream_respuesta(query, contexto, fuentes):
        yield evento
