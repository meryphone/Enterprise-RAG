"""Procesamiento por tipo de elemento Docling.

Recorremos los items de un `DoclingDocument` y los convertimos en una lista lineal
de `ElementoProcesado`: la unidad mínima que el chunker ve. En este paso decidimos
qué hacer con cada tipo (texto tal cual, tabla a Markdown, imagen descrita por
visión) y aplicamos la regla de fusión texto-imagen.

Aún no se construyen chunks finales: sólo elementos "listos para chunkear".
"""
from __future__ import annotations

import re
import sys
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
from app.procesamiento import vision
from app.procesamiento.patrones import (
    PATRON_ANEXO,
    PATRON_CABECERA,
    PATRON_INDICE,
    PATRON_PIE_PAGINA,
    PATRON_TITULO,
)


# Palabras clave que, cuando aparecen en el texto inmediatamente anterior a una
# imagen, nos hacen tratarla como ilustración "de ejemplo" (describir estructura,
# no transcribir datos).
_PALABRAS_EJEMPLO = (
    "ejemplo",
    "se puede ver",
    "como se muestra",
    "example",
    "as shown",
    "for instance",
)

# Longitud mínima en caracteres para que un fragmento de texto se considere
# contenido útil y no ruido de maquetación.
_MIN_LEN_TEXTO = 20

# Número máximo de ítems a escanear buscando metadatos de cabecera
_MAX_ITEMS_CABECERA = 35


# ── Metadatos de cabecera ────────────────────────────────────────────────────

@dataclass
class MetadatosDocumento:
    """Metadatos extraídos automáticamente de la cabecera del documento.

    Estos campos son comunes a todos los chunks del mismo documento y no
    deben aparecer en el texto de ningún chunk.
    """

    titulo: str | None = None
    edicion: str | None = None


def extraer_metadatos_documento(doc: DoclingDocument) -> MetadatosDocumento:
    """Itera los primeros ítems del documento y detecta metadatos de cabecera.

    Lógica de extracción:
    - **Título**: primer `SectionHeaderItem` en los primeros 35 ítems que cumpla
      el patrón de título (texto largo en mayúsculas, más de una palabra).
    - **Edición**: primer ítem que contenga la palabra EDICION/EDICIÓN/EDITION.
      Si el número sigue en el mismo ítem ("EDICION 6 HOJA 2 DE 10"), se extrae
      directamente. Si el ítem es solo "EDICION", el siguiente ítem numérico es
      la edición.
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
                and PATRON_TITULO.match(texto)
            ):
                meta.titulo = re.sub(r"\s+", " ", texto)
            continue

        if meta.edicion is None and isinstance(item, (TextItem, ListItem)):
            if "EDICI" in texto.upper():
                m = re.search(r"EDICI[OÓ]N\s+(\d+)", texto, re.IGNORECASE)
                if m:
                    meta.edicion = m.group(1)
                elif i + 1 < len(items_cabecera):
                    sig_texto = (items_cabecera[i + 1].text or "").strip()
                    if re.match(r"^\d+$", sig_texto):
                        meta.edicion = sig_texto

    return meta


# ── Dataclasses de salida ────────────────────────────────────────────────────


@dataclass
class ElementoProcesado:
    """Elemento listo para entrar al chunker.

    `texto` es el contenido textual final (ya con fusiones aplicadas). Los campos
    `pagina`, `seccion`, `tipo_elemento`, `es_imagen` y `dentro_de_anexo` se
    propagarán a los metadatos de los chunks resultantes.
    """

    texto: str
    pagina: int | None
    seccion: str | None
    tipo_elemento: str                     # Title, NarrativeText, ListItem, Table, Image
    es_imagen: bool = False
    dentro_de_anexo: bool = False
    indivisible: bool = False              # Para hierarchical chunking: las tablas son indivisibles y lo indicamos aquí.
    tabla_degradada: bool = False          # True cuando la tabla tiene celdas fusionadas que Docling no pudo separar.


# ── Utilidades internas ──────────────────────────────────────────────────────


def _pagina_de(item) -> int | None:
    if getattr(item, "prov", None):
        return item.prov[0].page_no
    return None


def _texto_previo_sugiere_ejemplo(buffer: list[ElementoProcesado]) -> bool:
    if not buffer:
        return False
    ultimo = buffer[-1].texto.lower()
    return any(clave in ultimo for clave in _PALABRAS_EJEMPLO)


# Palabras que solo pueden aparecer en cabeceras de página, nunca en contenido real.
# Cualquier token que no esté aquí, no sea un número y no sea un código de documento
# indica que el TextItem tiene contenido legítimo.
_PALABRAS_CABECERA = frozenset({
    "EDICION", "EDICIÓN", "EDITION",
    "REVISION", "REVISIÓN",
    "HOJA", "SHEET",
    "PAGINA", "PÁGINA", "PAGE",
    "DE", "OF",
})

_PATRON_CODIGO_DOC = re.compile(r"^[A-Z0-9]{2,}(?:-[A-Z0-9]+)+(?:\([^)]*\))?$")
_PATRON_NUMERO = re.compile(r"^\d+$")


def _es_fragmento_cabecera_puro(texto: str) -> bool:
    """True si el TextItem contiene únicamente tokens de cabecera de página.

    Tokens válidos: palabras de `_PALABRAS_CABECERA`, números puros y códigos de
    documento (PR-01, 13187-IT-01...). Requiere al menos un token "fuerte"
    (cualquier cosa que no sea solo DE/OF y números) para evitar filtrar frases
    cortas que accidentalmente se compongan solo de esas palabras.
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
        if _PATRON_NUMERO.match(t):
            continue
        if _PATRON_CODIGO_DOC.match(t):
            tiene_indicador_fuerte = True
            continue
        return False  # token con contenido real → no es cabecera pura
    return tiene_indicador_fuerte


