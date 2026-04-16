"""Ingesta completa del corpus.

Procesa todos los PDFs de data/docs/ y los indexa en ChromaDB cloud.

Reglas aplicadas automáticamente:
  - Archivos con "(English" o "(French" en el nombre se saltan — son versiones
    duplicadas en otro idioma; se conserva únicamente la versión española.
  - Archivos con "(ANEXO)" en el nombre reciben tipo_doc="anexo".
  - Los procedimientos del corpus intecsa usan idioma="es".
  - Los documentos de proyectos_clientes heredan proyecto_id y empresa del
    nombre de su carpeta ({proyecto_id}_{empresa}/).

Salidas:
  - JSON de inspección en data/parsed/<stem>.json  (como ingest_test.py)
  - Chunks indexados en ChromaDB cloud

Uso:
    cd /ruta/al/proyecto
    .venv/bin/python backend/scripts/ingest_all.py [--dry-run]

    --dry-run  Parsea y serializa JSON pero NO indexa en ChromaDB.
               Útil para validar el pipeline sin gastar cuota de embeddings.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import DOCS_DIR, PARSED_DIR, SETTINGS  # noqa: E402
from app.procesamiento.pipeline import (  # noqa: E402
    MetadatosAdministrador,
    documento_a_dict,
    ingestar_pdf,
)
from app.servicios.vector_store import indexar_documento  # noqa: E402


# ---------------------------------------------------------------------------
# Detección de idioma y tipo a partir del nombre de fichero
# ---------------------------------------------------------------------------

_RE_ENGLISH = re.compile(r"\(English", re.IGNORECASE)
_RE_FRENCH = re.compile(r"\(French", re.IGNORECASE)
_RE_ANEXO = re.compile(r"\(ANEXO\)", re.IGNORECASE)
_RE_ANEXO_DE = re.compile(r"^(.+?)\s*[\(\-]\s*(?:ANEXO|ANNEX|ADDENDUM)", re.IGNORECASE)


def _es_version_duplicada(nombre: str) -> bool:
    """True si el fichero es una versión en otro idioma de un doc que existe en español."""
    return bool(_RE_ENGLISH.search(nombre) or _RE_FRENCH.search(nombre))


def _tipo_doc(nombre: str, tipo_base: str = "procedimiento") -> str:
    return "anexo" if _RE_ANEXO.search(nombre) else tipo_base


def _anexo_de(nombre_stem: str) -> str | None:
    """Extrae el código del documento padre si el fichero es un anexo."""
    m = _RE_ANEXO_DE.match(nombre_stem)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Construcción del manifiesto de documentos
# ---------------------------------------------------------------------------


@dataclass
class EntradaManifiesto:
    ruta_relativa: str           # relativa a DOCS_DIR
    metadatos: MetadatosAdministrador


def _manifiesto_intecsa() -> list[EntradaManifiesto]:
    """Todos los PDFs del corpus global Intecsa (procedimientos_generales)."""
    carpeta = DOCS_DIR / "intecsa" / "procedimientos_generales"
    entradas = []
    for pdf in sorted(carpeta.glob("*.pdf")):
        if _es_version_duplicada(pdf.name):
            continue
        tipo = _tipo_doc(pdf.name)
        entradas.append(
            EntradaManifiesto(
                ruta_relativa=str(pdf.relative_to(DOCS_DIR)),
                metadatos=MetadatosAdministrador(
                    empresa="intecsa",
                    proyecto_id=None,
                    tipo_doc=tipo,
                    idioma="es",
                    anexo_de=_anexo_de(pdf.stem) if tipo == "anexo" else None,
                ),
            )
        )
    return entradas


def _idioma_proyecto(nombre_archivo: str) -> str:
    """Idioma de un documento de proyecto a partir de marcas en el nombre."""
    if _RE_ENGLISH.search(nombre_archivo):
        return "en"
    if _RE_FRENCH.search(nombre_archivo):
        return "fr"
    return "es"


def _manifiesto_proyectos() -> list[EntradaManifiesto]:
    """Todos los PDFs de los proyectos de clientes."""
    carpeta_raiz = DOCS_DIR / "proyectos_clientes"
    entradas = []
    for carpeta_proyecto in sorted(carpeta_raiz.iterdir()):
        if not carpeta_proyecto.is_dir():
            continue
        # Nombre de carpeta: {proyecto_id}_{empresa}
        # Dividimos solo en el primer "_".
        partes = carpeta_proyecto.name.split("_", 1)
        if len(partes) != 2:
            continue
        proyecto_id, empresa = partes

        for pdf in sorted(carpeta_proyecto.glob("*.pdf")):
            if _es_version_duplicada(pdf.name):
                continue
            tipo = _tipo_doc(pdf.name)
            entradas.append(
                EntradaManifiesto(
                    ruta_relativa=str(pdf.relative_to(DOCS_DIR)),
                    metadatos=MetadatosAdministrador(
                        empresa=empresa,
                        proyecto_id=proyecto_id,
                        tipo_doc=tipo,
                        idioma=_idioma_proyecto(pdf.name),
                        anexo_de=_anexo_de(pdf.stem) if tipo == "anexo" else None,
                    ),
                )
            )
    return entradas


def construir_manifiesto() -> list[EntradaManifiesto]:
    return _manifiesto_intecsa() + _manifiesto_proyectos()


# ---------------------------------------------------------------------------
# Resumen del documento ingerido (igual que ingest_test.py)
# ---------------------------------------------------------------------------


def _resumen(doc_dict: dict) -> str:
    chunks = doc_dict["chunks"]
    parents = [c for c in chunks if c["nivel"] == "parent"]
    children = [c for c in chunks if c["nivel"] == "child"]
    con_imagen = sum(1 for c in chunks if c["es_imagen"])
    anexo = sum(1 for c in chunks if c["dentro_de_anexo"])
    tablas = sum(1 for c in chunks if "Table" in c["tipos_elemento"])
    return (
        f"parents={len(parents)} children={len(children)} "
        f"tablas={tablas} img={con_imagen} anexo={anexo}"
    )


# ---------------------------------------------------------------------------
# Ejecución principal
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parsea y guarda JSON pero no indexa en ChromaDB.",
    )
    args = parser.parse_args()

    dry_run: bool = args.dry_run

    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    manifiesto = construir_manifiesto()

    print(f"ENV={SETTINGS.env}  vision={'ON' if SETTINGS.enable_vision else 'OFF'}")
    print(f"Modo={'DRY-RUN (sin indexar)' if dry_run else 'COMPLETO (parseo + indexado)'}")
    print(f"Total documentos: {len(manifiesto)}")
    print(f"Salida JSON → {PARSED_DIR}")
    print("-" * 72)

    errores = 0
    total_children = 0
    total_parents = 0
    t_global = time.perf_counter()

    for i, entrada in enumerate(manifiesto, 1):
        pdf_path = DOCS_DIR / entrada.ruta_relativa
        prefijo = f"[{i:3d}/{len(manifiesto)}]"

        if not pdf_path.is_file():
            print(f"{prefijo} [SKIP] No existe: {entrada.ruta_relativa}")
            errores += 1
            continue

        print(f"{prefijo} [RUN ] {entrada.ruta_relativa}", end="", flush=True)
        t0 = time.perf_counter()

        try:
            documento = ingestar_pdf(pdf_path, entrada.metadatos)
        except Exception as e:  # noqa: BLE001
            print(f"\n{prefijo} [FAIL] {type(e).__name__}: {e}")
            errores += 1
            continue

        # Guardar JSON de inspección.
        doc_dict = documento_a_dict(documento)
        out_path = PARSED_DIR / f"{pdf_path.stem}.json"
        out_path.write_text(
            json.dumps(doc_dict, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Indexar en ChromaDB (salvo --dry-run).
        conteo: dict[str, int] = {"children": 0, "parents": 0}
        if not dry_run:
            try:
                conteo = indexar_documento(documento)
            except Exception as e:  # noqa: BLE001
                dt = time.perf_counter() - t0
                print(f"\n{prefijo} [FAIL-CHROMA] {type(e).__name__}: {e}")
                errores += 1
                continue

        dt = time.perf_counter() - t0
        total_children += conteo["children"]
        total_parents += conteo["parents"]

        print(
            f"  ({dt:.1f}s)  "
            f"{_resumen(doc_dict)}"
            + (f"  → +{conteo['children']}ch +{conteo['parents']}p" if not dry_run else "")
        )

    dt_total = time.perf_counter() - t_global
    print("-" * 72)
    print(
        f"Finalizado en {dt_total:.1f}s — "
        f"docs={len(manifiesto) - errores}/{len(manifiesto)}  "
        f"errores={errores}"
    )
    if not dry_run:
        print(f"ChromaDB: {total_children} children + {total_parents} parents indexados")

    return 0 if errores == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
