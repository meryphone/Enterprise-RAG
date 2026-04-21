"""GPT-4o vision calls for elements that Docling cannot represent as text.

Used in two scenarios:
- Degraded tables (merged cells detected by PATRON_TABLA_DEGRADADA): the table
  image is sent to GPT-4o with PROMPT_TABLA_DEGRADADA for a faithful Markdown
  transcription.
- Standalone images (when ENABLE_VISION=1): described with PROMPT_DESCRIPCION_IMAGEN.

Image retrieval priority for tables:
    1. Docling crop (item.get_image) — best quality when available.
    2. Manual crop using the bounding box from prov on the page image.
    3. Full page image — last resort.
"""
from __future__ import annotations

import base64
import io
import re
import sys
from typing import TYPE_CHECKING

from docling_core.types.doc import DoclingDocument, TableItem
from openai import OpenAI

from app.config import SETTINGS
from app.ingestion.prompts import PROMPT_TABLA_DEGRADADA, PROMPT_TABLA_SIN_SECCION, PROMPT_TITULO_CABECERA

if TYPE_CHECKING:
    from PIL import Image as PILImage

_CROP_PADDING_PX = 30  # extra pixels around the table crop


def _obtener_imagen_tabla(item: TableItem, doc: DoclingDocument) -> "PILImage.Image | None":
    """Return the most focused image available for the table, in priority order:

    1. Docling automatic crop (item.get_image) — best when it works.
    2. Manual crop using the prov bounding box on the page image.
    3. Full page image — last resort.
    """
    # ── 1. Docling crop ───────────────────────────────────────────────────────
    imagen = item.get_image(doc, prov_index=0)
    if imagen is not None:
        return imagen

    if not item.prov:
        return None

    prov = item.prov[0]
    page_no = prov.page_no
    page = doc.pages.get(page_no)
    if page is None:
        return None

    page_img_ref = getattr(page, "image", None)
    if page_img_ref is None:
        return None
    imagen_pagina = getattr(page_img_ref, "pil_image", None)
    if imagen_pagina is None:
        return None

    # ── 2. Manual crop with bounding box ─────────────────────────────────────
    # Docling BoundingBox uses PDF coordinates: origin bottom-left, grows upward.
    # PIL uses origin top-left, grows downward.
    try:
        bbox = prov.bbox
        page_size = getattr(page, "size", None)
        if page_size is not None and page_size.width > 0 and page_size.height > 0:
            img_w, img_h = imagen_pagina.size
            scale_x = img_w / page_size.width
            scale_y = img_h / page_size.height

            left   = max(0, int(bbox.l * scale_x) - _CROP_PADDING_PX)
            right  = min(img_w, int(bbox.r * scale_x) + _CROP_PADDING_PX)
            top    = max(0, int((page_size.height - bbox.t) * scale_y) - _CROP_PADDING_PX)
            bottom = min(img_h, int((page_size.height - bbox.b) * scale_y) + _CROP_PADDING_PX)

            if right > left and bottom > top:
                return imagen_pagina.crop((left, top, right, bottom))
    except Exception as e:
        print(f"[vision] manual crop failed: {e}", file=sys.stderr)

    # ── 3. Full page ─────────────────────────────────────────────────────────
    return imagen_pagina


def describir_tabla(item: TableItem, doc: DoclingDocument) -> str | None:
    """Describe a degraded table via GPT-4o vision.

    Returns the Markdown transcription produced by the LLM, or None if no
    image could be obtained or the API call fails.

    Args:
        item: Docling TableItem with prov metadata.
        doc: Parent DoclingDocument (used to retrieve page images).
        seccion: Current section heading, used to select the prompt variant.
    """
    imagen = _obtener_imagen_tabla(item, doc)
    if imagen is None:
        print("[vision] describir_tabla: no image available", file=sys.stderr)
        return None

    buf = io.BytesIO()
    imagen.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    try:
        client = OpenAI(api_key=SETTINGS.openai_api_key)
        resp = client.chat.completions.create(
            model=SETTINGS.llm_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT_TABLA_DEGRADADA},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
            max_tokens=1024,
        )
        texto = resp.choices[0].message.content.strip()
        if texto.startswith("```"):
            texto = re.sub(r"^```[a-z]*\n?", "", texto)
            texto = re.sub(r"\n?```$", "", texto)
            texto = texto.strip()
        return texto or None
    except Exception as e:
        print(f"[vision] describir_tabla failed: {e}", file=sys.stderr)
        return None


def describir_tabla_sin_seccion(
    item: TableItem, doc: DoclingDocument
) -> tuple[str | None, str | None]:
    """Describe a table with no preceding section heading: extract its own title + content.

    Useful for tables that appear without a preceding SectionHeaderItem (e.g. documents
    whose content is entirely tabular, such as role-permission lists).

    Returns (texto_tabla, titulo_tabla). Either may be None if it fails.
    """
    imagen = _obtener_imagen_tabla(item, doc)
    if imagen is None:
        print("[vision] describir_tabla_sin_seccion: no image available", file=sys.stderr)
        return None, None

    buf = io.BytesIO()
    imagen.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    try:
        client = OpenAI(api_key=SETTINGS.openai_api_key)
        resp = client.chat.completions.create(
            model=SETTINGS.llm_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT_TABLA_SIN_SECCION},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
            max_tokens=1024,
        )
        respuesta = resp.choices[0].message.content.strip()

        titulo: str | None = None
        tabla_lines: list[str] = []
        in_tabla = False
        for line in respuesta.splitlines():
            if line.startswith("TITULO:"):
                titulo = line[7:].strip() or None
            elif line.startswith("TABLA:"):
                in_tabla = True
            elif in_tabla:
                tabla_lines.append(line)

        texto = "\n".join(tabla_lines).strip() or None
        print(f"[vision] tabla_sin_seccion title={titulo!r}", file=sys.stderr)
        return texto, titulo
    except Exception as e:
        print(f"[vision] describir_tabla_sin_seccion failed: {e}", file=sys.stderr)
        return None, None


def extraer_titulo_cabecera(doc: DoclingDocument) -> str | None:
    """Extract the document title from the first page header via GPT-4o.

    Fallback when the regex could not detect a title (e.g. documents whose title
    is in a header table rather than in a SectionHeaderItem).
    Crops the top 22% of the first page to focus on the header area.
    """
    page = doc.pages.get(1)
    if page is None:
        return None
    page_img_ref = getattr(page, "image", None)
    if page_img_ref is None:
        return None
    imagen_pagina = getattr(page_img_ref, "pil_image", None)
    if imagen_pagina is None:
        return None

    w, h = imagen_pagina.size
    cabecera = imagen_pagina.crop((0, 0, w, int(h * 0.22)))

    buf = io.BytesIO()
    cabecera.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    try:
        client = OpenAI(api_key=SETTINGS.openai_api_key)
        resp = client.chat.completions.create(
            model=SETTINGS.llm_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT_TITULO_CABECERA},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
            max_tokens=80,
        )
        titulo = resp.choices[0].message.content.strip()
        print(f"[vision] title extracted: {titulo!r}", file=sys.stderr)
        return titulo or None
    except Exception as e:
        print(f"[vision] extraer_titulo_cabecera failed: {e}", file=sys.stderr)
        return None
