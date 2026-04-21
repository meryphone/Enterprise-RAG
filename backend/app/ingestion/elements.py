"""Element extraction from a parsed DoclingDocument.

Iterates the items of a DoclingDocument and converts them into a flat list of
ElementoProcesado — the unit the chunker consumes. Decides per element type
what to do: pass text as-is, export tables to Markdown, describe images with
GPT-4o vision, and apply the text-image merge rule.

No chunks are produced here; only elements ready to be chunked.
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

# Minimum character length for a text fragment to be considered useful content
# rather than layout noise.
_MIN_LEN_TEXTO = 20

# Maximum number of items to scan when looking for header metadata.
_MAX_ITEMS_CABECERA = 35


# ── Header metadata ──────────────────────────────────────────────────────────

@dataclass
class MetadatosDocumento:
    """Metadata automatically extracted from the document header.

    These fields are shared across all chunks from the same document and must
    not appear in the text of any chunk.
    """

    titulo: str | None = None
    edicion: str | None = None
    fecha_emision: str | None = None       # reserved, not extracted yet


def extraer_metadatos_documento(doc: DoclingDocument) -> MetadatosDocumento:
    """Extract title and edition from the first items of the document.

    - **Title**: first SectionHeaderItem in the first 35 items that matches
      PATRON_TITULO (long uppercase text, more than one word).
    - **Edition**: first item containing EDICION/EDITION. If the number follows
      on the same item ("EDICION 6 HOJA 2 DE 10"), it is extracted directly;
      otherwise the next numeric-only item is used.

    Args:
        doc: Parsed DoclingDocument from Docling.

    Returns:
        MetadatosDocumento with title and edition populated where found.
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


# ── Output dataclasses ───────────────────────────────────────────────────────


@dataclass
class ElementoProcesado:
    """Element ready to enter the chunker.

    `texto` is the final textual content (merges already applied). The fields
    `pagina`, `seccion`, `tipo_elemento`, `es_imagen`, and `dentro_de_anexo` are
    propagated to the metadata of the resulting chunks.
    """

    texto: str
    pagina: int | None
    seccion: str | None
    tipo_elemento: str                     # Title, NarrativeText, ListItem, Table, Image
    es_imagen: bool = False
    dentro_de_anexo: bool = False
    indivisible: bool = False              # For hierarchical chunking: tables are indivisible.
    tabla_degradada: bool = False          # True when the table has merged cells that Docling could not separate.


# ── Internal utilities ───────────────────────────────────────────────────────


def _pagina_de(item) -> int | None:
    if getattr(item, "prov", None):
        return item.prov[0].page_no
    return None


# Words that can only appear in page headers, never in real content.
# Any token not in this set, not a number, and not a document code
# indicates that the TextItem has legitimate content.
_PALABRAS_CABECERA = frozenset({
    "EDICION", "EDICIÓN", "EDITION",
    "REVISION", "REVISIÓN",
    "HOJA", "SHEET",
    "PAGINA", "PÁGINA", "PAGE",
    "DE", "OF",
})

