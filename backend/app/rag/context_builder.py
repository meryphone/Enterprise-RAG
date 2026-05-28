"""Construcción de contexto para el LLM y payload de fuentes para el frontend.

- `expandir_parents`: sustituye children por sus parents (recuperación por ID).
- `fusionar_partes_tabla`: reconstruye tablas grandes partidas por el chunker.
- `construir_contexto`: envuelve cada chunk en `<fuente>` XML para GPT-4o.
- `construir_fuentes`: payload JSON-serializable para el evento `sources` del SSE.
"""
from __future__ import annotations

import logging

from app.rag.retrieval import ChunkRecuperado
from app.rag.vector_store import coleccion_parents, get_chroma

logger = logging.getLogger(__name__)


def expandir_parents(chunks: list[ChunkRecuperado], coleccion: str) -> list[ChunkRecuperado]:
    """Sustituye children por sus parents en una sola llamada a ChromaDB.

    Tablas (`parent_id=''`) pasan tal cual. Deduplica por parent_id.
    """
    tablas: list[ChunkRecuperado] = []
    por_parent: dict[str, ChunkRecuperado] = {}

    for chunk in chunks:
        pid = chunk.metadatos.get("parent_id", "")
        if pid == "":
            tablas.append(chunk)
        elif pid not in por_parent:
            por_parent[pid] = chunk

    if not por_parent:
        return tablas

    col = get_chroma().get_collection(name=coleccion_parents(coleccion))
    data = col.get(ids=list(por_parent.keys()), include=["documents", "metadatas"])
    recuperados = {
        pid: (doc, meta)
        for pid, doc, meta in zip(
            data.get("ids", []),
            data.get("documents", []),
            data.get("metadatas", []) or [{}] * len(data.get("ids", [])),
        )
    }

    resultado: list[ChunkRecuperado] = []
    for pid, original in por_parent.items():
        if pid in recuperados:
            texto, meta = recuperados[pid]
            resultado.append(ChunkRecuperado(
                chunk_id=pid,
                texto=texto,
                metadatos=meta or original.metadatos,
                score=original.score,
                score_vector=original.score_vector,
                score_bm25=original.score_bm25,
                score_fusion=original.score_fusion,
            ))
        else:
            logger.warning("Parent '%s' no encontrado en '%s__parents'. Se usa el child.", pid, coleccion)
            resultado.append(original)

    return resultado + tablas


def fusionar_partes_tabla(chunks: list[ChunkRecuperado]) -> list[ChunkRecuperado]:
    """Fusiona chunks del mismo documento y sección que son partes de una tabla dividida.

    Cuando el chunker parte una tabla grande, todas las piezas comparten nombre_fichero
    y sección. Se concatenan en orden de página para que el LLM vea la tabla completa.
    """
    tablas: dict[str, list[ChunkRecuperado]] = {}
    resto: list[ChunkRecuperado] = []

    for chunk in chunks:
        meta = chunk.metadatos or {}
        es_tabla = chunk.texto.strip().startswith("|")
        nombre = meta.get("nombre_fichero", "")
        seccion = meta.get("seccion", "")
        if es_tabla and nombre and seccion:
            tablas.setdefault(f"{nombre}||{seccion}", []).append(chunk)
        else:
            resto.append(chunk)

    resultado = list(resto)
    for partes in tablas.values():
        if len(partes) == 1:
            resultado.append(partes[0])
            continue

        partes.sort(key=lambda c: c.metadatos.get("pagina_inicio", 0))
        meta_merged = dict(partes[0].metadatos)
        p_fin = max(p.metadatos.get("pagina_fin", -1) for p in partes)
        if p_fin != -1:
            meta_merged["pagina_fin"] = p_fin
        resultado.append(ChunkRecuperado(
            chunk_id=partes[0].chunk_id,
            texto="\n".join(p.texto.rstrip() for p in partes),
            metadatos=meta_merged,
            score=max(p.score for p in partes),
        ))
        logger.info(
            "Fusionados %d chunks de tabla '%s' § '%s'",
            len(partes),
            meta_merged.get("nombre_fichero", ""),
            meta_merged.get("seccion", ""),
        )

    return resultado


def construir_contexto(chunks: list[ChunkRecuperado]) -> str:
    """Envuelve cada chunk en `<fuente>` XML con id numérico y nombre de documento.

    Los metadatos extra viajan en el payload `sources` del SSE; aquí solo se incluyen
    los necesarios para que el LLM identifique la procedencia.
    """
    partes: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.metadatos
        nombre = meta.get("nombre_fichero", "")
        doc_id = nombre.removesuffix(".pdf") if nombre else f"fuente-{i}"
        attrs = f'id="{i}" doc="{doc_id}"'

        if edicion := (meta.get("version", "") or ""):
            attrs += f' edicion="{edicion}"'
        if seccion := (meta.get("seccion", "") or ""):
            attrs += f' seccion="{seccion}"'

        p_ini = meta.get("pagina_inicio", -1)
        p_fin = meta.get("pagina_fin", -1)
        if p_ini != -1:
            paginas = str(p_ini) if p_fin in (p_ini, -1) else f"{p_ini}-{p_fin}"
            attrs += f' paginas="{paginas}"'

        partes.append(f"<fuente {attrs}>\n{chunk.texto}\n</fuente>")
    return "\n\n".join(partes)


def construir_fuentes(chunks: list[ChunkRecuperado]) -> list[dict]:
    """Payload JSON para el evento `sources` del SSE (chips en el frontend)."""
    return [
        {
            "ref": i,
            "doc": chunk.metadatos.get("nombre_fichero", ""),
            "titulo": chunk.metadatos.get("titulo_documento", ""),
            "version": chunk.metadatos.get("version", ""),
            "seccion": chunk.metadatos.get("seccion", ""),
            "pagina_inicio": chunk.metadatos.get("pagina_inicio", -1),
            "pagina_fin": chunk.metadatos.get("pagina_fin", -1),
            "score": round(chunk.score, 4),
            "es_anexo": bool(chunk.metadatos.get("dentro_de_anexo", False)),
        }
        for i, chunk in enumerate(chunks, start=1)
    ]
