"""Orquestador del pipeline de ingesta.

Coordina los cuatro pasos descritos en CLAUDE.md:
    1. Parseo del PDF con Docling (parser.py).
    2. Extracción de metadatos de cabecera (elements.py).
    3. Procesado por tipo de elemento → list[ElementoProcesado] (elements.py).
    4. Chunking jerárquico → parents y children con metadatos (chunker.py).

Interfaz pública:
    ingestar_pdf(path, metadatos_admin) → DocumentoIngerido
    documento_a_dict(documento)         → dict (serializable a JSON)
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.ingestion import elements as mod_elements
from app.ingestion import parser as mod_parser
from app.ingestion.chunker import Chunk, chunk_jerarquico
from app.ingestion.elements import MetadatosDocumento

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entradas y salidas del pipeline
# ---------------------------------------------------------------------------


@dataclass
class MetadatosAdministrador:
    """Metadatos que aporta el administrador al subir el documento."""

    empresa: str                          # "intecsa" o nombre del cliente
    proyecto_id: str | None               # None → corpus global
    tipo_doc: str                         # procedimiento, especificacion, ..., anexo
    idioma: str                           # ISO 639-1: "es", "en", "fr"
    anexo_de: str | None = None           # nombre_fichero del doc padre cuando tipo_doc=="anexo"


@dataclass
class DocumentoIngerido:
    doc_id: str
    nombre_fichero: str
    metadatos_admin: MetadatosAdministrador
    metadatos_documento: MetadatosDocumento
    fecha_ingesta: str                    # ISO 8601
    chunks: list[Chunk] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper de ejecución por paso (timing + manejo de errores uniforme)
# ---------------------------------------------------------------------------


def _ejecutar_paso(
    num: int,
    nombre_archivo: str,
    label: str,
    fn: Callable[..., Any],
    *args: Any,
) -> tuple[Any, float]:
    """Ejecuta un paso del pipeline midiendo tiempo y propagando errores con log."""
    t0 = time.perf_counter()
    try:
        resultado = fn(*args)
    except Exception:
        logger.exception("[%s] paso %d/4 %s: falló", nombre_archivo, num, label)
        raise
    return resultado, time.perf_counter() - t0


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def ingestar_pdf(path: Path, metadatos_admin: MetadatosAdministrador) -> DocumentoIngerido:
    """Ejecuta el pipeline completo de ingesta sobre un PDF y devuelve el resultado.

    Args:
        path: Ruta al fichero PDF.
        metadatos_admin: Metadatos aportados por el administrador (empresa, proyecto, tipo, idioma).

    Returns:
        DocumentoIngerido con todos los chunks listos para indexar en el vector store.
    """
    path = Path(path)
    nombre = path.name

    doc, dt = _ejecutar_paso(1, nombre, "parse", mod_parser.parse_pdf, path)
    logger.info("[%s] paso 1/4 parse (%.1f s)", nombre, dt)

    metadatos_documento, dt = _ejecutar_paso(
        2, nombre, "metadata", mod_elements.extraer_metadatos_documento, doc,
    )
    logger.info(
        "[%s] paso 2/4 metadata (%.2f s) titulo=%r",
        nombre, dt, metadatos_documento.titulo,
    )

    es_anexo = metadatos_admin.tipo_doc == "anexo"
    elementos, dt = _ejecutar_paso(
        3, nombre, "elements", mod_elements.procesar_documento, doc, es_anexo,
    )
    logger.info("[%s] paso 3/4 elements (%.2f s) %d elementos", nombre, dt, len(elementos))

    chunks, dt = _ejecutar_paso(4, nombre, "chunks", chunk_jerarquico, elementos)
    children = sum(1 for c in chunks if c.nivel == "child")
    parents = sum(1 for c in chunks if c.nivel == "parent")
    logger.info(
        "[%s] paso 4/4 chunks (%.2f s) %d children %d parents",
        nombre, dt, children, parents,
    )

    return DocumentoIngerido(
        doc_id=uuid.uuid4().hex,
        nombre_fichero=path.name,
        metadatos_admin=metadatos_admin,
        metadatos_documento=metadatos_documento,
        fecha_ingesta=datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        chunks=chunks,
    )


def documento_a_dict(documento: DocumentoIngerido) -> dict:
    """Serializa un DocumentoIngerido a dict compatible con JSON."""
    return asdict(documento)
