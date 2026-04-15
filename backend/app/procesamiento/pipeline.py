"""Orquestador del pipeline de ingesta.

Entrada:
    - ruta al PDF
    - metadatos del administrador (empresa, proyecto_id, tipo_doc, idioma)

Salida:
    - `DocumentoIngerido` con todos los chunks listos para indexar en el
      vector store (paso que aún no hacemos — se hará cuando conectemos Chroma).

Este módulo coordina los pasos descritos en CLAUDE.md → "Flujo general":
    1. Parsear el PDF con Docling.
    2. Extraer título y edición de la cabecera del documento.
    3. Procesar cada elemento según su tipo → lista de `ElementoProcesado`.
    4. Hierarchical chunking → parents y children con sus metadatos.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.procesamiento import elementos as mod_elementos
from app.procesamiento import parser as mod_parser
from app.procesamiento import vision
from app.procesamiento.chunker import Chunk, chunk_jerarquico


# ---------------------------------------------------------------------------
# Inputs y outputs del pipeline
# ---------------------------------------------------------------------------


@dataclass
class MetadatosAdministrador:
    """Metadatos que el administrador aporta al subir el documento."""

    empresa: str                          # "intecsa" o nombre del cliente
    proyecto_id: str | None               # None → corpus global
    tipo_doc: str                         # procedimiento, especificacion, ..., anexo
    idioma: str                           # ISO 639-1: "es", "en", "fr"


@dataclass
class DocumentoIngerido:
    doc_id: str
    nombre_fichero: str
    metadatos_admin: MetadatosAdministrador
    metadatos_portada: vision.MetadatosPortada
    fecha_ingesta: str                    # ISO 8601
    paginas_total: int
    chunks: list[Chunk] = field(default_factory=list)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def ingestar_pdf(path: Path, metadatos_admin: MetadatosAdministrador) -> DocumentoIngerido:
    """Ejecuta el pipeline completo sobre un PDF y devuelve el documento ingerido."""
    path = Path(path)

    # 1. Parseo con Docling.
    doc = mod_parser.parse_pdf(path)

    # 2. Metadatos desde la cabecera del documento (texto digital, gratis).
    #    Extrae título y edición mediante regex sobre los primeros ítems.
    cabecera = mod_elementos.extraer_metadatos_documento(doc)
    metadatos_portada = vision.MetadatosPortada.vacio()
    if cabecera.titulo:
        metadatos_portada.titulo_documento = cabecera.titulo
    if cabecera.edicion:
        metadatos_portada.edicion = cabecera.edicion

    # doc_id: siempre un UUID generado — no se extrae del documento.
    doc_id = uuid.uuid4().hex

    # 3. Procesamiento por tipo de elemento.
    elementos = mod_elementos.procesar_documento(doc)

    # 4. Hierarchical chunking.
    chunks = chunk_jerarquico(elementos)

    # 5. Si el administrador declaró el documento entero como anexo, propagar
    #    dentro_de_anexo=True a todos los chunks. Cubre documentos que son 100%
    #    anexo y no tienen secciones con título ANEXO/APPENDIX/ANNEX.
    if metadatos_admin.tipo_doc == "anexo":
        for chunk in chunks:
            chunk.dentro_de_anexo = True

    return DocumentoIngerido(
        doc_id=doc_id,
        nombre_fichero=path.name,
        metadatos_admin=metadatos_admin,
        metadatos_portada=metadatos_portada,
        fecha_ingesta=datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        paginas_total=len(doc.pages),
        chunks=chunks,
    )


def documento_a_dict(documento: DocumentoIngerido) -> dict:
    """Serializa el documento ingerido a un dict listo para JSON."""
    return {
        "doc_id": documento.doc_id,
        "nombre_fichero": documento.nombre_fichero,
        "metadatos_admin": asdict(documento.metadatos_admin),
        "metadatos_portada": asdict(documento.metadatos_portada),
        "fecha_ingesta": documento.fecha_ingesta,
        "paginas_total": documento.paginas_total,
        "chunks": [asdict(c) for c in documento.chunks],
    }
