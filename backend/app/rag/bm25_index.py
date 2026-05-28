"""Índice BM25 en memoria por colección.

Se construye lazy en la primera consulta y se cachea por proceso. Hay que invalidar
manualmente con `invalidar_cache_bm25(coleccion)` tras reingerir documentos.

ChromaDB Cloud limita `col.get()` a 300 items por llamada — la carga se pagina.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.rag.vector_store import get_chroma

logger = logging.getLogger(__name__)

_PAGE_SIZE = 300


@dataclass
class IndiceBM25:
    ids: list[str]
    textos: list[str]
    metadatas: list[dict]
    bm25: BM25Okapi | None  # None si la colección está vacía


_cache: dict[str, IndiceBM25] = {}
_cache_lock = threading.Lock()


def tokenizar(texto: str) -> list[str]:
    """Tokenización multilingüe que preserva códigos técnicos con guión.

    Captura primero patrones tipo PR-01, IT-02, JDAP (letras+guión+dígitos) para
    evitar que BM25 parta 'PR-01' en 'pr' y '01'.
    """
    return re.findall(r"[A-Za-z]{1,6}-\d+|[A-Za-z0-9_À-ž]+", texto.lower())


def get_indice_bm25(coleccion: str) -> IndiceBM25:
    """Devuelve el índice BM25 de la colección, construyéndolo la primera vez.

    Si la colección está vacía, devuelve un índice con `ids=[]` y `bm25=None`;
    el caller debe comprobar `indice.ids` antes de llamar a `bm25.get_scores()`.
    """
    cached = _cache.get(coleccion)
    if cached is not None:
        return cached

    with _cache_lock:
        cached = _cache.get(coleccion)
        if cached is not None:
            return cached

        ids, textos, metadatas = _cargar_paginado(coleccion)

        if not textos:
            indice = IndiceBM25(ids=[], textos=[], metadatas=[], bm25=None)
        else:
            tokens = [tokenizar(_texto_indexable(texto, meta)) for texto, meta in zip(textos, metadatas)]
            indice = IndiceBM25(ids=ids, textos=textos, metadatas=metadatas, bm25=BM25Okapi(tokens))

        _cache[coleccion] = indice
        logger.info("Índice BM25 construido para '%s' (%d docs)", coleccion, len(ids))
        return indice


def invalidar_cache_bm25(coleccion: str | None = None) -> None:
    """Invalida la caché del índice BM25 (toda o de una colección concreta).

    Llamar tras indexar nuevos documentos para que la próxima query reconstruya el índice.
    """
    with _cache_lock:
        if coleccion is None:
            _cache.clear()
        else:
            _cache.pop(coleccion, None)


def _cargar_paginado(coleccion: str) -> tuple[list[str], list[str], list[dict]]:
    col = get_chroma().get_collection(name=coleccion)
    ids: list[str] = []
    textos: list[str] = []
    metadatas: list[dict] = []
    offset = 0
    while True:
        data = col.get(limit=_PAGE_SIZE, offset=offset)
        batch_ids = data.get("ids") or []
        if not batch_ids:
            break
        ids.extend(batch_ids)
        textos.extend(data.get("documents") or [])
        metadatas.extend(data.get("metadatas") or [{} for _ in batch_ids])
        if len(batch_ids) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return ids, textos, metadatas


def _texto_indexable(texto: str, meta: dict | None) -> str:
    """Concatena nombre_fichero + título + sección + texto para enriquecer BM25.

    Incluye el nombre del fichero (sin extensión) para que queries con código
    explícito (PR-02, IT-05) hagan hit directo.
    """
    meta = meta or {}
    partes: list[str] = []
    nombre = meta.get("nombre_fichero", "") or ""
    if nombre:
        partes.append(nombre.replace(".pdf", "").replace("_", " "))
    titulo = meta.get("titulo_documento", "") or ""
    if titulo:
        partes.append(titulo)
    seccion = meta.get("seccion", "") or ""
    if seccion:
        partes.append(seccion)
    partes.append(texto or "")
    return " ".join(partes)
