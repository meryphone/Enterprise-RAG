"""Inspecciona cómo Docling parsea un conjunto de PDFs.

Muestra cada ítem del DoclingDocument con su tipo, página y texto (truncado),
lo que permite verificar si la cabecera llega como un bloque único o fragmentada,
si los títulos de sección se detectan bien, etc.

Uso:
    # Un fichero concreto
    python scripts/inspect_docling.py data/docs/proyectos_clientes/14093_petresa/14093-IT-01.pdf

    # Varios ficheros
    python scripts/inspect_docling.py doc1.pdf doc2.pdf

    # Glob
    python scripts/inspect_docling.py data/docs/proyectos_clientes/14093_petresa/*.pdf

    # Limitar a las primeras N páginas (para documentos largos)
    python scripts/inspect_docling.py --paginas 3 doc.pdf

    # Mostrar solo los primeros N ítems globales
    python scripts/inspect_docling.py --items 40 doc.pdf
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ── Bootstrap de path para importar desde backend/ sin instalar el paquete ───
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

from docling_core.types.doc import (  # noqa: E402
    ListItem,
    PictureItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
)

from app.ingestion.parser import parse_pdf  # noqa: E402


# ── Colores ANSI ──────────────────────────────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_CYAN   = "\033[36m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_BLUE   = "\033[34m"
_MAGENTA= "\033[35m"
_RED    = "\033[31m"

_COLOR = {
    "SectionHeaderItem": _CYAN + _BOLD,
    "TextItem":          _RESET,
    "ListItem":          _GREEN,
    "TableItem":         _YELLOW,
    "PictureItem":       _MAGENTA,
    "otro":              _DIM,
}


def _tipo(item) -> str:
    return type(item).__name__


def _color(item) -> str:
    return _COLOR.get(_tipo(item), _COLOR["otro"])


def _truncar(texto: str, ancho: int = 120) -> str:
    texto = texto.replace("\n", "↵ ")
    return texto if len(texto) <= ancho else texto[:ancho] + "…"


def _pagina(item) -> str:
    if getattr(item, "prov", None):
        return str(item.prov[0].page_no)
    return "?"


def inspeccionar(path: Path, max_paginas: int | None, max_items: int | None) -> None:
    print(f"\n{_BOLD}{'─' * 80}{_RESET}")
    print(f"{_BOLD}Fichero: {path.name}{_RESET}  ({path})")
    print(f"{'─' * 80}{_RESET}")

    doc = parse_pdf(path)

    print(f"  Páginas totales: {len(doc.pages)}\n")

    contadores: dict[str, int] = {}
    n = 0

    for item, level in doc.iterate_items():
        tipo = _tipo(item)
        pag_str = _pagina(item)
        pag_num = int(pag_str) if pag_str.isdigit() else 0

        if max_paginas and pag_num > max_paginas:
            continue

        contadores[tipo] = contadores.get(tipo, 0) + 1
        n += 1

        if max_items and n > max_items:
            print(f"  {_DIM}[… límite de {max_items} ítems alcanzado]{_RESET}")
            break

        # Texto a mostrar según tipo
        if isinstance(item, (TextItem, ListItem, SectionHeaderItem)):
            contenido = _truncar(item.text or "")
        elif isinstance(item, TableItem):
            try:
                md = item.export_to_markdown(doc=doc)
            except TypeError:
                md = item.export_to_markdown()
            contenido = _truncar(md.strip())
        elif isinstance(item, PictureItem):
            anns = list(item.get_annotations()) if hasattr(item, "get_annotations") else []
            contenido = f"[imagen] annotations={len(anns)}"
        else:
            contenido = ""

        indent = "  " * level
        color = _color(item)
        print(
            f"  {_DIM}#{n:>3}  pág {pag_str:>3}  lv{level}{_RESET}"
            f"  {color}{tipo:<20}{_RESET}"
            f"  {indent}{contenido}"
        )

    # Resumen de tipos
    print(f"\n  {_BOLD}Resumen de tipos:{_RESET}")
    for tipo, cnt in sorted(contadores.items(), key=lambda x: -x[1]):
        print(f"    {tipo:<25} {cnt:>4}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdfs", nargs="+", type=Path, help="PDFs a inspeccionar")
    parser.add_argument("--paginas", type=int, default=None, metavar="N",
                        help="Mostrar solo ítems de las primeras N páginas")
    parser.add_argument("--items", type=int, default=None, metavar="N",
                        help="Mostrar solo los primeros N ítems por documento")
    args = parser.parse_args()

    for pdf in args.pdfs:
        if not pdf.exists():
            print(f"{_RED}No existe: {pdf}{_RESET}", file=sys.stderr)
            continue
        inspeccionar(pdf, max_paginas=args.paginas, max_items=args.items)


if __name__ == "__main__":
    main()
