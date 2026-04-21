"""Ingesta de un único documento.

Uso:
    python scripts/ingest_one.py <ruta_pdf> [opciones]

    Opciones:
      --empresa     NOMBRE    (default: intecsa)
      --proyecto    ID        (default: ninguno)
      --tipo        TIPO      procedimiento|instruccion_trabajo|especificacion|informe|anexo
                              (default: se infiere del nombre del fichero)
      --idioma      CODIGO    es|en|fr  (default: es)
      --anexo-de    NOMBRE    nombre del doc padre si tipo=anexo

Ejemplos:
    python scripts/ingest_one.py data/docs/intecsa/procedimientos_generales/PR-01.pdf
    python scripts/ingest_one.py data/docs/intecsa/procedimientos_generales/PR-08-ANEXO-III.pdf --tipo anexo --anexo-de PR-08
    python scripts/ingest_one.py data/docs/proyectos_clientes/13187_repsol/13187-IT-01.pdf --empresa repsol --proyecto 13187 --tipo instruccion_trabajo
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import PARSED_DIR, SETTINGS  # noqa: E402
from app.procesamiento.pipeline import (  # noqa: E402
    MetadatosAdministrador,
    documento_a_dict,
    ingestar_pdf,
)
from app.servicios.vector_store import indexar_documento  # noqa: E402


def _inferir_tipo(nombre: str) -> str:
    n = nombre.upper()
    if "ANEXO" in n or "ANNEX" in n or "APPENDIX" in n:
        return "anexo"
    if nombre.startswith("PR-"):
        return "procedimiento"
    if "-IT-" in nombre or "IT-" in nombre:
        return "instruccion_trabajo"
    return "procedimiento"


def _inferir_idioma(nombre: str) -> str:
    n = nombre.upper()
    if "ENGLISH" in n or "EN " in n:
        return "en"
    if "FRENCH" in n or "FRANÇAIS" in n:
        return "fr"
    return "es"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path, help="Ruta al fichero PDF")
    parser.add_argument("--empresa",   default="intecsa")
    parser.add_argument("--proyecto",  default=None, metavar="ID")
    parser.add_argument("--tipo",      default=None,
                        choices=["procedimiento", "instruccion_trabajo", "especificacion", "informe", "anexo"])
    parser.add_argument("--idioma",    default=None, choices=["es", "en", "fr"])
    parser.add_argument("--anexo-de",  default=None, dest="anexo_de", metavar="NOMBRE")
    args = parser.parse_args()

    pdf_path: Path = args.pdf.resolve()
    if not pdf_path.exists():
        print(f"[ERROR] No existe: {pdf_path}", file=sys.stderr)
        return 1

    tipo   = args.tipo   or _inferir_tipo(pdf_path.stem)
    idioma = args.idioma or _inferir_idioma(pdf_path.stem)

    metadatos = MetadatosAdministrador(
        empresa=args.empresa,
        proyecto_id=args.proyecto,
        tipo_doc=tipo,
        idioma=idioma,
        anexo_de=args.anexo_de or "",
    )

    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    print(f"ENV={SETTINGS.env}  vision={'ON' if SETTINGS.enable_vision else 'OFF'}")
    print(f"[RUN ] {pdf_path.name}  tipo={tipo} idioma={idioma} empresa={args.empresa}")

    t0 = time.perf_counter()
    documento = ingestar_pdf(pdf_path, metadatos)
    dt = time.perf_counter() - t0

    doc_dict = documento_a_dict(documento)
    out_path = PARSED_DIR / f"{pdf_path.stem}.json"
    out_path.write_text(json.dumps(doc_dict, ensure_ascii=False, indent=2), encoding="utf-8")

    chunks = doc_dict["chunks"]
    parents  = [c for c in chunks if c["nivel"] == "parent"]
    children = [c for c in chunks if c["nivel"] == "child"]
    con_imagen = sum(1 for c in chunks if c["es_imagen"])
    anexo      = sum(1 for c in chunks if c["dentro_de_anexo"])
    tablas     = sum(1 for c in chunks if "Table" in c["tipos_elemento"])

    print(
        f"[OK  ] {pdf_path.name}  ({dt:.1f}s)  "
        f"parents={len(parents)} children={len(children)} "
        f"tablas={tablas} con_imagen={con_imagen} anexo={anexo}"
    )
    print(f"       → {out_path}")

    t1 = time.perf_counter()
    conteo = indexar_documento(documento)
    dt_idx = time.perf_counter() - t1
    print(f"[IDX ] ChromaDB  ({dt_idx:.1f}s)  +{conteo['children']} children  +{conteo['parents']} parents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
