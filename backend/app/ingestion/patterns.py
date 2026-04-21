"""Compiled regular expressions shared across the ingestion pipeline.

Centralised here so they are compiled once and easy to tune or test in isolation.
"""
import re

# ── Document structure ───────────────────────────────────────────────────────

# Annex sections — flags content as lower-priority during reranking.
PATRON_ANEXO = re.compile(
    r"(?:"
    r"^\s*(?:\d+[\.\s]+)?(?:ANEXOS?|APPENDIX|ANNEX(?:ES?)?)\b"   # inicio del título
    r"|"
    r"(?:ANEXO|ANNEX|APPENDIX)\s+(?:[IVX]+|\d+[a-z]?)\s*$"       # final con identificador
    r")",
    re.IGNORECASE,
)

# Table-of-contents sections — content is discarded during element extraction.
PATRON_INDICE = re.compile(
    r"^\s*([IÍ]\s*N\s*D\s*[IÍ]\s*C\s*E|INDEX|TABLE\s+OF\s+CONTENTS|CONTENTS|SUMARIO|SOMMAIRE)\.?\s*$",
    re.IGNORECASE,
)

# ── Corporate page header ────────────────────────────────────────────────────

# Repeated header block on every page (e.g. "EDICION 6  HOJA 3 DE 10").
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

# ── Document title ───────────────────────────────────────────────────────────

# Candidate SectionHeaderItem for the document title: starts with an uppercase letter and contains at least 10 allowed characters.
PATRON_TITULO = re.compile(
    r"^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ0-9 \-\/\.\,\(\)\'\":]{9,}$",
)

# ── Section title normalisation ──────────────────────────────────────────────

# Docling sometimes omits the space between a section number and its title: "3.NOTES" → normalised to "3. NOTES".
PATRON_NUMERO_TITULO = re.compile(r"^(\d+\.)\s*([A-ZÁÉÍÓÚÑ])")

# ── Page headers/footers ─────────────────────────────────────────────────────

# Applied to both SectionHeaderItem and TextItem to discard layout noise: page numbers, edition tokens, date strings, standalone document codes, etc.
PATRON_PIE_PAGINA = re.compile(
    r"""
    ^\s*(

        # ── Edition / revision / version ─────────────────────────────────────
        [Ee]dici[oó]n   \s+ \d
        | [Ee]dition    \s+ \d
        | [Rr]evisi[oó]n \s+ \d
        | \b[Rr]ev\.?\s+ \d
        | [Vv]ersi[oó]n \s+ \d
        | \bv\d+\.\d+\b \s*$

        # ── Page numbering ───────────────────────────────────────────────────
        | (?:HOJA|SHEET|P[ÁA]GINA|PAGE) \s+ \d+ \s+ (?:DE|OF) \s+ \d+
        | [Pp][áa]g(?:ina)? \.?\s+ \d
        | [Pp]age \s+ \d
        | \d+\s*[/]\s*\d+ \s*$
        | \d+\s+de\s+\d+ \s*$
        | \d+\s+of\s+\d+ \s*$

        # ── Pure dates ───────────────────────────────────────────────────────
        | \d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4} \s*$
        | \d{4}[/\-]\d{2}[/\-]\d{2} \s*$
        | \d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|
            septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4} \s*$
        | (?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|
            septiembre|octubre|noviembre|diciembre)\s+\d{4} \s*$
        | (?:january|february|march|april|may|june|july|august|
            september|october|november|december)\s+\d{4} \s*$

        # ── Standalone document code (e.g. PR-01, IT-TU-16, 13187-IT-01). ──
        | [A-Z0-9]{2,}(?:-[A-Z0-9]+)+(?:\s*\([^)]*\))? \s*$

        # ── Individual header tokens ──────────────────────────────────────────
        # Docling sometimes emits each header field as a separate TextItem.
        # A lone number or lone header keyword is always noise.
        | \d+ \s*$
        | (?:EDICI[OÓ]N|EDITION|HOJA|SHEET|P[ÁA]GINA|PAGE|DE|OF) \s*$

        # ── Literal footer/header labels ─────────────────────────────────────
        | pie\s+de\s+p[áa]gina \s*$
        | footer \s*$
        | header \s*$
        | encabezado \s*$
        | cabecera \s*$

    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ── Edition number extraction ────────────────────────────────────────────────

PATRON_EDICION = re.compile(r"EDICI[OÓ]N\s+(\d+)", re.IGNORECASE)
PATRON_SOLO_NUMERO = re.compile(r"^\d+$")

# ── Degraded tables ──────────────────────────────────────────────────────────

# Merged cells rendered as excessive whitespace between pipes in Markdown.
PATRON_TABLA_DEGRADADA = re.compile(r"\|\s{6,}\|")

# ── Page header tokens ───────────────────────────────────────────────────────

# Standalone document code (e.g. PR-01, IT-TU-16, 13187-IT-01).
PATRON_CODIGO_DOC = re.compile(r"^[A-Z0-9]{2,}(?:-[A-Z0-9]+)+(?:\([^)]*\))?$")
