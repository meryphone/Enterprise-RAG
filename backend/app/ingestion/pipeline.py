"""Ingestion pipeline orchestrator.

Coordinates the four steps described in CLAUDE.md:
    1. Parse the PDF with Docling (parser.py).
    2. Extract document-level metadata from the header (elements.py).
    3. Process each element by type → list of ElementoProcesado (elements.py).
    4. Hierarchical chunking → parents and children with metadata (chunker.py).

Public interface:
    ingestar_pdf(path, metadatos_admin) → DocumentoIngerido
    documento_a_dict(documento)         → dict (JSON-serialisable)
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.ingestion import elements as mod_elements
from app.ingestion import parser as mod_parser
from app.ingestion.chunker import Chunk, chunk_jerarquico
from app.ingestion.elements import MetadatosDocumento


# ---------------------------------------------------------------------------
# Pipeline inputs and outputs
# ---------------------------------------------------------------------------


@dataclass
class MetadatosAdministrador:
    """Metadata supplied by the administrator when uploading the document."""

    empresa: str                          # "intecsa" or client name
    proyecto_id: str | None               # None → global corpus
    tipo_doc: str                         # procedimiento, especificacion, ..., anexo
    idioma: str                           # ISO 639-1: "es", "en", "fr"
    anexo_de: str | None = None           # nombre_fichero of the parent doc when tipo_doc=="anexo"


@dataclass
class DocumentoIngerido:
    doc_id: str
    nombre_fichero: str
    metadatos_admin: MetadatosAdministrador
    metadatos_documento: MetadatosDocumento
    fecha_ingesta: str                    # ISO 8601
    chunks: list[Chunk] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ingestar_pdf(path: Path, metadatos_admin: MetadatosAdministrador) -> DocumentoIngerido:
    """Run the full ingestion pipeline on a PDF and return the result.

    Args:
        path: Path to the PDF file.
        metadatos_admin: Administrator-supplied metadata (company, project, type, language).

    Returns:
        DocumentoIngerido with all chunks ready for indexing in the vector store.
    """
    path = Path(path)

    # 1. Parse with Docling.
    doc = mod_parser.parse_pdf(path)

    # 2. Metadata from the document header (free for digital text).
    #    Extracts title and edition via regex over the first items.
    metadatos_documento = mod_elements.extraer_metadatos_documento(doc)

    # doc_id: always a generated UUID — never extracted from the document.
    doc_id = uuid.uuid4().hex

    # 3. Per-element type processing.
    es_anexo = metadatos_admin.tipo_doc == "anexo"
    elementos = mod_elements.procesar_documento(doc, es_anexo_documento=es_anexo)

    # 4. Hierarchical chunking.
    chunks = chunk_jerarquico(elementos)

    return DocumentoIngerido(
        doc_id=doc_id,
        nombre_fichero=path.name,
        metadatos_admin=metadatos_admin,
        metadatos_documento=metadatos_documento,
        fecha_ingesta=datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        chunks=chunks,
    )


def documento_a_dict(documento: DocumentoIngerido) -> dict:
    """Serialise a DocumentoIngerido to a JSON-compatible dict.

    Used by ingestion scripts to persist parsed output for inspection.
    """
    return {
        "doc_id": documento.doc_id,
        "nombre_fichero": documento.nombre_fichero,
        "metadatos_admin": asdict(documento.metadatos_admin),
        "metadatos_documento": asdict(documento.metadatos_documento),
        "fecha_ingesta": documento.fecha_ingesta,
        "chunks": [asdict(c) for c in documento.chunks],
    }
