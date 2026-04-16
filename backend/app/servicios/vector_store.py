"""Capa de abstracción del vector store.

Dev local  → ChromaDB cloud.
Producción → Azure AI Search.

El código de negocio (pipeline, retrieval) importa solo este módulo — nunca
sabe qué backend está corriendo. Cambiar de Chroma a Azure es cambiar la
implementación aquí sin tocar nada más.

Estrategia de almacenamiento (ChromaDB):
- Colección `{nombre}`           → child chunks con embeddings (se buscan).
- Colección `{nombre}__parents`  → parent chunks sin embeddings (se recuperan
                                   por ID para expandir el contexto al LLM).
- Las tablas (parent_id=None) se almacenan solo en la colección principal.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import chromadb
from openai import OpenAI

from app.config import SETTINGS

if TYPE_CHECKING:
    from app.procesamiento.pipeline import DocumentoIngerido

logger = logging.getLogger(__name__)

# Dimensionalidad fija de text-embedding-3-small.
_EMBEDDING_DIM = 1536
# Tamaño de lote para las llamadas a la API de embeddings.
_BATCH_SIZE = 100


# ---------------------------------------------------------------------------
# Cliente ChromaDB (singleton por proceso)
# ---------------------------------------------------------------------------

_chroma_client: chromadb.CloudClient | None = None


def _get_chroma() -> chromadb.CloudClient:
    global _chroma_client
    if _chroma_client is None:
        if not SETTINGS.chroma_api_key or not SETTINGS.chroma_tenant:
            raise RuntimeError(
                "CHROMA_API_KEY y CHROMA_TENANT son obligatorios. "
                "Comprueba el fichero .env."
            )
        _chroma_client = chromadb.CloudClient(
            tenant=SETTINGS.chroma_tenant,
            database=SETTINGS.chroma_database,
            api_key=SETTINGS.chroma_api_key,
        )
    return _chroma_client


# ---------------------------------------------------------------------------
# Utilidades de nombres de colección
# ---------------------------------------------------------------------------


def nombre_coleccion(empresa: str, proyecto_id: str | None) -> str:
    """Devuelve el nombre de la colección ChromaDB para un documento.

    - Corpus global Intecsa → "intecsa"
    - Corpus por proyecto   → "{proyecto_id}_{empresa}"
    """
    if proyecto_id is None:
        return empresa.lower()
    return f"{proyecto_id}_{empresa.lower()}"


def _coleccion_parents(nombre: str) -> str:
    return f"{nombre}__parents"


# ---------------------------------------------------------------------------
# Generación de embeddings en lotes
# ---------------------------------------------------------------------------


def _generar_embeddings(textos: list[str]) -> list[list[float]]:
    """Llama a OpenAI en lotes y devuelve los embeddings en el mismo orden."""
    if not textos:
        return []
    if not SETTINGS.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada.")

    client = OpenAI(api_key=SETTINGS.openai_api_key)
    embeddings: list[list[float]] = []

    for i in range(0, len(textos), _BATCH_SIZE):
        lote = textos[i : i + _BATCH_SIZE]
        resp = client.embeddings.create(
            input=lote,
            model=SETTINGS.embedding_model,
        )
        embeddings.extend(e.embedding for e in resp.data)

    return embeddings


# ---------------------------------------------------------------------------
# Serialización de metadatos (ChromaDB solo admite str/int/float/bool)
# ---------------------------------------------------------------------------


def _meta_chunk(chunk, documento: "DocumentoIngerido") -> dict:
    """Construye el dict de metadatos plano para un chunk."""
    return {
        # Identificación del documento
        "doc_id": documento.doc_id,
        "nombre_fichero": documento.nombre_fichero,
        "titulo_documento": documento.metadatos_portada.titulo_documento or "",
        "version": documento.metadatos_portada.edicion or "",
        "fecha_edicion": documento.metadatos_portada.fecha_edicion or "",
        "fecha_ingesta": documento.fecha_ingesta,
        # Metadatos del administrador
        "empresa": documento.metadatos_admin.empresa,
        "proyecto_id": documento.metadatos_admin.proyecto_id or "",
        "tipo_doc": documento.metadatos_admin.tipo_doc,
        "idioma": documento.metadatos_admin.idioma,
        "anexo_de": documento.metadatos_admin.anexo_de or "",
        # Metadatos del chunk
        "nivel": chunk.nivel,
        "parent_id": chunk.parent_id or "",
        "pagina_inicio": chunk.pagina_inicio if chunk.pagina_inicio is not None else -1,
        "pagina_fin": chunk.pagina_fin if chunk.pagina_fin is not None else -1,
        "seccion": chunk.seccion or "",
        # Tipos de elemento como cadena separada por comas
        "tipos_elemento": ",".join(chunk.tipos_elemento),
        # Flags booleanos
        "es_imagen": chunk.es_imagen,
        "dentro_de_anexo": chunk.dentro_de_anexo,
        "tabla_degradada": chunk.tabla_degradada,
    }


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def indexar_documento(documento: "DocumentoIngerido") -> dict[str, int]:
    """Indexa todos los chunks del documento en ChromaDB.

    Devuelve un dict con el recuento de chunks indexados:
        {"children": N, "parents": M}
    """
    from app.procesamiento.pipeline import DocumentoIngerido  # evitar circular

    chroma = _get_chroma()
    col_nombre = nombre_coleccion(
        documento.metadatos_admin.empresa,
        documento.metadatos_admin.proyecto_id,
    )

    children = [c for c in documento.chunks if c.nivel == "child"]
    parents = [c for c in documento.chunks if c.nivel == "parent"]

    # ── Indexar children con embeddings ────────────────────────────────────
    if children:
        col_children = chroma.get_or_create_collection(
            name=col_nombre,
            metadata={"hnsw:space": "cosine"},
        )

        textos = [c.texto for c in children]
        embeddings = _generar_embeddings(textos)

        col_children.upsert(
            ids=[c.chunk_id for c in children],
            documents=textos,
            embeddings=embeddings,
            metadatas=[_meta_chunk(c, documento) for c in children],
        )
        logger.info(
            "Indexados %d children en colección '%s'", len(children), col_nombre
        )

    # ── Almacenar parents (sin embeddings — solo para recuperación por ID) ─
    if parents:
        col_parents = chroma.get_or_create_collection(
            name=_coleccion_parents(col_nombre),
        )

        col_parents.upsert(
            ids=[c.chunk_id for c in parents],
            documents=[c.texto for c in parents],
            metadatas=[_meta_chunk(c, documento) for c in parents],
        )
        logger.info(
            "Almacenados %d parents en colección '%s'",
            len(parents),
            _coleccion_parents(col_nombre),
        )

    return {"children": len(children), "parents": len(parents)}


def precrear_colecciones(nombres: list[str]) -> None:
    """Crea las colecciones children + parents si no existen.

    Útil para que el Query Router pueda listar todos los scopes disponibles
    desde el primer momento, aunque aún no tengan documentos indexados.
    """
    chroma = _get_chroma()
    for nombre in nombres:
        chroma.get_or_create_collection(
            name=nombre,
            metadata={"hnsw:space": "cosine"},
        )
        chroma.get_or_create_collection(name=_coleccion_parents(nombre))
        logger.info("Colección '%s' (+ __parents) lista", nombre)


def colecciones_disponibles() -> list[str]:
    """Lista las colecciones de children (excluye colecciones __parents)."""
    chroma = _get_chroma()
    cols = chroma.list_collections()
    return [c.name for c in cols if not c.name.endswith("__parents")]
