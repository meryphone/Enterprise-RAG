"""Llamadas directas a GPT-4o vision para elementos que Docling no puede representar en texto."""
from __future__ import annotations

import base64
import io
import sys

from docling_core.types.doc import DoclingDocument, TableItem
from openai import OpenAI

from app.config import SETTINGS
from app.procesamiento.prompts import PROMPT_TABLA_DEGRADADA


def describir_tabla(item: TableItem, doc: DoclingDocument) -> str | None:
    """Describe una tabla degradada vía GPT-4o vision.

    Obtiene el recorte de la tabla desde la imagen de página (requiere
    generate_page_images=True en el converter) y lo envía a GPT-4o con el
    prompt estándar de descripción de imágenes técnicas.

    Devuelve la descripción como string, o None si la imagen no está disponible
    o la llamada a la API falla.
    """
    imagen = item.get_image(doc, prov_index=0)
    if imagen is None:
        print("[vision] describir_tabla: get_image devolvió None (¿generate_page_images=True?)", file=sys.stderr)
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
            import re
            texto = re.sub(r"^```[a-z]*\n?", "", texto)
            texto = re.sub(r"\n?```$", "", texto)
            texto = texto.strip()
        return texto or None
    except Exception as e:
        print(f"[vision] describir_tabla falló: {e}", file=sys.stderr)
        return None
