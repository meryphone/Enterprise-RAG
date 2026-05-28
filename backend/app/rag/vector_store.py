"""Capa de abstracción del vector store.

Dev local  → ChromaDB Cloud.
Producción → Azure AI Search (cambiar la implementación solo aquí).

La lógica de negocio (pipeline de ingesta, retrieval) importa este módulo en
exclusiva y nunca referencia el cliente subyacente directamente.

Estrategia de almacenamiento (ChromaDB):
- Colección ``{name}``           → chunks child con embeddings (sobre los que se busca).
- Colección ``{name}__parents``  → chunks parent sin embeddings (se recuperan por ID
                                   para expandir el contexto antes de la generación).
- Las tablas (parent_id=None/vacío) se almacenan solo en la colección principal.

El texto que se embebe es distinto del texto almacenado. El embedding incluye
prefijos de contexto del documento (tipo, código, título, sección) para anclar
semánticamente el chunk. El texto almacenado es el texto bruto del chunk que
leerá el LLM.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import chromadb
from openai import OpenAI

from app.config import SETTINGS

if TYPE_CHECKING:
    from app.ingestion.pipeline import DocumentoIngerido

logger = logging.getLogger(__name__)

_EMBEDDING_DIM = 3072       # text-embedding-3-large
_BATCH_SIZE = 100           # tamaño de lote para la API de embeddings
_MIN_PALABRAS_ORPHAN = 15   # mínimo de palabras para indexar un parent huérfano con embedding


# ---------------------------------------------------------------------------
# Cliente ChromaDB (singleton por proceso)
# ---------------------------------------------------------------------------

_chroma_client: chromadb.CloudClient | None = None


def get_chroma() -> chromadb.CloudClient:
    """Cliente ChromaDB compartido (singleton)."""
    global _chroma_client
    if _chroma_client is None:
        if not SETTINGS.chroma_api_key or not SETTINGS.chroma_tenant:
            raise RuntimeError(
                "CHROMA_API_KEY y CHROMA_TENANT son obligatorios. Comprueba el fichero .env."
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
    """``"intecsa"`` para corpus global, ``"{proyecto_id}_{empresa}"`` para proyectos."""
    if proyecto_id is None:
        return empresa.lower()
    return f"{proyecto_id}_{empresa.lower()}"


def coleccion_parents(nombre: str) -> str:
    """Nombre de la colección de parents asociada a una colección de children."""
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
        resp = client.embeddings.create(input=lote, model=SETTINGS.embedding_model)
        embeddings.extend(e.embedding for e in resp.data)
    return embeddings


# ---------------------------------------------------------------------------
# Serialización de metadatos (ChromaDB solo admite str/int/float/bool)
# ---------------------------------------------------------------------------


def _meta_chunk(chunk, documento: "DocumentoIngerido") -> dict:
    """Aplana los metadatos de un chunk a tipos escalares aceptados por ChromaDB."""
    meta_doc = documento.metadatos_documento
    meta_admin = documento.metadatos_admin
    return {
        # Documento
        "doc_id": documento.doc_id,
        "nombre_fichero": documento.nombre_fichero,
        "titulo_documento": meta_doc.titulo or "",
        "version": meta_doc.edicion or "",
        "fecha_emision": meta_doc.fecha_emision or "",
        "fecha_ingesta": documento.fecha_ingesta,
        # Administrador
        "empresa": meta_admin.empresa,
        "proyecto_id": meta_admin.proyecto_id or "",
        "tipo_doc": meta_admin.tipo_doc,
        "idioma": meta_admin.idioma,
        "anexo_de": meta_admin.anexo_de or "",
        # Chunk
        "nivel": chunk.nivel,
        "parent_id": chunk.parent_id or "",
        "pagina_inicio": chunk.pagina_inicio if chunk.pagina_inicio is not None else -1,
        "pagina_fin": chunk.pagina_fin if chunk.pagina_fin is not None else -1,
        "seccion": chunk.seccion or "",
        "es_imagen": chunk.es_imagen,
        "dentro_de_anexo": chunk.dentro_de_anexo,
    }


def _texto_para_embedding(chunk, documento: "DocumentoIngerido") -> str:
    """Concatena tipo_doc · nombre_fichero · título · sección · texto para el embedding."""
    partes: list[str] = []
    if tipo := (documento.metadatos_admin.tipo_doc or ""):
        partes.append(tipo)
    if documento.nombre_fichero:
        partes.append(documento.nombre_fichero)
    if titulo := (documento.metadatos_documento.titulo or ""):
        partes.append(titulo)
    if chunk.seccion:
        partes.append(chunk.seccion)
    partes.append(chunk.texto)
    return "\n\n".join(partes)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def indexar_documento(documento: "DocumentoIngerido") -> dict[str, int]:
    """Indexa todos los chunks de un documento en ChromaDB.

    - Children → colección principal con embeddings.
    - Parents → colección ``__parents`` sin embeddings (recuperación por ID).
    - Parents huérfanos (sin children porque el texto era demasiado corto) →
      colección principal con embeddings, ``parent_id=""`` para que no se intente expandir.

    Returns:
        ``{"children": int, "parents": int}`` con los conteos efectivamente indexados.
    """
    chroma = get_chroma()
    col_nombre = nombre_coleccion(documento.metadatos_admin.empresa, documento.metadatos_admin.proyecto_id)

    children = [c for c in documento.chunks if c.nivel == "child"]
    parents = [c for c in documento.chunks if c.nivel == "parent"]

    child_parent_ids = {c.parent_id for c in children if c.parent_id}
    orphan_parents = [
        p for p in parents
        if p.chunk_id not in child_parent_ids
        and len(p.texto.split()) >= _MIN_PALABRAS_ORPHAN
    ]

    # ── Children + parents huérfanos (con embeddings) ──────────────────────
    a_indexar = children + orphan_parents
    if a_indexar:
        col_children = chroma.get_or_create_collection(
            name=col_nombre,
            metadata={"hnsw:space": "cosine"},
        )
        textos_embed = [_texto_para_embedding(c, documento) for c in a_indexar]
        try:
            embeddings = _generar_embeddings(textos_embed)
            col_children.upsert(
                ids=[c.chunk_id for c in a_indexar],
                documents=[c.texto for c in a_indexar],
                embeddings=embeddings,
                metadatas=[_meta_chunk(c, documento) for c in a_indexar],
            )
        except Exception:
            logger.exception("Fallo indexando children en colección '%s'", col_nombre)
            raise
        logger.info(
            "Indexados %d chunks (%d children + %d orphan parents) en '%s'",
            len(a_indexar), len(children), len(orphan_parents), col_nombre,
        )

    # ── Parents (sin embeddings) ───────────────────────────────────────────
    if parents:
        col_parents_nombre = coleccion_parents(col_nombre)
        col_parents = chroma.get_or_create_collection(name=col_parents_nombre)
        try:
            col_parents.upsert(
                ids=[c.chunk_id for c in parents],
                documents=[c.texto for c in parents],
                metadatas=[_meta_chunk(c, documento) for c in parents],
            )
        except Exception:
            logger.exception("Fallo almacenando parents en colección '%s'", col_parents_nombre)
            raise
        logger.info("Almacenados %d parents en colección '%s'", len(parents), col_parents_nombre)

    return {"children": len(a_indexar), "parents": len(parents)}


def precrear_colecciones(nombres: list[str]) -> None:
    """Crea las colecciones children + parents si no existen.

    Útil para que el Query Router pueda listar todos los scopes desde el primer
    momento, aunque aún no tengan documentos indexados.
    """
    chroma = get_chroma()
    for nombre in nombres:
        chroma.get_or_create_collection(name=nombre, metadata={"hnsw:space": "cosine"})
        chroma.get_or_create_collection(name=coleccion_parents(nombre))
        logger.info("Colección '%s' (+ __parents) lista", nombre)


def colecciones_disponibles() -> list[str]:
    """Nombres de colecciones de ChromaDB filtrando las ``__parents`` (detalle interno)."""
    cols = get_chroma().list_collections()
    return [c.name for c in cols if not c.name.endswith("__parents")]
