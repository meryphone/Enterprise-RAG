"""Pipeline de retrieval híbrido con rerank de Cohere.

Pipeline:
    1. Reescritura dual de la query (`query_rewriter`).
    2. Búsqueda vectorial densa (ChromaDB, coseno).
    3. Búsqueda BM25 dispersa (`bm25_index`, en memoria).
    4. Fusión ponderada de scores normalizados (min-max).
    5. Rerank con Cohere sobre los top-K → top-N final.
    6. Recuperación de hermanos de tabla descartados por Cohere.

API pública: `recuperar(query, proyecto_id, empresa, ...)`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import cohere
from openai import OpenAI

from app.config import SETTINGS
from app.rag.bm25_index import (
    get_indice_bm25,
    invalidar_cache_bm25,  # re-export para main.py
    tokenizar,
)
from app.rag.query_rewriter import reescribir_query
from app.rag.vector_store import get_chroma, nombre_coleccion

__all__ = ["ChunkRecuperado", "recuperar", "invalidar_cache_bm25"]

logger = logging.getLogger(__name__)


@dataclass
class ChunkRecuperado:
    """Resultado final del pipeline de retrieval."""

    chunk_id: str
    texto: str
    metadatos: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0                  # score final (tras rerank)
    score_vector: float | None = None   # similitud vectorial normalizada
    score_bm25: float | None = None     # score BM25 normalizado
    score_fusion: float | None = None   # fusión ponderada pre-rerank


def recuperar(
    query: str,
    proyecto_id: str | None,
    empresa: str = "intecsa",
    top_k: int | None = None,
    top_n: int | None = None,
    peso_vector: float | None = None,
    peso_bm25: float | None = None,
) -> list[ChunkRecuperado]:
    """Recupera los chunks más relevantes para una query dentro del scope dado.

    Returns:
        Lista de ChunkRecuperado ordenada por relevancia descendente de Cohere.
    """
    top_k = top_k if top_k is not None else SETTINGS.retrieval_top_k
    top_n = top_n if top_n is not None else SETTINGS.retrieval_top_n
    peso_vector = peso_vector if peso_vector is not None else SETTINGS.retrieval_peso_vector
    peso_bm25 = peso_bm25 if peso_bm25 is not None else SETTINGS.retrieval_peso_bm25

    coleccion = nombre_coleccion(empresa, proyecto_id)
    query_vector, query_bm25 = reescribir_query(query)

    # ── 1. Recuperación dual ────────────────────────────────────────────
    cache_docs, scores_vec_por_id = _buscar_vectorial(coleccion, query_vector, top_k)
    scores_bm25_por_id = _buscar_bm25(coleccion, query_bm25, top_k, cache_docs)

    # ── 2. Fusión de scores ─────────────────────────────────────────────
    fusion = _fusionar_scores(scores_vec_por_id, scores_bm25_por_id, peso_vector, peso_bm25)[:top_k]
    if not fusion:
        return []

    # ── 3. Rerank con Cohere ────────────────────────────────────────────
    resultados = _rerank_cohere(query, fusion, cache_docs, top_n)

    # ── 4. Recuperar hermanos de tabla descartados por Cohere ───────────
    resultados.extend(_recuperar_partes_tabla_huerfanas(resultados, fusion, cache_docs))

    logger.info("recuperar(q=%r, scope=%s) → %d chunks", query[:60], coleccion, len(resultados))
    return resultados


# ---------------------------------------------------------------------------
# Etapas internas
# ---------------------------------------------------------------------------


def _buscar_vectorial(
    coleccion: str,
    query_vector: str,
    top_k: int,
) -> tuple[dict[str, tuple[str, dict]], dict[str, float]]:
    """Búsqueda densa. Devuelve (cache_docs, scores_normalizados_por_id)."""
    col = get_chroma().get_collection(name=coleccion)
    emb = _embedding_query(query_vector)
    res = col.query(query_embeddings=[emb], n_results=top_k)

    ids = res["ids"][0] if res["ids"] else []
    docs = res["documents"][0] if res["documents"] else []
    metas = res["metadatas"][0] if res["metadatas"] else []
    # distancia coseno en [0, 2] → similitud en [-1, 1]
    scores = [1.0 - d for d in (res["distances"][0] if res["distances"] else [])]

    cache_docs = {cid: (doc, meta or {}) for cid, doc, meta in zip(ids, docs, metas)}
    return cache_docs, dict(zip(ids, _minmax(scores)))


def _buscar_bm25(
    coleccion: str,
    query_bm25: str,
    top_k: int,
    cache_docs: dict[str, tuple[str, dict]],
) -> dict[str, float]:
    """Búsqueda BM25. Añade documentos al cache si no estaban."""
    indice = get_indice_bm25(coleccion)
    if not indice.ids:
        return {}

    puntuaciones = indice.bm25.get_scores(tokenizar(query_bm25))
    top = sorted(enumerate(puntuaciones), key=lambda x: x[1], reverse=True)[:top_k]

    for pos, _ in top:
        cid = indice.ids[pos]
        if cid not in cache_docs:
            cache_docs[cid] = (indice.textos[pos], indice.metadatas[pos] or {})

    ids_top = [indice.ids[pos] for pos, _ in top]
    scores_top = [s for _, s in top]
    return dict(zip(ids_top, _minmax(scores_top)))


def _fusionar_scores(
    scores_vec: dict[str, float],
    scores_bm25: dict[str, float],
    peso_vector: float,
    peso_bm25: float,
) -> list[tuple[str, float, float | None, float | None]]:
    """Combina scores normalizados; devuelve lista (cid, score_fusion, sv, sb) ordenada."""
    fusion = []
    for cid in set(scores_vec) | set(scores_bm25):
        sv = scores_vec.get(cid)
        sb = scores_bm25.get(cid)
        score = peso_vector * (sv or 0.0) + peso_bm25 * (sb or 0.0)
        fusion.append((cid, score, sv, sb))
    fusion.sort(key=lambda x: -x[1])
    return fusion


def _rerank_cohere(
    query: str,
    fusion: list[tuple[str, float, float | None, float | None]],
    cache_docs: dict[str, tuple[str, dict]],
    top_n: int,
) -> list[ChunkRecuperado]:
    """Rerank con la query original. Prefija cada chunk con doc/sección para dar contexto."""
    if not SETTINGS.cohere_api_key:
        raise RuntimeError("COHERE_API_KEY no configurada.")

    textos_rerank = [_texto_para_rerank(cid, cache_docs) for cid, *_ in fusion]
    co = cohere.Client(api_key=SETTINGS.cohere_api_key)
    resp = co.rerank(
        model=SETTINGS.cohere_rerank_model,
        query=query,
        documents=textos_rerank,
        top_n=min(top_n, len(textos_rerank)),
    )

    resultados: list[ChunkRecuperado] = []
    for r in resp.results:
        cid, score_fusion, sv, sb = fusion[r.index]
        texto, meta = cache_docs[cid]
        resultados.append(ChunkRecuperado(
            chunk_id=cid, texto=texto, metadatos=meta,
            score=r.relevance_score, score_vector=sv, score_bm25=sb, score_fusion=score_fusion,
        ))
    return resultados


def _recuperar_partes_tabla_huerfanas(
    resultados: list[ChunkRecuperado],
    fusion: list[tuple[str, float, float | None, float | None]],
    cache_docs: dict[str, tuple[str, dict]],
) -> list[ChunkRecuperado]:
    """Si Cohere seleccionó un chunk de tabla, recupera sus hermanos del mismo doc+sección.

    El chunker parte tablas grandes en varias piezas. Cohere puede quedarse solo con una;
    aquí recuperamos el resto para que `fusionar_partes_tabla` reconstruya la tabla completa.
    """
    ids_seleccionados = {r.chunk_id for r in resultados}
    tablas_seleccionadas: set[str] = set()
    for r in resultados:
        if r.texto.strip().startswith("|"):
            nombre = (r.metadatos or {}).get("nombre_fichero", "")
            seccion = (r.metadatos or {}).get("seccion", "")
            if nombre and seccion:
                tablas_seleccionadas.add(f"{nombre}||{seccion}")

    if not tablas_seleccionadas:
        return []

    huerfanas: list[ChunkRecuperado] = []
    for cid, score_fusion, sv, sb in fusion:
        if cid in ids_seleccionados:
            continue
        texto, meta = cache_docs.get(cid, ("", {}))
        if not texto.strip().startswith("|"):
            continue
        nombre = (meta or {}).get("nombre_fichero", "")
        seccion = (meta or {}).get("seccion", "")
        if f"{nombre}||{seccion}" in tablas_seleccionadas:
            huerfanas.append(ChunkRecuperado(
                chunk_id=cid, texto=texto, metadatos=meta,
                score=0.0, score_vector=sv, score_bm25=sb, score_fusion=score_fusion,
            ))
            logger.debug("Parte de tabla añadida post-rerank: %s § %s", nombre, seccion)
    return huerfanas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _embedding_query(texto: str) -> list[float]:
    if not SETTINGS.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada.")
    client = OpenAI(api_key=SETTINGS.openai_api_key)
    resp = client.embeddings.create(input=[texto], model=SETTINGS.embedding_model)
    return resp.data[0].embedding


def _minmax(scores: list[float]) -> list[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi == lo:
        return [1.0] * len(scores)
    return [(s - lo) / (hi - lo) for s in scores]


def _texto_para_rerank(cid: str, cache_docs: dict[str, tuple[str, dict]]) -> str:
    """Prefija cada chunk con [doc — sección] para dar contexto al reranker.

    Crítico para tablas: su contenido bruto (pipes y nombres de columnas) no revela
    de qué tratan sin encabezado.
    """
    texto, meta = cache_docs[cid]
    doc = (meta or {}).get("nombre_fichero", "").removesuffix(".pdf")
    seccion = (meta or {}).get("seccion", "") or ""
    partes = [p for p in (doc, seccion) if p]
    prefix = f"[{' — '.join(partes)}]\n" if partes else ""
    return f"{prefix}{texto}"
