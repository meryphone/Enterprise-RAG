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


def _fusionar_partes_tabla(chunks: list[ChunkRecuperado]) -> list[ChunkRecuperado]:
    """Fusiona chunks del mismo documento y sección que son partes de una tabla dividida.

    Cuando el chunker parte una tabla grande en varios chunks, todos comparten
    nombre_fichero y seccion. Aquí los concatenamos para que el LLM vea la tabla
    completa. Chunks que no son tabla (no empiezan por '|') no se fusionan.
    """
    tablas: dict[str, list[ChunkRecuperado]] = {}
    resto: list[ChunkRecuperado] = []

    for chunk in chunks:
        meta = chunk.metadatos
        es_tabla = chunk.texto.strip().startswith("|")
        nombre = (meta or {}).get("nombre_fichero", "")
        seccion = (meta or {}).get("seccion", "")

        if es_tabla and nombre and seccion:
            clave = f"{nombre}||{seccion}"
            tablas.setdefault(clave, []).append(chunk)
        else:
            resto.append(chunk)

    resultado: list[ChunkRecuperado] = list(resto)
    for partes in tablas.values():
        if len(partes) == 1:
            resultado.append(partes[0])
            continue

        partes.sort(key=lambda c: c.metadatos.get("pagina_inicio", 0))
        texto_unido = "\n".join(p.texto.rstrip() for p in partes)
        meta_merged = dict(partes[0].metadatos)
        p_fin = max(p.metadatos.get("pagina_fin", -1) for p in partes)
        if p_fin != -1:
            meta_merged["pagina_fin"] = p_fin
        resultado.append(ChunkRecuperado(
            chunk_id=partes[0].chunk_id,
            texto=texto_unido,
            metadatos=meta_merged,
            score=max(p.score for p in partes),
        ))
        logger.info(
            "Fusionados %d chunks de tabla '%s' § '%s'",
            len(partes),
            partes[0].metadatos.get("nombre_fichero", ""),
            partes[0].metadatos.get("seccion", ""),
        )

    return resultado


def _construir_contexto(chunks: list[ChunkRecuperado]) -> str:
    """Envuelve cada chunk en XML con id numérico y nombre de documento.

    El atributo 'doc' permite al LLM identificar la procedencia de cada fuente
    cuando la pregunta es específica sobre un documento concreto.
    Los metadatos de sección/versión/páginas viajan en el payload 'sources' del SSE.
    """
    partes: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.metadatos
        nombre = meta.get("nombre_fichero", "")
        doc_id = nombre.removesuffix(".pdf") if nombre else f"fuente-{i}"

        attrs = f'id="{i}" doc="{doc_id}"'

        edicion = meta.get("version", "") or ""
        if edicion:
            attrs += f' edicion="{edicion}"'

        seccion = meta.get("seccion", "") or ""
        if seccion:
            attrs += f' seccion="{seccion}"'

        p_ini = meta.get("pagina_inicio", -1)
        p_fin = meta.get("pagina_fin", -1)
        if p_ini != -1:
            paginas = str(p_ini) if p_fin == p_ini or p_fin == -1 else f"{p_ini}-{p_fin}"
            attrs += f' paginas="{paginas}"'

        partes.append(f'<fuente {attrs}>\n{chunk.texto}\n</fuente>')
    return "\n\n".join(partes)


def _construir_fuentes(chunks: list[ChunkRecuperado]) -> list[dict]:
    fuentes = []
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.metadatos
        fuentes.append({
            "ref": i,
            "doc": meta.get("nombre_fichero", ""),
            "titulo": meta.get("titulo_documento", ""),
            "version": meta.get("version", ""),
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
        temperature=0.0,
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
        contexto_vacio = "(No se han encontrado fragmentos relevantes en la documentación indexada.)"
        async for evento in _stream_respuesta(query, contexto_vacio, []):
            yield evento
        return

    chunks_expandidos = _expandir_parents(chunks, coleccion)
    chunks_expandidos = _fusionar_partes_tabla(chunks_expandidos)
    contexto = _construir_contexto(chunks_expandidos)
    fuentes = _construir_fuentes(chunks_expandidos)
    async for evento in _stream_respuesta(query, contexto, fuentes):
        yield evento
