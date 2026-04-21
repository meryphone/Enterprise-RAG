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
from dotenv import load_dotenv

# Force CPU before importing torch/docling: the GTX 960M (CC 5.0) is not compatible.
# Remove this line in Azure where a supported GPU is available.
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

from app.ingestion.prompts import PROMPT_DESCRIPCION_IMAGEN


# Docling takes several seconds to initialise its models.
# We cache a single converter to reuse across documents.
_CONVERTER: DocumentConverter | None = None


def get_converter() -> DocumentConverter:
    """Return the process-level Docling converter singleton, building it on first call."""
    global _CONVERTER
    if _CONVERTER is None:
        _CONVERTER = _build_converter()
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
    pipeline_options = PdfPipelineOptions()
    pipeline_options.generate_picture_images = True
    pipeline_options.generate_page_images = True
    pipeline_options.do_picture_description = True
    pipeline_options.enable_remote_services = True
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
    """Parse a PDF and return a DoclingDocument with images in memory.

    Args:
        path: Absolute path to the PDF file.

    Returns:
        Parsed DoclingDocument ready for element extraction.
    """
    converter = get_converter()
    result = converter.convert(str(path))
    return result.document
