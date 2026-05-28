"""Reescritura dual de la query para retrieval híbrido.

Produce dos variantes con GPT-4o-mini:
- **VECTOR**: reformulación semántica bilingüe (ES + EN) para embeddings densos.
- **BM25**: bolsa de palabras con sinónimos y traducciones para búsqueda léxica.

El rerank de Cohere usa siempre la query original para máxima fidelidad.
Si la API falla o `ENABLE_QUERY_REWRITING=0`, se devuelve la query original.
"""
from __future__ import annotations

import logging

from openai import OpenAI

from app.config import SETTINGS
from app.ingestion.prompts import PROMPT_REESCRITURA_QUERY

logger = logging.getLogger(__name__)


def reescribir_query(query: str) -> tuple[str, str]:
    """Devuelve (query_vector, query_bm25). Cae a la query original ante errores."""
    if not SETTINGS.enable_query_rewriting:
        logger.info("Query rewriting deshabilitado (ENABLE_QUERY_REWRITING=0)")
        return query, query

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
    except Exception as e:
        logger.warning("Query rewriting falló, usando query original: %s", e)
        return query, query

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
