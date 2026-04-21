"""Llamadas directas a GPT-4o vision para elementos que Docling no puede representar en texto."""
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

_CROP_PADDING_PX = 30  # píxeles extra alrededor del recorte de tabla


def _obtener_imagen_tabla(item: TableItem, doc: DoclingDocument) -> "PILImage.Image | None":
    """Devuelve la imagen más enfocada posible de la tabla, en este orden:

    1. Crop automático de Docling (item.get_image) — el mejor cuando funciona.
    2. Crop manual usando el bounding box de prov sobre la imagen de página.
    3. Imagen de página completa — último recurso.
    """
    # ── 1. Crop de Docling ────────────────────────────────────────────────────
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

    # ── 2. Crop manual con bounding box ──────────────────────────────────────
    # BoundingBox de Docling usa coordenadas PDF: origen abajo-izquierda,
    # y crece hacia arriba. PIL usa origen arriba-izquierda, y crece hacia abajo.
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
        print(f"[vision] crop manual falló: {e}", file=sys.stderr)

    # ── 3. Página completa ────────────────────────────────────────────────────
    return imagen_pagina


def describir_tabla(item: TableItem, doc: DoclingDocument) -> str | None:
    """Describe una tabla degradada vía GPT-4o vision.

    Intenta obtener el crop más enfocado posible (ver _obtener_imagen_tabla).
    Devuelve el Markdown de la tabla, o None si no hay imagen o la API falla.
    """
    imagen = _obtener_imagen_tabla(item, doc)
    if imagen is None:
        print("[vision] describir_tabla: sin imagen disponible", file=sys.stderr)
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
        print(f"[vision] describir_tabla falló: {e}", file=sys.stderr)
        return None


def describir_tabla_sin_seccion(
    item: TableItem, doc: DoclingDocument
) -> tuple[str | None, str | None]:
    """Describe una tabla sin sección de contexto: extrae título propio + contenido.

    Útil para tablas que aparecen sin SectionHeaderItem previo (p.ej. documentos
    cuyo contenido es enteramente tabular, como listas de permisos por rol).

    Devuelve (texto_tabla, titulo_tabla). Cualquiera puede ser None si falla.
    """
    imagen = _obtener_imagen_tabla(item, doc)
    if imagen is None:
        print("[vision] describir_tabla_sin_seccion: sin imagen disponible", file=sys.stderr)
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
        print(f"[vision] tabla_sin_seccion titulo={titulo!r}", file=sys.stderr)
        return texto, titulo
    except Exception as e:
        print(f"[vision] describir_tabla_sin_seccion falló: {e}", file=sys.stderr)
        return None, None


def extraer_titulo_cabecera(doc: DoclingDocument) -> str | None:
    """Extrae el título del documento desde la cabecera de la primera página vía GPT-4o.

    Fallback cuando el regex no pudo detectar título (p.ej. documentos cuyo título
    está en una tabla de cabecera en lugar de en un SectionHeaderItem).
    Recorta el 22% superior de la primera página para enfocar la cabecera.
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
        print(f"[vision] titulo extraído: {titulo!r}", file=sys.stderr)
        return titulo or None
    except Exception as e:
        print(f"[vision] extraer_titulo_cabecera falló: {e}", file=sys.stderr)
        return None
