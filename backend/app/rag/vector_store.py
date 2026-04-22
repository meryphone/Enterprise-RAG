"""Vector store abstraction layer.

Dev local  → ChromaDB Cloud.
Production → Azure AI Search (swap implementation here only).

Business logic (ingestion pipeline, retrieval) imports this module exclusively
and never references the underlying client directly.

Storage strategy (ChromaDB):
- Collection ``{name}``           → child chunks with embeddings (searched).
- Collection ``{name}__parents``  → parent chunks without embeddings (fetched by ID
                                    to expand context before generation).
- Tables (parent_id=None/empty) are stored only in the main collection.

Embedding text differs from stored text. The embedding includes document-level
context prefixes (type, code, title, section) to anchor the chunk semantically.
The stored text is the raw chunk text that the LLM will read.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.ingestion.pipeline import DocumentoIngerido  

import chromadb
from openai import OpenAI

from app.config import SETTINGS

if TYPE_CHECKING:
    from app.ingestion.pipeline import DocumentoIngerido

logger = logging.getLogger(__name__)

# Dimensionality for text-embedding-3-large.
_EMBEDDING_DIM = 3072
# Batch size for embedding API calls.
_BATCH_SIZE = 100


# ---------------------------------------------------------------------------
# Cliente ChromaDB (singleton por proceso)
# ---------------------------------------------------------------------------

_chroma_client: chromadb.CloudClient | None = None


def get_chroma() -> chromadb.CloudClient:
    """Shared ChromaDB client (singleton). Exposed for other services."""
    return _get_chroma()


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
    """Return the ChromaDB collection name for a given scope.

    Args:
        empresa: Company identifier (e.g. ``"intecsa"``).
        proyecto_id: Project code, or None for the global corporate corpus.

    Returns:
        ``"intecsa"`` for the global corpus, ``"{proyecto_id}_{empresa}"`` for projects.
    """
    if proyecto_id is None:
        return empresa.lower()
    return f"{proyecto_id}_{empresa.lower()}"


def coleccion_parents(nombre: str) -> str:
    """Nombre de la colección de parents asociada a una colección de children."""
    return f"{nombre}__parents"


def _coleccion_parents(nombre: str) -> str:
    return coleccion_parents(nombre)


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
        "titulo_documento": documento.metadatos_documento.titulo or "",
        "version": documento.metadatos_documento.edicion or "",
        "fecha_emision": documento.metadatos_documento.fecha_emision or "",
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
    """Index all chunks of a document into ChromaDB.

    Children are embedded and stored in the main collection.
    Parents are stored without embeddings in the ``__parents`` collection.
    Orphan parents (no children generated, parent_id="") are embedded and
    stored in the main collection directly.

    Args:
        documento: Fully-ingested document with chunks.

    Returns:
        Dict with keys ``"children"`` and ``"parents"`` showing counts added.
    """

    chroma = _get_chroma()
    col_nombre = nombre_coleccion(
        documento.metadatos_admin.empresa,
        documento.metadatos_admin.proyecto_id,
    )

    children = [c for c in documento.chunks if c.nivel == "child"]
    parents = [c for c in documento.chunks if c.nivel == "parent"]

    # Parents sin hijos: el chunker no pudo subdividirlos (texto demasiado corto).
    # Se indexan en la colección de children con embeddings para que sean recuperables
    # por búsqueda semántica. Su parent_id es "" (como las tablas), así el orquestador
    # los pasa directamente al LLM sin intentar expansión.
    # Mínimo de palabras para que el embedding sea útil: textos más cortos producen
    # representaciones vectoriales de baja calidad que contaminan el retrieval.
    _MIN_PALABRAS_ORPHAN = 15
    child_parent_ids = {c.parent_id for c in children if c.parent_id}
    orphan_parents = [
        p for p in parents
        if p.chunk_id not in child_parent_ids
        and len(p.texto.split()) >= _MIN_PALABRAS_ORPHAN
    ]

    # Conjunto efectivo a indexar con embeddings: children + parents huérfanos
    a_indexar = children + orphan_parents

    # ── Indexar children (+ orphan parents) con embeddings ─────────────────
    if a_indexar:
        col_children = chroma.get_or_create_collection(
            name=col_nombre,
            metadata={"hnsw:space": "cosine"},
        )

        textos = [c.texto for c in a_indexar]
        titulo_doc = documento.metadatos_documento.titulo or ""
        tipo_doc_label = documento.metadatos_admin.tipo_doc or ""
        codigo_doc = documento.nombre_fichero.removesuffix(".pdf") if documento.nombre_fichero else ""
        textos_embed = []
        for c in a_indexar:
            partes = []
            if tipo_doc_label:
                partes.append(tipo_doc_label)
            if codigo_doc:
                partes.append(codigo_doc)
            if titulo_doc:
                partes.append(titulo_doc)
            if c.seccion:
                partes.append(c.seccion)
            partes.append(c.texto)
            textos_embed.append("\n\n".join(partes))
        embeddings = _generar_embeddings(textos_embed)

        col_children.upsert(
            ids=[c.chunk_id for c in a_indexar],
            documents=textos,
            embeddings=embeddings,
            metadatas=[_meta_chunk(c, documento) for c in a_indexar],
        )
        logger.info(
            "Indexados %d chunks (%d children + %d orphan parents) en '%s'",
            len(a_indexar), len(children), len(orphan_parents), col_nombre,
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

    return {"children": len(a_indexar), "parents": len(parents)}


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
    """Return names of all non-parent collections in ChromaDB.

    Filters out ``__parents`` collections, which are implementation details
    not visible to the API layer.
    """
    chroma = _get_chroma()
    cols = chroma.list_collections()
    return [c.name for c in cols if not c.name.endswith("__parents")]
