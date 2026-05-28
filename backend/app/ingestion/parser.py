"""Docling PDF parser wrapper.

Isolates the rest of the pipeline from Docling's API. Receives a PDF path and
returns a DoclingDocument with images materialised in memory (required for
GPT-4o vision calls downstream).

The DocumentConverter is initialised once as a process-level singleton because
startup takes ~30 s (model loading). Subsequent calls reuse the cached instance.
"""
from __future__ import annotations

import os
from pathlib import Path

# Forzar CPU si FORCE_CPU=1 (default: activado en dev por compatibilidad con
# la GTX 960M, CC 5.0, no soportada por PyTorch 2.6+). En Azure o cualquier
# entorno con GPU compatible, exportar FORCE_CPU=0 para habilitar CUDA.
if os.environ.get("FORCE_CPU", "1") == "1":
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

from docling.datamodel.base_models import InputFormat  # noqa: E402
from docling.document_converter import DocumentConverter, PdfFormatOption  # noqa: E402
from docling_core.types.doc import DoclingDocument  # noqa: E402
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
    TableFormerMode,
    PictureDescriptionApiOptions,
)

import logging
import time

logging.getLogger("RapidOCR").setLevel(logging.WARNING)

from app.config import SETTINGS
from app.ingestion.prompts import PROMPT_DESCRIPCION_IMAGEN

logger = logging.getLogger(__name__)

# Docling takes several seconds to initialise its models.
# We cache a single converter to reuse across documents.
_CONVERTER: DocumentConverter | None = None


def get_converter() -> DocumentConverter:
    """Return the process-level Docling converter singleton, building it on first call."""
    global _CONVERTER
    if _CONVERTER is None:
        logger.info("Inicializando Docling DocumentConverter (primera vez)…")
        t0 = time.perf_counter()
        _CONVERTER = _build_converter()
        logger.info("Converter listo en %.1f s", time.perf_counter() - t0)
    return _CONVERTER


def _build_picture_desc_options() -> PictureDescriptionApiOptions:
    """Build GPT-4o VLM options for image description via Docling."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    return PictureDescriptionApiOptions(
        url="https://api.openai.com/v1/chat/completions",
        params=dict(
            model="gpt-4o",
            max_tokens=1024,
        ),
        headers={
            "Authorization": f"Bearer {api_key}",
        },
        prompt=PROMPT_DESCRIPCION_IMAGEN,
        timeout=90,
    )


def _build_converter() -> DocumentConverter:
    """Construye el DocumentConverter de Docling con las opciones del pipeline activadas según SETTINGS."""
    vision_on = SETTINGS.enable_vision
    pipeline_options = PdfPipelineOptions()
    pipeline_options.generate_picture_images = vision_on
    pipeline_options.generate_page_images = vision_on   # page images only needed for degraded-table fallback
    pipeline_options.do_picture_description = vision_on
    pipeline_options.enable_remote_services = vision_on
    if vision_on:
        pipeline_options.picture_description_options = _build_picture_desc_options()
    pipeline_options.images_scale = 3.0
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options = TableStructureOptions(mode=TableFormerMode.ACCURATE)

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

def parse_pdf(path: Path) -> DoclingDocument:
    """Parsea un PDF y devuelve un DoclingDocument con las imágenes en memoria.

    El timing y el manejo de errores los hace el pipeline orquestador
    (``pipeline._ejecutar_paso``); aquí no duplicamos esos logs.

    Args:
        path: Ruta absoluta al fichero PDF.

    Returns:
        DoclingDocument parseado, listo para la extracción de elementos.
    """
    converter = get_converter()
    return converter.convert(str(path)).document
