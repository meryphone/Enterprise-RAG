"""Expresiones regulares compartidas por el pipeline de ingestión.

Centralizadas aquí para facilitar el ajuste y las pruebas unitarias.
"""
import re

# ── Estructura del documento ─────────────────────────────────────────────────

# Secciones de tipo anexo (marcan el contenido como penalizable en reranker)
PATRON_ANEXO = re.compile(r"\b(ANEXO|APPENDIX|ANNEX)\b", re.IGNORECASE)

# Secciones de índice/tabla de contenidos — su contenido se descarta
PATRON_INDICE = re.compile(
    r"^\s*([ÍI]NDICE|INDEX|TABLE\s+OF\s+CONTENTS|CONTENTS|SUMARIO|SOMMAIRE)\.?\s*$",
    re.IGNORECASE,
)

# ── Cabecera corporativa ─────────────────────────────────────────────────────

# Cabecera repetida en cada página detectada de forma laxa (para descartar
# ítems de texto ordinario que contienen el bloque EDICION…HOJA X DE Y).
# Variante 1: con EDICION/EDITION explícito.
# Variante 2: código + número + HOJA/SHEET sin EDICION explícito.
PATRON_CABECERA = re.compile(
    r"""
    (?:EDICI[OÓ]N|EDITION)
    [\s\w\-()]*?
    (?:HOJA|SHEET|P[ÁA]GINA|PAGE)
    \s+\d+\s+(?:DE|OF)\s+\d+
    |
    [A-Z0-9]{2,}(?:-[A-Z0-9]+)+
    (?:\s*\([^)]*\))?
    \s+\d+\s+
    (?:HOJA|SHEET|P[ÁA]GINA|PAGE)
    \s+\d+\s+(?:DE|OF)\s+\d+
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ── Título de documento ──────────────────────────────────────────────────────

# SectionHeaderItem candidato a ser el título del documento: empieza por letra
# mayúscula, contiene al menos 10 caracteres del conjunto permitido.
# Se combina con la comprobación de que el texto tenga al menos un espacio
# (más de una palabra) para evitar secciones cortas como "INTRODUCCIÓN".
PATRON_TITULO = re.compile(
    r"^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ0-9 \-\/\.\,\(\)\'\":]{9,}$",
)

# ── Pies/cabeceras de página repetidos ──────────────────────────────────────

# Se aplica tanto a SectionHeaderItem (para no actualizar seccion_actual) como
# a TextItem (para no generar chunk). Captura elementos que son completamente
# ruido de maquetación: números de página, códigos solos, ediciones solas, etc.
PATRON_PIE_PAGINA = re.compile(
    r"""
    ^\s*(

        # ── Edición / revisión / versión ─────────────────────────────────────
        [Ee]dici[oó]n   \s+ \d
        | [Ee]dition    \s+ \d
        | [Rr]evisi[oó]n \s+ \d
        | \b[Rr]ev\.?\s+ \d
        | [Vv]ersi[oó]n \s+ \d
        | \bv\d+\.\d+\b \s*$

        # ── Numeración de página ──────────────────────────────────────────────
        | (?:HOJA|SHEET|P[ÁA]GINA|PAGE) \s+ \d+ \s+ (?:DE|OF) \s+ \d+
        | [Pp][áa]g(?:ina)? \.?\s+ \d
        | [Pp]age \s+ \d
        | \d+\s*[/]\s*\d+ \s*$
        | \d+\s+de\s+\d+ \s*$
        | \d+\s+of\s+\d+ \s*$

        # ── Fechas puras ──────────────────────────────────────────────────────
        | \d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4} \s*$
        | \d{4}[/\-]\d{2}[/\-]\d{2} \s*$
        | \d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|
            septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4} \s*$
        | (?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|
            septiembre|octubre|noviembre|diciembre)\s+\d{4} \s*$
        | (?:january|february|march|april|may|june|july|august|
            september|october|november|december)\s+\d{4} \s*$

        # ── Códigos de documento puros (PR-07, IT-TU-16, 13187-IT-01, etc.) ──
        | [A-Z0-9]{2,}(?:-[A-Z0-9]+)+(?:\s*\([^)]*\))? \s*$

        # ── Tokens individuales de cabecera ───────────────────────────────────
        # Docling a veces emite cada campo de cabecera como TextItem separado.
        # Un número solo o una palabra clave de cabecera sola es siempre ruido.
        | \d+ \s*$
        | (?:EDICI[OÓ]N|EDITION|HOJA|SHEET|P[ÁA]GINA|PAGE|DE|OF) \s*$

        # ── Literales de pie/cabecera ─────────────────────────────────────────
        | pie\s+de\s+p[áa]gina \s*$
        | footer \s*$
        | header \s*$
        | encabezado \s*$
        | cabecera \s*$

    )
    """,
    re.VERBOSE | re.IGNORECASE,
)
