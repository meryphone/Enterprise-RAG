"""Retrieval híbrido + rerank (Fase 1 MVP).

Pipeline:
    1. Búsqueda vectorial (ChromaDB, cosine)          → top-k candidatos.
    2. Búsqueda léxica BM25 (rank-bm25, en memoria)   → top-k candidatos.
    3. Fusión ponderada de scores normalizados (min-max) con los pesos
       `RETRIEVAL_PESO_VECTOR` / `RETRIEVAL_PESO_BM25` del .env.
    4. Filtrado por metadatos: el scope (proyecto_id) determina la colección;
       `tipo_doc` se aplica como filtro opcional.
    5. Reranking con Cohere (`rerank-multilingual-v3.0`) → top-n final.

El código de negocio solo llama a `recuperar()` y recibe `ChunkRecuperado`s
listos para pasar al LLM.

Expansión a parents:
    No se incluye en este módulo. Los `ChunkRecuperado` exponen `parent_id`
    en sus metadatos; el orquestador de `/query` se encargará de recuperar
    los parents por ID cuando arme el contexto para el LLM.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import cohere
from openai import OpenAI
from rank_bm25 import BM25Okapi

from app.config import SETTINGS
from app.ingestion.prompts import PROMPT_REESCRITURA_QUERY
from app.rag.vector_store import get_chroma, nombre_coleccion

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache BM25 por colección (in-memory, lazy)
# ---------------------------------------------------------------------------


@dataclass
class _IndiceBM25:
    ids: list[str]
    textos: list[str]
    metadatas: list[dict]
    bm25: BM25Okapi


_cache_bm25: dict[str, _IndiceBM25] = {}


def _tokenizar(texto: str) -> list[str]:
    """Tokenización multilingüe que preserva códigos técnicos con guión.

    Primero captura patrones tipo PR-01, IT-02, JDAP (letras+guión+dígitos),
    luego palabras normales. Esto evita que BM25 parta 'PR-01' en 'pr' y '01'.
    """
    return re.findall(r"[A-Za-z]{1,6}-\d+|[A-Za-z0-9_\u00C0-\u017E]+", texto.lower())


def _get_indice_bm25(coleccion: str) -> _IndiceBM25:
    """Devuelve el índice BM25 de la colección, construyéndolo la primera vez.

    Se hace singleton por proceso. Si se indexan nuevos documentos en la
    colección después de construir el índice, hay que invalidar con
    `invalidar_cache_bm25(coleccion)`.

    ChromaDB Cloud limita col.get() a 300 items por llamada. Se pagina
    en bloques de 300 hasta cargar todos los chunks.
    """
    if coleccion in _cache_bm25:
        return _cache_bm25[coleccion]

    chroma = get_chroma()
    col = chroma.get_collection(name=coleccion)

    _PAGE = 300
    ids: list[str] = []
    textos: list[str] = []
    metadatas: list[dict] = []
    offset = 0
    while True:
        data = col.get(limit=_PAGE, offset=offset)
        batch_ids = data.get("ids") or []
        if not batch_ids:
            break
        ids.extend(batch_ids)
        textos.extend(data.get("documents") or [])
        metas = data.get("metadatas") or [{} for _ in batch_ids]
        metadatas.extend(metas)
        if len(batch_ids) < _PAGE:
            break
        offset += _PAGE

    if not textos:
        # Colección vacía — devolver índice trivial para evitar errores
        bm25 = BM25Okapi([[""]])
    else:
        tokens = []
        for texto, meta in zip(textos, metadatas):
            partes = []
            # Incluir nombre_fichero (sin extensión) para que queries con
            # código explícito (PR-02, IT-05) hagan hit directo en BM25.
            nombre = (meta or {}).get("nombre_fichero", "") or ""
            if nombre:
                partes.append(nombre.replace(".pdf", "").replace("_", " "))
            titulo = (meta or {}).get("titulo_documento", "") or ""
            seccion = (meta or {}).get("seccion", "") or ""
            if titulo:
                partes.append(titulo)
            if seccion:
                partes.append(seccion)
            partes.append(texto or "")
            tokens.append(_tokenizar(" ".join(partes)))
        bm25 = BM25Okapi(tokens)

    indice = _IndiceBM25(ids=ids, textos=textos, metadatas=metadatas, bm25=bm25)
    _cache_bm25[coleccion] = indice
    logger.info("Índice BM25 construido para '%s' (%d docs)", coleccion, len(ids))
    return indice


def invalidar_cache_bm25(coleccion: str | None = None) -> None:
    """Limpia el caché BM25. Llamar tras indexar nuevos documentos."""
    if coleccion is None:
        _cache_bm25.clear()
    else:
        _cache_bm25.pop(coleccion, None)


# ---------------------------------------------------------------------------
# Embeddings de query
# ---------------------------------------------------------------------------


def _embedding_query(texto: str) -> list[float]:
    if not SETTINGS.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada.")
    client = OpenAI(api_key=SETTINGS.openai_api_key)
    resp = client.embeddings.create(input=[texto], model=SETTINGS.embedding_model)
    return resp.data[0].embedding


# ---------------------------------------------------------------------------
# Query rewriting
# ---------------------------------------------------------------------------


def _reescribir_query(query: str) -> tuple[str, str]:
    """Produce dos variantes de la query vía GPT-4o-mini.

    Devuelve (query_vector, query_bm25):
    - query_vector: reformulación semántica para embedding.
    - query_bm25: bolsa de palabras con sinónimos para búsqueda léxica.
    Ambas caen back a la query original si la llamada falla o el formato es inesperado.
    """
    try:
        client = OpenAI(api_key=SETTINGS.openai_api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PROMPT_REESCRITURA_QUERY},
                {"role": "user", "content": query},
            ],
            max_tokens=180,
            temperature=0.0,
        )
        texto = resp.choices[0].message.content.strip()
        q_vector = query
        q_bm25 = query
        for line in texto.splitlines():
            if line.startswith("VECTOR:"):
                q_vector = line[len("VECTOR:"):].strip() or query
            elif line.startswith("BM25:"):
                q_bm25 = line[len("BM25:"):].strip() or query
        logger.info("Query vector: %r", q_vector)
        logger.info("Query BM25:   %r", q_bm25)
        return q_vector, q_bm25
    except Exception as e:
        logger.warning("Query rewriting falló, usando query original: %s", e)
    return query, query


# ---------------------------------------------------------------------------
# Normalización de scores
# ---------------------------------------------------------------------------


def _minmax(scores: list[float]) -> list[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi == lo:
        return [1.0] * len(scores)
    return [(s - lo) / (hi - lo) for s in scores]


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


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
    tipo_doc: str | None = None,
    top_k: int | None = None,
    top_n: int | None = None,
    peso_vector: float | None = None,
    peso_bm25: float | None = None,
) -> list[ChunkRecuperado]:
    """Recupera los chunks más relevantes para `query` en el scope dado.

    Args:
        query: pregunta del usuario en lenguaje natural.
        proyecto_id: código del proyecto, o `None` para el corpus global Intecsa.
        empresa: nombre de la empresa del scope; por defecto "intecsa".
        tipo_doc: filtro opcional de metadato `tipo_doc`.
        top_k: candidatos tras la fusión híbrida (default del .env).
        top_n: resultados finales tras el rerank (default del .env).
        peso_vector, peso_bm25: pesos de fusión (defaults del .env).

    Returns:
        Lista de `ChunkRecuperado` ordenada por score decreciente (top-n).
    """
    top_k = top_k if top_k is not None else SETTINGS.retrieval_top_k
    top_n = top_n if top_n is not None else SETTINGS.retrieval_top_n
    peso_vector = peso_vector if peso_vector is not None else SETTINGS.retrieval_peso_vector
    peso_bm25 = peso_bm25 if peso_bm25 is not None else SETTINGS.retrieval_peso_bm25

    coleccion = nombre_coleccion(empresa, proyecto_id)
    where = {"tipo_doc": tipo_doc} if tipo_doc else None

    # Vector usa la reformulación semántica; BM25 usa la bolsa de palabras.
    # Rerank usa la query original para máxima fidelidad a la intención.
    query_vector, query_bm25 = _reescribir_query(query)

    chroma = get_chroma()
    col = chroma.get_collection(name=coleccion)

    # ── 1. Búsqueda vectorial (reformulación semántica) ──────────────────
    emb = _embedding_query(query_vector)
    res_vec = col.query(
        query_embeddings=[emb],
        n_results=top_k,
        where=where,
    )
    ids_vec: list[str] = res_vec["ids"][0] if res_vec["ids"] else []
    docs_vec: list[str] = res_vec["documents"][0] if res_vec["documents"] else []
    metas_vec: list[dict] = res_vec["metadatas"][0] if res_vec["metadatas"] else []
    # Pasamos de distancia del coseno en [0, 2] → similitud en [-1, 1] con 1 = idéntico (por estándar)
    scores_vec = [1.0 - d for d in (res_vec["distances"][0] if res_vec["distances"] else [])]

    # ── 2. Búsqueda BM25 ─────────────────────────────────────────────────
    indice = _get_indice_bm25(coleccion)

    def _pasa_filtro(i: int) -> bool:
    # Sin filtro → todos los chunks son válidos
        if not where:
            return True

        # Metadatos del chunk i (diccionario vacío si no tiene)
        metadatos = indice.metadatas[i] or {}

        # El chunk pasa solo si TODOS los campos del filtro coinciden
        for campo, valor_esperado in where.items():
            if metadatos.get(campo) != valor_esperado:
                return False

        return True

    if indice.ids:
        puntuaciones_bm25 = indice.bm25.get_scores(_tokenizar(query_bm25))

        chunks_con_puntuacion = [
            (posicion, puntuaciones_bm25[posicion])
            for posicion in range(len(indice.ids))
            if _pasa_filtro(posicion)
        ]
        chunks_con_puntuacion.sort(key=lambda x: x[1], reverse=True)
        candidatos_bm25 = chunks_con_puntuacion[:top_k]

    else:
        candidatos_bm25 = []

    ids_bm25 = [indice.ids[i] for i, _ in candidatos_bm25]
    scores_bm25 = [s for _, s in candidatos_bm25]

    # ── 3. Fusión de scores normalizados ─────────────────────────────────
    norm_vec = dict(zip(ids_vec, _minmax(scores_vec)))
    norm_bm25 = dict(zip(ids_bm25, _minmax(scores_bm25)))

    # Cacheamos (texto, meta) por id desde ambos retrievers para no re-consultar.
    cache_docs: dict[str, tuple[str, dict]] = {}
    for i, t, m in zip(ids_vec, docs_vec, metas_vec):
        cache_docs[i] = (t, m or {})
    for idx, _ in candidatos_bm25:
        cid = indice.ids[idx]
        if cid not in cache_docs:
            cache_docs[cid] = (indice.textos[idx], indice.metadatas[idx] or {}) # cache_docs: dict[id] = (texto, metadatos)

    fusion = []
    for cid in set(norm_vec) | set(norm_bm25):
        sv = norm_vec.get(cid)
        sb = norm_bm25.get(cid)
        score = peso_vector * (sv or 0.0) + peso_bm25 * (sb or 0.0)
        fusion.append((cid, score, sv, sb))

    fusion.sort(key=lambda x: -x[1])
    fusion = fusion[:top_k] # fusion : list of (chunk_id, score_fusion, score_vector, score_bm25) de los top_k candidatos tras la fusión híbrida

    if not fusion:
        return []

    # ── 4. Rerank con Cohere ─────────────────────────────────────────────
    if not SETTINGS.cohere_api_key:
        raise RuntimeError("COHERE_API_KEY no configurada.")

    # Prefijamos cada chunk con su documento y sección para que Cohere entienda
    # el contexto, especialmente crítico en tablas cuyo contenido bruto (pipes y
    # nombres) no revela de qué tratan sin encabezado.
    def _texto_para_rerank(cid: str) -> str:
        texto, meta = cache_docs[cid]
        doc = (meta or {}).get("nombre_fichero", "").removesuffix(".pdf")
        seccion = (meta or {}).get("seccion", "") or ""
        partes = []
        if doc:
            partes.append(doc)
        if seccion:
            partes.append(seccion)
        prefix = f"[{' — '.join(partes)}]\n" if partes else ""
        return f"{prefix}{texto}"

    textos_rerank = [_texto_para_rerank(cid) for cid, *_ in fusion]

    co = cohere.Client(api_key=SETTINGS.cohere_api_key)
    # Rerank usa la query original para máxima fidelidad a la intención del usuario
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
        resultados.append(
            ChunkRecuperado(
                chunk_id=cid,
                texto=texto,
                metadatos=meta,
                score=r.relevance_score,
                score_vector=sv,
                score_bm25=sb,
                score_fusion=score_fusion,
            )
        )

    # ── 5. Recuperar partes de tabla descartadas por Cohere ──────────────
    # Si Cohere seleccionó un chunk de tabla, incluimos todos sus hermanos
    # del mismo doc+sección aunque no llegaran al top_n. Así _fusionar_partes_tabla
    # en query.py puede reconstruir la tabla completa.
    ids_seleccionados = {r.chunk_id for r in resultados}
    tablas_seleccionadas: set[str] = set()
    for r in resultados:
        meta = r.metadatos or {}
        if r.texto.strip().startswith("|"):
            nombre = meta.get("nombre_fichero", "")
            seccion = meta.get("seccion", "")
            if nombre and seccion:
                tablas_seleccionadas.add(f"{nombre}||{seccion}")

    if tablas_seleccionadas:
        for cid, score_fusion, sv, sb in fusion:
            if cid in ids_seleccionados:
                continue
            texto, meta = cache_docs.get(cid, ("", {}))
            if not texto.strip().startswith("|"):
                continue
            nombre = (meta or {}).get("nombre_fichero", "")
            seccion = (meta or {}).get("seccion", "")
            if f"{nombre}||{seccion}" in tablas_seleccionadas:
                resultados.append(ChunkRecuperado(
                    chunk_id=cid,
                    texto=texto,
                    metadatos=meta,
                    score=0.0,
                    score_vector=sv,
                    score_bm25=sb,
                    score_fusion=score_fusion,
                ))
                logger.debug("Parte de tabla añadida post-rerank: %s § %s", nombre, seccion)

    logger.info(
        "recuperar(q=%r, scope=%s, tipo_doc=%s) → %d chunks",
        query[:60], coleccion, tipo_doc, len(resultados),
    )
    for i, r in enumerate(resultados, 1):
        logger.debug(
            "  [%d] score=%.3f  doc=%s  sec=%s  texto=%r",
            i,
            r.score,
            r.metadatos.get("nombre_fichero", "?"),
            r.metadatos.get("seccion", "?")[:50],
            r.texto[:80],
        )
    return resultados
