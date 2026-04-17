"""Orquestador de POST /query."""
from __future__ import annotations

import json
from typing import AsyncGenerator

from openai import AsyncOpenAI

from app.config import SETTINGS
from app.procesamiento.prompts import SYSTEM_PROMPT
from app.servicios.retrieval import ChunkRecuperado, recuperar
from app.servicios.vector_store import coleccion_parents, get_chroma, nombre_coleccion


def _expandir_parents(
    chunks: list[ChunkRecuperado],
    coleccion: str,
) -> list[ChunkRecuperado]:
    """Sustituye children por sus parents. Tablas (parent_id='') pasan tal cual.

    Deduplica: si varios children comparten el mismo parent_id, expande una vez.
    """
    col_parents = coleccion_parents(coleccion)
    chroma = get_chroma()

    vistos: dict[str, ChunkRecuperado] = {}
    resultado: list[ChunkRecuperado] = []
    tablas: list[ChunkRecuperado] = []

    for chunk in chunks:
        pid = chunk.metadatos.get("parent_id", "")

        if pid == "":
            tablas.append(chunk)
            continue

        if pid in vistos:
            continue

        col = chroma.get_collection(name=col_parents)
        data = col.get(ids=[pid], include=["documents", "metadatas"])

        if data["ids"]:
            expandido = ChunkRecuperado(
                chunk_id=pid,
                texto=data["documents"][0],
                metadatos=data["metadatas"][0] if data["metadatas"] else chunk.metadatos,
                score=chunk.score,
                score_vector=chunk.score_vector,
                score_bm25=chunk.score_bm25,
                score_fusion=chunk.score_fusion,
            )
            vistos[pid] = expandido
            resultado.append(expandido)
        else:
            resultado.append(chunk)

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

        paginas = f"Pág. {p_ini}" if p_ini == p_fin else f"Pág. {p_ini}-{p_fin}"
        if p_ini == -1:
            paginas = ""

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
    for chunk in chunks:
        meta = chunk.metadatos
        fuentes.append({
            "doc": meta.get("nombre_fichero", ""),
            "titulo": meta.get("titulo_documento", ""),
            "seccion": meta.get("seccion", ""),
            "pagina_inicio": meta.get("pagina_inicio", -1),
            "pagina_fin": meta.get("pagina_fin", -1),
            "score": round(chunk.score, 4),
            "es_anexo": bool(meta.get("dentro_de_anexo", False)),
        })
    return fuentes


async def _stream_respuesta(
    query: str,
    contexto: str,
    fuentes: list[dict],
) -> AsyncGenerator[str, None]:
    """Genera eventos SSE: tokens → sources → done."""
    client = AsyncOpenAI(api_key=SETTINGS.openai_api_key)

    stream = await client.chat.completions.create(
        model=SETTINGS.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Contexto:\n\n{contexto}\n\nPregunta: {query}"},
        ],
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"

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
    chunks_expandidos = _expandir_parents(chunks, coleccion)
    contexto = _construir_contexto(chunks_expandidos)
    fuentes = _construir_fuentes(chunks_expandidos)
    async for evento in _stream_respuesta(query, contexto, fuentes):
        yield evento
