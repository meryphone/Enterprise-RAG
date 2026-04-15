"""Llamadas a GPT-4o vision.

Se aislan aquí todos los prompts y el cliente OpenAI. El resto del pipeline no sabe
qué modelo se usa: si no hay API key configurada, estas funciones devuelven
marcadores de posición ("[VISION_DESHABILITADA:<motivo>]") y el pipeline sigue
adelante. Esto permite validar la estructura del parseo sin gastar tokens.

Cuando migremos a Azure, sólo cambia la instanciación del cliente (AzureOpenAI en
lugar de OpenAI) — los prompts y la interfaz de este módulo se quedan igual.
"""
from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config import SETTINGS

if TYPE_CHECKING:
    from PIL.Image import Image


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PROMPT_METADATOS_PORTADA = (
    "Esta es la portada de un documento técnico de Intecsa. Contiene una tabla "
    "de revisiones con varias entradas de fecha y edición. Extrae "
    "en formato JSON: codigo_documento, edicion (la más reciente), "
    "fecha_edicion (la fecha más reciente de la tabla de revisiones)."
)

PROMPT_IMAGEN_CONTENIDO = (
    "Analiza esta imagen de un documento técnico de ingeniería industrial. "
    "Describe con el máximo detalle todo su contenido: si hay texto, "
    "transcríbelo fielmente; si hay tablas, describe las columnas y extrae los "
    "datos que contienen; si hay diagramas o esquemas técnicos, describe los "
    "elementos, conexiones y etiquetas visibles; si hay capturas de pantalla de "
    "software, describe qué muestra la interfaz y qué acción representa. El "
    "objetivo es que alguien que no vea la imagen pueda responder preguntas "
    "técnicas basándose únicamente en tu descripción."
)

PROMPT_IMAGEN_EJEMPLO = (
    "Esta imagen es un ejemplo ilustrativo dentro de un documento técnico. "
    "No transcribas los datos que contiene. Describe únicamente: qué tipo de "
    "documento o tabla muestra, qué columnas o campos tiene, y para qué sirve "
    "según el contexto."
)

# ---------------------------------------------------------------------------
# Cliente OpenAI (perezoso).
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    """Devuelve un cliente OpenAI inicializado, o None si no hay API key."""
    global _client
    if _client is not None:
        return _client
    if not SETTINGS.enable_vision:
        return None
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        return None
    _client = OpenAI(api_key=SETTINGS.openai_api_key)
    return _client


def _image_to_data_url(image: "Image") -> str:
    """Convierte un PIL.Image en un data URL base64 para la API de OpenAI."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _vision_call(image: "Image", prompt: str) -> str:
    """Llamada genérica a GPT-4o vision. Devuelve texto plano.

    Si la visión está deshabilitada (sin API key o flag), devuelve un marcador
    para que el pipeline pueda seguir y el desarrollador vea qué chunks estarían
    afectados al validar con un corpus real.
    """
    client = _get_client()
    if client is None:
        return "[VISION_DESHABILITADA:sin_api_key]"

    data_url = _image_to_data_url(image)
    response = client.chat.completions.create(
        model=SETTINGS.llm_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# API pública del módulo.
# ---------------------------------------------------------------------------


@dataclass
class MetadatosPortada:
    """Metadatos del documento, ensamblados desde dos fuentes:

    - Cabecera repetida en cada página (texto digital, vía Docling + regex):
      `codigo_documento`, `titulo_documento`, `edicion`.
    - Tabla de revisiones de la portada (GPT-4o vision, si está habilitada):
      `fecha_edicion`.
    """

    codigo_documento: str | None
    edicion: str | None
    fecha_edicion: str | None
    titulo_documento: str | None = None

    @classmethod
    def vacio(cls) -> "MetadatosPortada":
        return cls(None, None, None, None)


def extraer_metadatos_portada(image: "Image") -> MetadatosPortada:
    """Extrae {codigo, edicion, fecha} de la portada."""
    raw = _vision_call(image, PROMPT_METADATOS_PORTADA)
    if raw.startswith("[VISION_DESHABILITADA"):
        return MetadatosPortada.vacio()
    # El modelo a veces envuelve el JSON en bloques ```json — los limpiamos.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return MetadatosPortada.vacio()
    return MetadatosPortada(
        codigo_documento=data.get("codigo_documento"),
        edicion=data.get("edicion"),
        fecha_edicion=data.get("fecha_edicion"),
    )


def describir_imagen(image: "Image", *, es_ejemplo: bool = False) -> str:
    """Descripción en prosa de una imagen de contenido técnico."""
    prompt = PROMPT_IMAGEN_EJEMPLO if es_ejemplo else PROMPT_IMAGEN_CONTENIDO
    return _vision_call(image, prompt)
