"""Wrapper sobre Docling.

Aisla al resto del pipeline del API concreto de Docling: recibimos una ruta a un PDF
y devolvemos un `DoclingDocument` con las imágenes materializadas en
memoria (necesario para poder mandarlas a GPT-4o vision después).
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Forzamos CPU antes de importar torch/docling: la GTX 960M (CC 5.0) no es compatible.
# En Azure se quitará esta línea y se usará la GPU del servicio.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

from docling.datamodel.base_models import InputFormat  # noqa: E402
from docling.document_converter import DocumentConverter, PdfFormatOption  # noqa: E402
from docling_core.types.doc import DoclingDocument  # noqa: E402
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
    TableFormerMode,
    PictureDescriptionApiOptions                                               
)


# Docling tarda varios segundos en inicializar sus modelos.
# Cacheamos un único converter para reutilizarlo entre documentos.
_CONVERTER: DocumentConverter | None = None

# OPENAI_API_KEY = load_dotent()

def get_converter() -> DocumentConverter:
    global _CONVERTER
    if _CONVERTER is None:
        _CONVERTER = _build_converter()
    return _CONVERTER


def _build_converter() -> DocumentConverter:
    pipeline_options = PdfPipelineOptions()
    pipeline_options.generate_picture_images = True
    pipeline_options.do_picture_description = False # Usar GPT-4o vision para describir las imágenes.
    pipeline_options.images_scale = 2.0
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options =  TableStructureOptions(mode=TableFormerMode.ACCURATE)

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

def parse_pdf(path: Path) -> DoclingDocument:
    """Parsea un PDF y devuelve el DoclingDocument listo para procesar."""
    converter = get_converter()
    result = converter.convert(str(path))
    return result.document