def _es_fragmento_cabecera_puro(texto: str) -> bool:
    """True if the TextItem contains only page-header tokens.

    Valid tokens: words from `_PALABRAS_CABECERA`, pure numbers, and document
    codes (PR-01, 13187-IT-01...). Requires at least one "strong" token
    (anything other than just DE/OF and numbers) to avoid filtering short phrases
    that accidentally consist only of those words.
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
        return False  # token with real content → not a pure header
    return tiene_indicador_fuerte


# ── Public API ───────────────────────────────────────────────────────────────


def procesar_documento(doc: DoclingDocument, es_anexo_documento: bool = False) -> list[ElementoProcesado]:
    """Convert all items in a DoclingDocument into a flat list of ElementoProcesado.

    Args:
        doc: Parsed DoclingDocument.
        es_anexo_documento: True when the whole file is classified as an annex,
            so all elements start with dentro_de_anexo=True.

    Returns:
        List of ElementoProcesado in document order, ready for chunking.
    """
    resultado: list[ElementoProcesado] = []

    meta = extraer_metadatos_documento(doc)
    if meta.titulo is None and SETTINGS.enable_vision:
        from app.ingestion import vision as mod_vision
        meta.titulo = mod_vision.extraer_titulo_cabecera(doc)
    _titulo_norm = re.sub(r"\s+", " ", meta.titulo).upper() if meta.titulo else None

    seccion_actual: str | None = None
    dentro_de_anexo = es_anexo_documento  # sticky: only transitions False → True
    dentro_de_indice = False
    pagina_anterior = 0

    # Diagnostic counters — answer "did Docling not detect the image, or did
    # the pipeline discard it?". Dumped to stderr at the end.
    pic_total = 0
    pic_logo = 0
    pic_sin_descripcion = 0
    pic_fusionada = 0
    pic_standalone = 0

    for item, _level in doc.iterate_items():
        pagina = _pagina_de(item)

        # --- Section headings: update context, do not emit a chunk ----
        if isinstance(item, SectionHeaderItem):
            texto_seccion = (item.text or "").strip()
            # Ignore headings that are repeated page headers/footers
            if texto_seccion and PATRON_PIE_PAGINA.match(texto_seccion):
                continue
            # Ignore the document title heading that would reset the current section
            if _titulo_norm and _titulo_norm in texto_seccion.upper():
                continue
            # Docling sometimes concatenates number and title: "3.NOTES" → "3. NOTES"
            texto_seccion = PATRON_NUMERO_TITULO.sub(r"\1 \2", texto_seccion)
            seccion_actual = texto_seccion or seccion_actual
            if not dentro_de_anexo:
                dentro_de_anexo = bool(seccion_actual and PATRON_ANEXO.search(seccion_actual))
            dentro_de_indice = bool(seccion_actual and PATRON_INDICE.match(seccion_actual))
            continue  # only updates context, does not produce a chunk

        # --- Table-of-contents section: discard all content ------------------
        if dentro_de_indice:
            continue

        # --- Narrative text and list items -----------------------------------
        if isinstance(item, (TextItem, ListItem)):
            texto = (item.text or "").strip()
            if not texto:
                continue
            # Filter header/footer noise:
            if PATRON_CABECERA.search(texto):          # full "EDICION 6 HOJA 7 DE 10" block
                continue
            if PATRON_PIE_PAGINA.match(texto):         # bare code, "HOJA X DE Y", bare edition…
                continue
            if _es_fragmento_cabecera_puro(texto):     # fragmented multi-token header
                continue
            # Filter repetitions of the document title
            if _titulo_norm and re.sub(r"\s+", " ", texto).upper() == _titulo_norm:
                continue
            # Filter texts too short to be useful content, unless it is a ListItem
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

        # --- Tables -----------------------------------------------------------
        # The document header is sometimes detected as the first TableItem on
        # each page; we skip it.
        if isinstance(item, TableItem):
            if pagina is not None and pagina != pagina_anterior:
                pagina_anterior = pagina
                continue
            try:
                md = item.export_to_markdown(doc=doc)
            except TypeError:
                md = item.export_to_markdown()
            md = md.strip()
            # Docling sometimes wraps the table in code fences (```markdown ... ```)
            if md.startswith("```"):
                md = re.sub(r"^```[a-z]*\n?", "", md)
                md = re.sub(r"\n?```$", "", md)
                md = md.strip()
            # Docling embeds images as base64 data URIs in table cells.
            # Keep only the alt text (symbol name that Docling recognised).
            md = re.sub(r"!\[([^\]]*)\]\(data:[^)]+\)", r"\1", md)

            # Detect degraded tables with merged cells that break the Markdown.
            degradada = bool(PATRON_TABLA_DEGRADADA.search(md))

            seccion_tabla = seccion_actual  # may be overridden by vision-extracted title

            if SETTINGS.enable_vision:
                from app.ingestion import vision as mod_vision
                if seccion_actual is None:
                    # No context section: vision extracts the table's own title + content.
                    descripcion, titulo_tabla = mod_vision.describir_tabla_sin_seccion(item, doc)
                    if descripcion:
                        md = descripcion
                    if titulo_tabla:
                        seccion_tabla = titulo_tabla
                elif degradada:
                    # Known section but degraded table: only improve the content.
                    descripcion = mod_vision.describir_tabla(item, doc)
                    if descripcion:
                        md = descripcion

            resultado.append(
                ElementoProcesado(
                    texto=md,
                    pagina=pagina,
                    seccion=seccion_tabla,
                    tipo_elemento="Table",
                    dentro_de_anexo=dentro_de_anexo,
                    indivisible=True,
                    tabla_degradada=degradada,
                )
            )
            continue

        # --- Images -----------------------------------------------------------
        if isinstance(item, PictureItem):
            # The corporate logo appears in the page header as the first PictureItem.
            # We detect it by page change: if it is the first image seen on this page,
            # we skip it. pagina_anterior is updated here (not outside the block) so
            # that a second image on the same page is still processed.
            if pagina is not None and pagina != pagina_anterior:
                pagina_anterior = pagina
                pic_logo += 1
                continue
            pic_total += 1

            # Description generated by Docling during parsing via GPT-4o
            # (PictureDescriptionApiOptions in parser.py). If Docling did not
            # generate it (vision disabled or network error), discard the image.
            descripcion: str | None = None
            for ann in item.get_annotations():
                if isinstance(ann, DescriptionAnnotation) and ann.text.strip():
                    descripcion = ann.text.strip()
                    break

            # No description available → discard the image.
            if descripcion is None:
                pic_sin_descripcion += 1
                continue

            # Merge with previous text? Conditions: same page number and
            # previous element is narrative text or list item.
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

            # No merge possible → standalone chunk.
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

        # Any other Docling element type is ignored for now.
        # (e.g. formula, code, key-value, etc. — not present in the Intecsa corpus).

    print(
        f"[elementos] PictureItem: total={pic_total} "
        f"logo_omitido={pic_logo} "
        f"sin_descripcion={pic_sin_descripcion} "
        f"fusionadas={pic_fusionada} "
        f"standalone={pic_standalone}",
        file=sys.stderr,
    )

    return resultado
