"""Llamadas a GPT-4o vision para elementos que Docling no puede representar como texto.

Se usa en dos escenarios:
- Tablas degradadas (celdas fusionadas detectadas por PATRON_TABLA_DEGRADADA):
  la imagen de la tabla se envía a GPT-4o con PROMPT_TABLA_DEGRADADA para
  obtener una transcripción fiel a Markdown.
- Imágenes standalone (cuando ENABLE_VISION=1): se describen con PROMPT_DESCRIPCION_IMAGEN.

Prioridad para obtener la imagen de una tabla:
    1. Crop de Docling (item.get_image) — mejor calidad cuando está disponible.
    2. Crop manual usando el bounding box de prov sobre la imagen de la página.
    3. Imagen completa de la página — último recurso.
"""
from __future__ import annotations

import base64
import io
import logging
import re
from typing import TYPE_CHECKING

from docling_core.types.doc import DoclingDocument, TableItem
from openai import OpenAI

from app.config import SETTINGS
from app.ingestion.prompts import PROMPT_TABLA_DEGRADADA, PROMPT_TABLA_SIN_SECCION, PROMPT_TITULO_CABECERA

if TYPE_CHECKING:
    from PIL import Image as PILImage

logger = logging.getLogger(__name__)

_CROP_PADDING_PX = 30  # píxeles extra alrededor del crop de la tabla


# ---------------------------------------------------------------------------
# Cliente OpenAI (singleton de módulo) y helpers de bajo nivel
# ---------------------------------------------------------------------------


_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        if not SETTINGS.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY no configurada.")
        _openai_client = OpenAI(api_key=SETTINGS.openai_api_key)
    return _openai_client


def _imagen_a_base64_png(imagen: "PILImage.Image") -> str:
    """Codifica una imagen PIL como PNG en base64 (sin el prefijo data URI)."""
    buf = io.BytesIO()
    imagen.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _limpiar_code_fences(texto: str) -> str:
    """Elimina los ``` envolventes que a veces añade el LLM."""
    if texto.startswith("```"):
        texto = re.sub(r"^```[a-z]*\n?", "", texto)
        texto = re.sub(r"\n?```$", "", texto)
    return texto.strip()


def _llamar_vision(
    prompt: str,
    imagen_b64: str,
    *,
    max_tokens: int = 1024,
    contexto_error: str,
) -> str | None:
    """Envía prompt + imagen a GPT-4o vision y devuelve el texto bruto de respuesta.

    Devuelve None si la llamada falla; loguea la excepción con `contexto_error`
    como prefijo para identificar el caller.
    """
    try:
        client = _get_openai_client()
        resp = client.chat.completions.create(
            model=SETTINGS.llm_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{imagen_b64}"}},
                ],
            }],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        logger.exception("%s falló", contexto_error)
        return None


# ---------------------------------------------------------------------------
# Selección de imagen de una tabla
# ---------------------------------------------------------------------------


def _obtener_imagen_tabla(item: TableItem, doc: DoclingDocument) -> "PILImage.Image | None":
    """Devuelve la imagen más enfocada disponible para la tabla, por orden de prioridad:

    1. Crop automático de Docling (item.get_image) — el mejor cuando funciona.
    2. Crop manual usando el bounding box de prov sobre la imagen de página.
    3. Imagen completa de la página — último recurso.
    """
    # ── 1. Crop de Docling ───────────────────────────────────────────────────
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
    # El BoundingBox de Docling usa coordenadas PDF: origen abajo-izquierda,
    # crece hacia arriba. PIL usa origen arriba-izquierda, crece hacia abajo.
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
    except Exception:
        logger.exception("Recorte manual de tabla falló")

    # ── 3. Página completa ───────────────────────────────────────────────────
    return imagen_pagina


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def describir_tabla(item: TableItem, doc: DoclingDocument) -> str | None:
    """Describe una tabla degradada vía GPT-4o vision.

    Devuelve la transcripción a Markdown producida por el LLM, o None si no se
    pudo obtener imagen o la llamada a la API falló.

    Args:
        item: TableItem de Docling con metadatos prov.
        doc: DoclingDocument padre (se usa para recuperar imágenes de página).
    """
    imagen = _obtener_imagen_tabla(item, doc)
    if imagen is None:
        logger.warning("describir_tabla: no se obtuvo imagen para la tabla")
        return None

    texto = _llamar_vision(
        PROMPT_TABLA_DEGRADADA,
        _imagen_a_base64_png(imagen),
        contexto_error="describir_tabla",
    )
    if texto is None:
        return None
    return _limpiar_code_fences(texto) or None


def describir_tabla_sin_seccion(
    item: TableItem, doc: DoclingDocument
) -> tuple[str | None, str | None]:
    """Describe una tabla sin cabecera de sección previa: extrae su propio título + contenido.

    Útil para tablas que aparecen sin SectionHeaderItem previa (p.ej. documentos
    cuyo contenido es enteramente tabular, como listas de roles-permisos).

    Devuelve (texto_tabla, titulo_tabla). Cualquiera puede ser None si falla.
    """
    imagen = _obtener_imagen_tabla(item, doc)
    if imagen is None:
        logger.warning("describir_tabla_sin_seccion: no se obtuvo imagen para la tabla")
        return None, None

    respuesta = _llamar_vision(
        PROMPT_TABLA_SIN_SECCION,
        _imagen_a_base64_png(imagen),
        contexto_error="describir_tabla_sin_seccion",
    )
    if respuesta is None:
        return None, None

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
    logger.info("tabla_sin_seccion title=%r", titulo)
    return texto, titulo


def extraer_titulo_cabecera(doc: DoclingDocument) -> str | None:
    """Extrae el título del documento desde la cabecera de la primera página vía GPT-4o.

    Fallback cuando la regex no pudo detectar el título (p.ej. documentos cuyo
    título está en una tabla de cabecera en vez de en un SectionHeaderItem).
    Recorta el 22% superior de la primera página para centrarse en la cabecera.
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

    titulo = _llamar_vision(
        PROMPT_TITULO_CABECERA,
        _imagen_a_base64_png(cabecera),
        max_tokens=80,
        contexto_error="extraer_titulo_cabecera",
    )
    if titulo is None:
        return None
    logger.info("Título extraído: %r", titulo)
    return titulo or None
