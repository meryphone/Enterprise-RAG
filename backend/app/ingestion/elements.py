"""Extracción de elementos de un DoclingDocument parseado.

Itera los items de un DoclingDocument y los convierte en una lista plana de
ElementoProcesado — la unidad que consume el chunker. Decide por tipo de
elemento qué hacer: pasar el texto tal cual, exportar tablas a Markdown,
describir imágenes con GPT-4o vision y aplicar la regla de fusión texto-imagen.

Aquí no se generan chunks; solo elementos listos para chunkear.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from docling_core.types.doc import (
    DescriptionAnnotation,
    DoclingDocument,
    ListItem,
    PictureItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
)

from app.config import SETTINGS
from app.ingestion.patterns import (
    PATRON_ANEXO,
    PATRON_CABECERA,
    PATRON_CODIGO_DOC,
    PATRON_EDICION,
    PATRON_INDICE,
    PATRON_NUMERO_TITULO,
    PATRON_PIE_PAGINA,
    PATRON_SOLO_NUMERO,
    PATRON_TABLA_DEGRADADA,
    PATRON_TITULO,
)

logger = logging.getLogger(__name__)

# Longitud mínima en caracteres para que un fragmento de texto se considere
# contenido útil y no ruido de layout.
_MIN_LEN_TEXTO = 20

# Número máximo de items a escanear cuando se buscan metadatos de cabecera.
_MAX_ITEMS_CABECERA = 35


# ── Metadatos de cabecera ────────────────────────────────────────────────────


@dataclass
class MetadatosDocumento:
    """Metadatos extraídos automáticamente de la cabecera del documento.

    Estos campos los comparten todos los chunks del mismo documento y no
    deben aparecer en el texto de ningún chunk.
    """

    titulo: str | None = None
    edicion: str | None = None
    fecha_emision: str | None = None       # reservado, aún no se extrae


def extraer_metadatos_documento(doc: DoclingDocument) -> MetadatosDocumento:
    """Extrae título y edición de los primeros items del documento.

    - **Título**: primer SectionHeaderItem dentro de los primeros 35 items que
      encaja en PATRON_TITULO (texto largo en mayúsculas, más de una palabra).
    - **Edición**: primer item que contenga EDICION/EDITION. Si el número va
      en el mismo item ("EDICION 6 HOJA 2 DE 10") se extrae directamente;
      si no, se toma el siguiente item compuesto solo por dígitos.

    Args:
        doc: DoclingDocument parseado por Docling.

    Returns:
        MetadatosDocumento con título y edición rellenos cuando se encuentren.
    """
    meta = MetadatosDocumento()

    items_cabecera: list = []
    for item, _level in doc.iterate_items():
        if not isinstance(item, (TextItem, ListItem, SectionHeaderItem)):
            continue
        if not (item.text or "").strip():
            continue
        items_cabecera.append(item)
        if len(items_cabecera) >= _MAX_ITEMS_CABECERA:
            break

    for i, item in enumerate(items_cabecera):
        texto = (item.text or "").strip()

        if isinstance(item, SectionHeaderItem):
            if (
                meta.titulo is None
                and " " in texto
                and not PATRON_PIE_PAGINA.match(texto)
                and not PATRON_INDICE.match(texto)
                and PATRON_TITULO.match(texto)
            ):
                meta.titulo = re.sub(r"\s+", " ", texto)
            continue

        if meta.edicion is None and isinstance(item, (TextItem, ListItem)):
            if "EDICI" in texto.upper():
                m = PATRON_EDICION.search(texto)
                if m:
                    meta.edicion = m.group(1)
                elif i + 1 < len(items_cabecera):
                    sig_texto = (items_cabecera[i + 1].text or "").strip()
                    if PATRON_SOLO_NUMERO.match(sig_texto):
                        meta.edicion = sig_texto

    return meta


# ── Dataclasses de salida ────────────────────────────────────────────────────


@dataclass
class ElementoProcesado:
    """Elemento listo para entrar en el chunker.

    `texto` es el contenido textual final (con las fusiones ya aplicadas).
    Los campos `pagina`, `seccion`, `tipo_elemento`, `es_imagen` y
    `dentro_de_anexo` se propagan a los metadatos de los chunks resultantes.
    """

    texto: str
    pagina: int | None
    seccion: str | None
    tipo_elemento: str                     # Title, NarrativeText, ListItem, Table, Image
    es_imagen: bool = False
    dentro_de_anexo: bool = False
    indivisible: bool = False              # Para chunking jerárquico: las tablas son indivisibles.
    tabla_degradada: bool = False          # True cuando la tabla tiene celdas fusionadas que Docling no pudo separar.


# ── Estado interno y contadores de diagnóstico ───────────────────────────────


@dataclass
class _EstadoProcesado:
    """Estado mutable que se propaga durante el recorrido del documento."""

    seccion_actual: str | None = None
    dentro_de_anexo: bool = False
    dentro_de_indice: bool = False
    pagina_anterior: int = 0


# ── Utilidades internas ──────────────────────────────────────────────────────


def _pagina_de(item) -> int | None:
    if getattr(item, "prov", None):
        return item.prov[0].page_no
    return None


# Palabras que solo pueden aparecer en cabeceras/pies de página, nunca en
# contenido real. Cualquier token que no esté en este set, no sea numérico y no
# sea un código de documento indica que el TextItem tiene contenido legítimo.
_PALABRAS_CABECERA = frozenset({
    "EDICION", "EDICIÓN", "EDITION",
    "REVISION", "REVISIÓN",
    "HOJA", "SHEET",
    "PAGINA", "PÁGINA", "PAGE",
    "DE", "OF",
})


def _es_fragmento_cabecera_puro(texto: str) -> bool:
    """True si el TextItem contiene solo tokens de cabecera de página.

    Tokens válidos: palabras de `_PALABRAS_CABECERA`, números puros y códigos de
    documento (PR-01, 13187-IT-01...). Requiere al menos un token "fuerte"
    (algo distinto de solo DE/OF y números) para evitar filtrar frases cortas
    que casualmente solo contengan esas palabras.
    """
    tokens = texto.split()
    if not tokens:
        return False
    tiene_indicador_fuerte = False
    for t in tokens:
        t_u = t.upper()
        if t_u in _PALABRAS_CABECERA:
            if t_u not in {"DE", "OF"}:
                tiene_indicador_fuerte = True
            continue
        if PATRON_SOLO_NUMERO.match(t):
            continue
        if PATRON_CODIGO_DOC.match(t):
            tiene_indicador_fuerte = True
            continue
        return False  # token con contenido real → no es una cabecera pura
    return tiene_indicador_fuerte


# ── Handlers por tipo de item ────────────────────────────────────────────────


def _procesar_cabecera_seccion(
    item: SectionHeaderItem,
    estado: _EstadoProcesado,
    titulo_norm: str | None,
) -> None:
    """Actualiza el estado al encontrar una SectionHeaderItem. No emite elemento."""
    texto_seccion = (item.text or "").strip()
    # Ignoramos cabeceras que son cabeceras/pies de página repetidos
    if texto_seccion and PATRON_PIE_PAGINA.match(texto_seccion):
        return
    # Ignoramos la cabecera del título del documento — resetearía la sección
    if titulo_norm and titulo_norm in texto_seccion.upper():
        return
    # Docling a veces pega número y título: "3.NOTES" → "3. NOTES"
    texto_seccion = PATRON_NUMERO_TITULO.sub(r"\1 \2", texto_seccion)
    estado.seccion_actual = texto_seccion or estado.seccion_actual
    if not estado.dentro_de_anexo:
        estado.dentro_de_anexo = bool(
            estado.seccion_actual and PATRON_ANEXO.search(estado.seccion_actual)
        )
    estado.dentro_de_indice = bool(
        estado.seccion_actual and PATRON_INDICE.match(estado.seccion_actual)
    )


def _procesar_texto(
    item: TextItem | ListItem,
    pagina: int | None,
    estado: _EstadoProcesado,
    titulo_norm: str | None,
) -> ElementoProcesado | None:
    """Procesa un TextItem/ListItem y devuelve el ElementoProcesado, o None si se descarta."""
    texto = (item.text or "").strip()
    if not texto:
        return None
    # Filtros de ruido cabecera/pie:
    if PATRON_CABECERA.search(texto):          # bloque completo "EDICION 6 HOJA 7 DE 10"
        return None
    if PATRON_PIE_PAGINA.match(texto):         # código solo, "HOJA X DE Y", edición sola…
        return None
    if _es_fragmento_cabecera_puro(texto):     # cabecera fragmentada multi-token
        return None
    # Filtrar repeticiones del título del documento
    if titulo_norm and re.sub(r"\s+", " ", texto).upper() == titulo_norm:
        return None
    # Filtrar textos demasiado cortos, salvo si es un ListItem
    if len(texto) < _MIN_LEN_TEXTO and not isinstance(item, ListItem):
        return None
    tipo = "ListItem" if isinstance(item, ListItem) else "NarrativeText"
    return ElementoProcesado(
        texto=texto,
        pagina=pagina,
        seccion=estado.seccion_actual,
        tipo_elemento=tipo,
        dentro_de_anexo=estado.dentro_de_anexo,
    )


def _es_primera_aparicion_en_pagina(pagina: int | None, estado: _EstadoProcesado) -> bool:
    """True si este es el primer item visto en una nueva página (probable cabecera de página)."""
    if pagina is not None and pagina != estado.pagina_anterior:
        estado.pagina_anterior = pagina
        return True
    return False


def _procesar_tabla(
    item: TableItem,
    doc: DoclingDocument,
    pagina: int | None,
    estado: _EstadoProcesado,
) -> ElementoProcesado | None:
    """Procesa un TableItem. Devuelve el elemento o None si era la cabecera de página."""
    # La cabecera del documento se detecta a veces como el primer TableItem de
    # cada página; lo descartamos.
    if _es_primera_aparicion_en_pagina(pagina, estado):
        return None

    try:
        md = item.export_to_markdown(doc=doc)
    except TypeError:
        md = item.export_to_markdown()
    md = md.strip()
    # Docling envuelve a veces la tabla en code fences (```markdown ... ```)
    if md.startswith("```"):
        md = re.sub(r"^```[a-z]*\n?", "", md)
        md = re.sub(r"\n?```$", "", md)
        md = md.strip()
    # Docling incrusta imágenes como data URIs base64 en celdas de tabla.
    # Conservamos solo el alt text (nombre del símbolo que Docling reconoció).
    md = re.sub(r"!\[([^\]]*)\]\(data:[^)]+\)", r"\1", md)

    # Detectar tablas degradadas con celdas fusionadas que rompen el Markdown.
    degradada = bool(PATRON_TABLA_DEGRADADA.search(md))

    seccion_tabla = estado.seccion_actual  # vision puede sobrescribirla con su propio título

    if SETTINGS.enable_vision:
        from app.ingestion import vision as mod_vision
        if estado.seccion_actual is None:
            # Sin sección de contexto: vision extrae el propio título + contenido de la tabla.
            descripcion, titulo_tabla = mod_vision.describir_tabla_sin_seccion(item, doc)
            if descripcion:
                md = descripcion
            if titulo_tabla:
                seccion_tabla = titulo_tabla
        elif degradada:
            # Sección conocida pero tabla degradada: solo mejoramos el contenido.
            descripcion = mod_vision.describir_tabla(item, doc)
            if descripcion:
                md = descripcion

    return ElementoProcesado(
        texto=md,
        pagina=pagina,
        seccion=seccion_tabla,
        tipo_elemento="Table",
        dentro_de_anexo=estado.dentro_de_anexo,
        indivisible=True,
        tabla_degradada=degradada,
    )


def _procesar_imagen(
    item: PictureItem,
    pagina: int | None,
    resultado: list[ElementoProcesado],
    estado: _EstadoProcesado,
) -> None:
    """Procesa un PictureItem.

    Puede fusionar la descripción con el elemento anterior (modifica `resultado`
    in-place) o emitir un nuevo elemento standalone. La primera imagen de cada
    página se descarta como logo corporativo.
    """
    # El logo corporativo aparece como el primer PictureItem en la cabecera de página.
    # Lo detectamos por cambio de página: si es la primera imagen vista en esta
    # página, la saltamos. pagina_anterior se actualiza dentro del check para que
    # una segunda imagen en la misma página sí se procese.
    if _es_primera_aparicion_en_pagina(pagina, estado):
        return

    # Descripción generada por Docling durante el parseo vía GPT-4o
    # (PictureDescriptionApiOptions en parser.py). Si Docling no la generó
    # (vision desactivado o error de red), descartamos la imagen.
    descripcion: str | None = None
    for ann in item.get_annotations():
        if isinstance(ann, DescriptionAnnotation) and ann.text.strip():
            descripcion = ann.text.strip()
            break

    if descripcion is None:
        return

    # ¿Fusionar con el texto anterior? Condiciones: misma página y el elemento
    # previo es texto narrativo o ListItem.
    if (
        resultado
        and resultado[-1].pagina == pagina
        and resultado[-1].tipo_elemento in ("NarrativeText", "ListItem")
    ):
        previo = resultado[-1]
        previo.texto = f"{previo.texto}\n\n[Descripción visual: {descripcion}]"
        previo.es_imagen = True
        return

    # No es fusionable → chunk standalone.
    resultado.append(
        ElementoProcesado(
            texto=f"[Descripción visual: {descripcion}]",
            pagina=pagina,
            seccion=estado.seccion_actual,
            tipo_elemento="Image",
            es_imagen=True,
            dentro_de_anexo=estado.dentro_de_anexo,
        )
    )


# ── API pública ──────────────────────────────────────────────────────────────


def procesar_documento(doc: DoclingDocument, es_anexo_documento: bool = False) -> list[ElementoProcesado]:
    """Convierte todos los items de un DoclingDocument en una lista plana de ElementoProcesado.

    Args:
        doc: DoclingDocument parseado.
        es_anexo_documento: True cuando todo el fichero está clasificado como anexo,
            de forma que todos los elementos arrancan con dentro_de_anexo=True.

    Returns:
        Lista de ElementoProcesado en orden de documento, lista para chunkear.
    """
    resultado: list[ElementoProcesado] = []

    meta = extraer_metadatos_documento(doc)
    if meta.titulo is None and SETTINGS.enable_vision:
        from app.ingestion import vision as mod_vision
        meta.titulo = mod_vision.extraer_titulo_cabecera(doc)
    titulo_norm = re.sub(r"\s+", " ", meta.titulo).upper() if meta.titulo else None

    estado = _EstadoProcesado(dentro_de_anexo=es_anexo_documento)

    for item, _level in doc.iterate_items():
        pagina = _pagina_de(item)

        if isinstance(item, SectionHeaderItem):
            _procesar_cabecera_seccion(item, estado, titulo_norm)
            continue

        if estado.dentro_de_indice:
            continue

        if isinstance(item, (TextItem, ListItem)):
            elem = _procesar_texto(item, pagina, estado, titulo_norm)
            if elem is not None:
                resultado.append(elem)
            continue

        if isinstance(item, TableItem):
            elem = _procesar_tabla(item, doc, pagina, estado)
            if elem is not None:
                resultado.append(elem)
            continue

        if isinstance(item, PictureItem):
            _procesar_imagen(item, pagina, resultado, estado)
            continue

        # Otros tipos de item de Docling se ignoran por ahora.
        # (p.ej. formula, code, key-value, etc. — no presentes en el corpus de Intecsa).

    tablas = sum(1 for e in resultado if e.tipo_elemento == "Table")
    logger.info("procesar_documento: %d elementos (%d tablas)", len(resultado), tablas)

    return resultado