# ── API pública ──────────────────────────────────────────────────────────────


def procesar_documento(doc: DoclingDocument) -> list[ElementoProcesado]:
    """Recorre el DoclingDocument y produce la lista plana de elementos.

    Reglas aplicadas → "Procesado por tipo de elemento":

    - Ítems de cabecera (título, edición) → excluidos del chunking.
    - Sección de índice → todo su contenido se descarta.
    - SectionHeaderItem que coincida con PATRON_PIE_PAGINA → se descarta sin
      actualizar seccion_actual (evita que un pie de página actúe como sección).
    - Títulos / texto narrativo / list items → texto tal cual que Docling extrajo,
      limpiando ítems que contienen el patrón de cabecera repetida.
    - Tablas → se exportan a Markdown.
    - Imágenes → llamada a visión o descripción de Docling.
    - Fusión texto-imagen: si una imagen aparece contigua a un elemento de texto
      en la misma página, fusionamos la descripción visual en el chunk de texto
      con la etiqueta `[Descripción visual: ...]`.
    - Si el título de sección contiene ANEXO/APPENDIX/ANNEX, marcamos los
      elementos posteriores de esa sección como `dentro_de_anexo`.
    """
    resultado: list[ElementoProcesado] = []

    meta = extraer_metadatos_documento(doc)
    _titulo_norm = re.sub(r"\s+", " ", meta.titulo).upper() if meta.titulo else None

    seccion_actual: str | None = None
    dentro_de_anexo = False
    dentro_de_indice = False
    logo_omitido = False  # la primera imagen del documento es siempre el logo corporativo

    # Contadores de diagnóstico — resuelven la pregunta "¿Docling no detecta
    # la imagen o el pipeline la descarta?". Se vuelcan a stderr al final.
    pic_total = 0
    pic_logo = 0
    pic_sin_descripcion = 0
    pic_fusionada = 0
    pic_standalone = 0

    for item, _level in doc.iterate_items():
        pagina = _pagina_de(item)

        # --- Cabeceras de sección: actualizan el contexto, no emiten chunk ----
        if isinstance(item, SectionHeaderItem):
            texto_seccion = (item.text or "").strip()
            # Ignorar títulos que son pies/cabeceras de página repetidos
            if texto_seccion and PATRON_PIE_PAGINA.match(texto_seccion):
                continue
            # Ignorar el titulo de la cabecera que rompe la seccion actual
            if texto_seccion.contains(_titulo_norm):
                continue
            # Docling a veces concatena número y título: "3.NOTAS" → "3. NOTAS"
            texto_seccion = re.sub(r"^(\d+\.)\s*([A-ZÁÉÍÓÚÑ])", r"\1 \2", texto_seccion)
            seccion_actual = texto_seccion or seccion_actual
            dentro_de_anexo = bool(seccion_actual and PATRON_ANEXO.search(seccion_actual))
            dentro_de_indice = bool(seccion_actual and PATRON_INDICE.match(seccion_actual))
            continue  # solo actualiza contexto, no genera chunk propio

        # --- Sección de índice: descartar todo su contenido -------------------
        if dentro_de_indice:
            continue

        # --- Texto narrativo y list items -------------------------------------
        if isinstance(item, (TextItem, ListItem)):
            texto = (item.text or "").strip()
            if not texto:
                continue
            # Filtrar ruido de cabecera/pie de página:
            if PATRON_CABECERA.search(texto):          # "EDICION 6 HOJA 7 DE 10" completo
                continue
            if PATRON_PIE_PAGINA.match(texto):         # código solo, "HOJA X DE Y", edición sola…
                continue
            if _es_fragmento_cabecera_puro(texto):     # cabecera fragmentada multilinea
                continue
            # Filtrar repeticiones del título del documento
            if _titulo_norm and re.sub(r"\s+", " ", texto).upper() == _titulo_norm:
                continue
            # Filtrar textos demasiado cortos para ser contenido útil solo si no es un ListItem
            if len(texto) < _MIN_LEN_TEXTO and not isinstance(item, ListItem):
                continue
            tipo = "ListItem" if isinstance(item, ListItem) else "NarrativeText"
            resultado.append(
                ElementoProcesado(
                    texto=texto,
                    pagina=pagina,
                    seccion=seccion_actual,
                    tipo_elemento=tipo,
                    dentro_de_anexo=dentro_de_anexo,
                )
            )
            continue

        # --- Tablas -----------------------------------------------------------
        if isinstance(item, TableItem):
            try:
                md = item.export_to_markdown(doc=doc)
            except TypeError:
                md = item.export_to_markdown()
            md = md.strip()

            # Detectamos tablas degradadas con celdas fusionadas que rompen el Markdown.
            degradada = bool(re.search(r"\|\s{10,}\|", md))

            # Tablas degradadas con visión habilitada: intentamos obtener una
            # descripción visual más fiel que el Markdown roto.
            if degradada and SETTINGS.enable_vision:
                pil_image = item.get_image(doc) if hasattr(item, "get_image") else None
                if pil_image is not None:
                    md = vision.describir_imagen(pil_image)

            resultado.append(
                ElementoProcesado(
                    texto=md,
                    pagina=pagina,
                    seccion=seccion_actual,
                    tipo_elemento="Table",
                    dentro_de_anexo=dentro_de_anexo,
                    indivisible=True,
                    tabla_degradada=degradada,
                )
            )
            continue

        # --- Imágenes ---------------------------------------------------------
        if isinstance(item, PictureItem):
            pic_total += 1

            # La primera imagen del documento es siempre el logo de Intecsa en la
            # cabecera/portada. No aporta información — la descartamos sin procesar.
            if not logo_omitido:
                logo_omitido = True
                pic_logo += 1
                continue

            # 1. Descripción de Docling (Ollama vía PictureDescriptionApiOptions).
            #    Si Docling ya describió la imagen durante el parseo, usamos ese
            #    texto directamente — evita una segunda llamada a visión.
            descripcion: str | None = None
            for ann in item.get_annotations():
                if isinstance(ann, DescriptionAnnotation) and ann.text.strip():
                    descripcion = ann.text.strip()
                    break

            # 2. Fallback: visión externa (GPT-4o) si está habilitada y Docling
            #    no generó descripción.
            if descripcion is None and SETTINGS.enable_vision:
                pil_image = item.get_image(doc) if hasattr(item, "get_image") else item.image
                if pil_image is not None:
                    es_ejemplo = _texto_previo_sugiere_ejemplo(resultado)
                    descripcion = vision.describir_imagen(pil_image, es_ejemplo=es_ejemplo)

            # Sin descripción disponible → descartar la imagen.
            if descripcion is None:
                pic_sin_descripcion += 1
                continue

            # ¿Fusión con el texto previo? Condiciones: mismo número de página y
            # el elemento anterior es texto narrativo o list item.
            if (
                resultado
                and resultado[-1].pagina == pagina
                and resultado[-1].tipo_elemento in ("NarrativeText", "ListItem")
            ):
                previo = resultado[-1]
                previo.texto = f"{previo.texto}\n\n[Descripción visual: {descripcion}]"
                previo.es_imagen = True
                pic_fusionada += 1
                continue

            # Sin fusión posible → chunk standalone.
            resultado.append(
                ElementoProcesado(
                    texto=f"[Descripción visual: {descripcion}]",
                    pagina=pagina,
                    seccion=seccion_actual,
                    tipo_elemento="Image",
                    es_imagen=True,
                    dentro_de_anexo=dentro_de_anexo,
                )
            )
            pic_standalone += 1
            continue

        # Cualquier otro tipo de elemento de Docling lo ignoramos por ahora.
        # (Ej.: formula, code, key-value, etc. — no aparecen en el corpus Intecsa).

    print(
        f"[elementos] PictureItem: total={pic_total} "
        f"logo_omitido={pic_logo} "
        f"sin_descripcion={pic_sin_descripcion} "
        f"fusionadas={pic_fusionada} "
        f"standalone={pic_standalone}",
        file=sys.stderr,
    )

    return resultado
