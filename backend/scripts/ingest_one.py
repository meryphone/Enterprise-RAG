"""Ingesta de un único documento. Uso: python scripts/ingest_one.py <indice>

El índice corresponde a la posición en CASOS_DE_PRUEBA de ingest_test.py (0-6).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import DOCS_DIR, PARSED_DIR, SETTINGS  # noqa: E402
from app.procesamiento.pipeline import (  # noqa: E402
    MetadatosAdministrador,
    documento_a_dict,
    ingestar_pdf,
)

CASOS_DE_PRUEBA: list[tuple[str, MetadatosAdministrador]] = [
    (
        "intecsa/procedimientos_generales/PR-01.pdf",
        MetadatosAdministrador(empresa="intecsa", proyecto_id=None, tipo_doc="procedimiento", idioma="es"),
    ),
    (
        "intecsa/procedimientos_generales/PR-07.pdf",
        MetadatosAdministrador(empresa="intecsa", proyecto_id=None, tipo_doc="procedimiento", idioma="es"),
    ),
    (
        "intecsa/procedimientos_generales/PR-02_anexo.pdf",
        MetadatosAdministrador(empresa="intecsa", proyecto_id=None, tipo_doc="anexo", idioma="es"),
    ),
    (
        "proyectos_clientes/13187_repsol/13187-IT-01.pdf",
        MetadatosAdministrador(empresa="repsol", proyecto_id="13187", tipo_doc="procedimiento", idioma="es"),
    ),
    (
        "proyectos_clientes/13189_dow/13189-IT-01 (English Version).pdf",
        MetadatosAdministrador(empresa="dow", proyecto_id="13189", tipo_doc="procedimiento", idioma="en"),
    ),
    (
        "intecsa/instrucciones_trabajo/TU/LIBRERÍA DE CÉLULAS - DIAGRAMAS DE INGENIERÍA.pdf",
        MetadatosAdministrador(empresa="intecsa", proyecto_id=None, tipo_doc="procedimiento", idioma="es"),
    ),
    (
        "intecsa/instrucciones_trabajo/TU/PDMS DRAFT - MANUAL DE CONFIGURACIÓN (ADP).pdf",
        MetadatosAdministrador(empresa="intecsa", proyecto_id=None, tipo_doc="procedimiento", idioma="es"),
    ),
    (
        "intecsa/procedimientos_generales/PR-08 ANEXO III.pdf",
        MetadatosAdministrador(empresa="intecsa", proyecto_id=None, tipo_doc="anexo", idioma="es"),
    ),
]


def main() -> int:
    idx = int(sys.argv[1])
    rel_path, metadatos = CASOS_DE_PRUEBA[idx]
    pdf_path = DOCS_DIR / rel_path

    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    print(f"ENV={SETTINGS.env}  vision={'ON' if SETTINGS.enable_vision else 'OFF'}")
    print(f"[RUN ] {rel_path}")

    t0 = time.perf_counter()
    documento = ingestar_pdf(pdf_path, metadatos)
    dt = time.perf_counter() - t0

    doc_dict = documento_a_dict(documento)
    out_path = PARSED_DIR / f"{pdf_path.stem}.json"
    out_path.write_text(json.dumps(doc_dict, ensure_ascii=False, indent=2), encoding="utf-8")

    chunks = doc_dict["chunks"]
    parents = [c for c in chunks if c["nivel"] == "parent"]
    children = [c for c in chunks if c["nivel"] == "child"]
    con_imagen = sum(1 for c in chunks if c["es_imagen"])
    anexo = sum(1 for c in chunks if c["dentro_de_anexo"])
    tablas = sum(1 for c in chunks if "Table" in c["tipos_elemento"])

    print(
        f"[OK  ] {rel_path}  ({dt:.1f}s)  "
        f"páginas={doc_dict['paginas_total']} "
        f"parents={len(parents)} children={len(children)} "
        f"tablas={tablas} con_imagen={con_imagen} anexo={anexo}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
