"""Script de ingesta de prueba sobre 7 documentos representativos.

Selección de documentos (pensada para cubrir todos los casos del pipeline):

    1. PR-01.pdf                         — procedimiento sencillo, texto plano.
                                            Corpus global Intecsa.
    2. PR-07.pdf                         — procedimiento con varias imágenes
                                            y tablas → valida el procesado de
                                            Picture/Table y la fusión
                                            texto-imagen. Elegido en lugar de
                                            un PDF más grande para mantener el
                                            banco de prueba rápido en CPU.
    3. PR-02 (ANEXO).pdf                 — anexo completo → valida
                                            tipo_doc="anexo" y propagación a
                                            los chunks.
    4. 13187-IT-01.pdf                   — instrucción de trabajo de cliente
                                            (Repsol) → valida proyecto_id y la
                                            colección por proyecto.
    5. 13189-IT-01 (English Version).pdf — instrucción en inglés → valida
                                            idioma="en" y que el pipeline es
                                            agnóstico al idioma del documento.
    6. LIBRERÍA DE CÉLULAS - DIAGRAMAS DE INGENIERÍA.pdf
                                        — librería de células TU: documento con
                                            tablas densas de símbolos de tuberías.
    7. PDMS DRAFT - MANUAL DE CONFIGURACIÓN (ADP).pdf
                                        — manual técnico TU con estructura de
                                            secciones profunda y contenido mixto.

Cada documento se procesa y su resultado se serializa a JSON en
`data/parsed/<nombre>.json` para inspección manual.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Permite ejecutar el script con `python backend/scripts/ingest_test.py`.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import DOCS_DIR, PARSED_DIR, SETTINGS  # noqa: E402
from app.ingestion.pipeline import (  # noqa: E402
    MetadatosAdministrador,
    documento_a_dict,
    ingestar_pdf,
)


# (ruta_relativa_a_docs, metadatos_admin)
CASOS_DE_PRUEBA: list[tuple[str, MetadatosAdministrador]] = [
    (
        "intecsa/procedimientos_generales/PR-01.pdf",
        MetadatosAdministrador(
            empresa="intecsa", proyecto_id=None, tipo_doc="procedimiento", idioma="es"
        ),
    ),
    (
        "intecsa/procedimientos_generales/PR-07.pdf",
        MetadatosAdministrador(
            empresa="intecsa", proyecto_id=None, tipo_doc="procedimiento", idioma="es"
        ),
    ),
    (
        "intecsa/procedimientos_generales/PR-02 (ANEXO).pdf",
        MetadatosAdministrador(
            empresa="intecsa", proyecto_id=None, tipo_doc="anexo", idioma="es"
        ),
    ),
    (
        "proyectos_clientes/13187_repsol/13187-IT-01.pdf",
        MetadatosAdministrador(
            empresa="repsol", proyecto_id="13187", tipo_doc="procedimiento", idioma="es"
        ),
    ),
     (
        "intecsa/procedimientos_generales/PR-08 ANEXO III.pdf",
        MetadatosAdministrador(
            empresa="repsol", proyecto_id="13187", tipo_doc="procedimiento", idioma="es"
        ),
    ),
    (
        "proyectos_clientes/13189_dow/13189-IT-01 (English Version).pdf",
        MetadatosAdministrador(
            empresa="dow", proyecto_id="13189", tipo_doc="procedimiento", idioma="en"
        ),
    ),
    (
        "intecsa/instrucciones_trabajo/TU/LIBRERÍA DE CÉLULAS - DIAGRAMAS DE INGENIERÍA.pdf",
        MetadatosAdministrador(
            empresa="intecsa", proyecto_id=None, tipo_doc="procedimiento", idioma="es"
        ),
    ),
    (
        "intecsa/instrucciones_trabajo/TU/PDMS DRAFT - MANUAL DE CONFIGURACIÓN (ADP).pdf",
        MetadatosAdministrador(
            empresa="intecsa", proyecto_id=None, tipo_doc="procedimiento", idioma="es"
        ),
    ),
]


def _resumen(documento_dict: dict) -> str:
    chunks = documento_dict["chunks"]
    parents = [c for c in chunks if c["nivel"] == "parent"]
    children = [c for c in chunks if c["nivel"] == "child"]
    con_imagen = sum(1 for c in chunks if c["es_imagen"])
    anexo = sum(1 for c in chunks if c["dentro_de_anexo"])
    tablas = sum(1 for c in chunks if "Table" in c["tipos_elemento"])
    return (
        f"parents={len(parents)} children={len(children)} "
        f"tablas={tablas} con_imagen={con_imagen} anexo={anexo}"
    )


def main() -> int:
    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    print(f"ENV={SETTINGS.env}  vision={'ON' if SETTINGS.enable_vision else 'OFF'}")
    print(f"Salida JSON → {PARSED_DIR}")
    print("-" * 72)

    errores = 0
    for rel_path, metadatos in CASOS_DE_PRUEBA:
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
        out_path = PARSED_DIR / f"{pdf_path.stem}.json"
        out_path.write_text(
            json.dumps(doc_dict, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[OK  ] {rel_path}  ({dt:.1f}s)  {_resumen(doc_dict)}")

    print("-" * 72)
    print("Ingesta de prueba finalizada." + (f" ({errores} errores)" if errores else ""))
    return 0 if errores == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
