"""Ingesta con Unstructured.io — para comparar con Docling.

Mismos documentos que ingest_test.py pero usando el pipeline de Unstructured.
La salida JSON va a `data/parsed_unstructured/` para no pisar los de Docling.

Uso: python scripts/ingest_unstructured.py [indice]
  Sin argumento: procesa todos los documentos.
  Con índice (0-6): procesa solo ese documento.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import DOCS_DIR, SETTINGS  # noqa: E402
from app.procesamiento.pipeline import MetadatosAdministrador, documento_a_dict  # noqa: E402
from app.procesamiento.pipeline_unstructured import ingestar_pdf  # noqa: E402

PARSED_UNSTRUCTURED_DIR = BACKEND_DIR.parent / "data" / "parsed_unstructured"

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
        "intecsa/procedimientos_generales/PR-02 (ANEXO).pdf",
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
]


def _resumen(doc_dict: dict) -> str:
    chunks = doc_dict["chunks"]
    parents = [c for c in chunks if c["nivel"] == "parent"]
    children = [c for c in chunks if c["nivel"] == "child"]
    con_imagen = sum(1 for c in chunks if c["es_imagen"])
    anexo = sum(1 for c in chunks if c["dentro_de_anexo"])
    tablas = sum(1 for c in chunks if "Table" in c["tipos_elemento"])
    return (
        f"páginas={doc_dict['paginas_total']} "
        f"parents={len(parents)} children={len(children)} "
        f"tablas={tablas} con_imagen={con_imagen} anexo={anexo}"
    )


def main() -> int:
    PARSED_UNSTRUCTURED_DIR.mkdir(parents=True, exist_ok=True)

    # Selección de documentos
    if len(sys.argv) > 1:
        indices = [int(sys.argv[1])]
    else:
        indices = list(range(len(CASOS_DE_PRUEBA)))

    print(f"Parser: Unstructured.io")
    print(f"ENV={SETTINGS.env}  vision={'ON' if SETTINGS.enable_vision else 'OFF'}")
    print(f"Salida JSON → {PARSED_UNSTRUCTURED_DIR}")
    print("-" * 72)

    errores = 0
    for idx in indices:
        rel_path, metadatos = CASOS_DE_PRUEBA[idx]
        pdf_path = DOCS_DIR / rel_path
        if not pdf_path.is_file():
            print(f"[SKIP] No existe: {pdf_path}")
            errores += 1
            continue

        print(f"[RUN ] {rel_path}")
        t0 = time.perf_counter()
        try:
            documento = ingestar_pdf(pdf_path, metadatos)
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {rel_path}: {type(e).__name__}: {e}")
            errores += 1
            continue
        dt = time.perf_counter() - t0

        doc_dict = documento_a_dict(documento)
        out_path = PARSED_UNSTRUCTURED_DIR / f"{pdf_path.stem}.json"
        out_path.write_text(
            json.dumps(doc_dict, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[OK  ] {rel_path}  ({dt:.1f}s)  {_resumen(doc_dict)}")

    print("-" * 72)
    print("Ingesta Unstructured finalizada." + (f" ({errores} errores)" if errores else ""))
    return 0 if errores == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
