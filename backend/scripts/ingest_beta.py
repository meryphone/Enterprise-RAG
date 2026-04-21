"""Ingesta beta: primeros N procedimientos + todos los proyectos de clientes.

Crea todas las colecciones esperadas en ChromaDB (incluidas las vacías para
instrucciones de trabajo) y después ingesta los documentos seleccionados.

Uso:
    cd /ruta/al/proyecto
    .venv/bin/python backend/scripts/ingest_beta.py [--dry-run] [--max-procedimientos N]

    --dry-run               Parsea y guarda JSON pero NO indexa en ChromaDB.
    --max-procedimientos N  Numero de procedimientos principales a ingestar (default 10).
                            Sus anexos se incluyen automaticamente.
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
from app.ingestion.pipeline import (  # noqa: E402
    MetadatosAdministrador,
    documento_a_dict,
    ingestar_pdf,
)
from app.rag.vector_store import (  # noqa: E402
    indexar_documento,
    nombre_coleccion,
    precrear_colecciones,
)


# ---------------------------------------------------------------------------
# Lectura del manifiesto (collections.json)
# ---------------------------------------------------------------------------

_COLLECTIONS_JSON = DOCS_DIR / "collections.json"


def _leer_colecciones_esperadas() -> list[str]:
    """Devuelve los nombres de todas las colecciones que deben existir en ChromaDB.

    Lee collections.json y genera:
      - "intecsa" para el corpus corporativo.
      - "{codigo_proyecto}_{cliente}" para cada proyecto de clientes.
    """
    with open(_COLLECTIONS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    nombres: list[str] = []
    for col in data["colecciones"]:
        if col["tipo_coleccion"] == "corporativa":
            nombres.append(col["id"])  # "intecsa"
        elif col["tipo_coleccion"] == "proyectos":
            for proy in col["proyectos"]:
                nombres.append(proy["id"])  # "13187_repsol", etc.
    return nombres


# ---------------------------------------------------------------------------
# Deteccion de idioma y tipo a partir del nombre de fichero
# ---------------------------------------------------------------------------

_RE_ENGLISH = re.compile(r"\(English|[\-_]ENG\b|\(I\)|INGLES|-INGLES", re.IGNORECASE)
_RE_FRENCH = re.compile(r"\(French", re.IGNORECASE)
_RE_ANEXO = re.compile(r"ANEXO|ANNEX|ADDENDUM", re.IGNORECASE)

# Patron para extraer el numero de procedimiento de un PDF: PR-01, PR-02, etc.
_RE_PR_NUM = re.compile(r"^PR-(\d+)")


def _es_version_duplicada(nombre: str) -> bool:
    """True si el fichero es una version en otro idioma del mismo documento."""
    return bool(_RE_ENGLISH.search(nombre) or _RE_FRENCH.search(nombre))


def _tipo_doc_de_nombre(nombre: str, tipo_base: str = "procedimiento") -> str:
    """Infiere tipo_doc del nombre del fichero."""
    if _RE_ANEXO.search(nombre):
        return "anexo"
    return tipo_base


# Patron para extraer el documento padre de un anexo de proyecto.
# Ej: "14090-IT-01 (ANEXO).pdf" → "14090-IT-01"
#     "16055-IT-02 (ANEXO).pdf" → "16055-IT-02"
_RE_ANEXO_DE = re.compile(r"^(.+?)\s*[\(\-]\s*(?:ANEXO|ANNEX|ADDENDUM)", re.IGNORECASE)


def _anexo_de_nombre(nombre_stem: str) -> str | None:
    """Extrae el codigo del documento padre si el fichero es un anexo."""
    m = _RE_ANEXO_DE.match(nombre_stem)
    return m.group(1).strip() if m else None


def _idioma_de_nombre(nombre: str) -> str:
    if _RE_ENGLISH.search(nombre):
        return "en"
    if _RE_FRENCH.search(nombre):
        return "fr"
    return "es"


# ---------------------------------------------------------------------------
# Construccion del manifiesto de documentos a ingestar
# ---------------------------------------------------------------------------


@dataclass
class EntradaManifiesto:
    ruta_pdf: Path
    metadatos: MetadatosAdministrador


def _manifiesto_procedimientos(max_principales: int) -> list[EntradaManifiesto]:
    """Primeros N procedimientos principales + sus anexos.

    Ordena los PDFs por numero de procedimiento, toma los primeros
    `max_principales` codigos unicos (e.g. PR-01..PR-11 si PR-04 no existe)
    y anade automaticamente los anexos de esos procedimientos.
    """
    carpeta = DOCS_DIR / "intecsa" / "procedimientos_generales"
    todos = sorted(carpeta.glob("*.pdf"))

    # Separar principales de anexos y agrupar por numero de procedimiento.
    principales: dict[int, Path] = {}  # num -> path
    anexos: dict[int, list[Path]] = {}  # num -> [paths]

    for pdf in todos:
        if _es_version_duplicada(pdf.name):
            continue
        m = _RE_PR_NUM.match(pdf.stem)
        if not m:
            continue
        num = int(m.group(1))
        if _RE_ANEXO.search(pdf.name):
            anexos.setdefault(num, []).append(pdf)
        else:
            principales[num] = pdf

    # Tomar los primeros N numeros de procedimiento ordenados.
    numeros_seleccionados = sorted(principales.keys())[:max_principales]

    entradas: list[EntradaManifiesto] = []
    for num in numeros_seleccionados:
        # Procedimiento principal.
        pdf = principales[num]
        entradas.append(
            EntradaManifiesto(
                ruta_pdf=pdf,
                metadatos=MetadatosAdministrador(
                    empresa="intecsa",
                    proyecto_id=None,
                    tipo_doc="procedimiento",
                    idioma="es",
                ),
            )
        )
        # Anexos de este procedimiento.
        for anexo_pdf in sorted(anexos.get(num, [])):
            entradas.append(
                EntradaManifiesto(
                    ruta_pdf=anexo_pdf,
                    metadatos=MetadatosAdministrador(
                        empresa="intecsa",
                        proyecto_id=None,
                        tipo_doc="anexo",
                        idioma="es",
                        anexo_de=pdf.stem,
                    ),
                )
            )
    return entradas


def _manifiesto_instrucciones_intecsa() -> list[EntradaManifiesto]:
    """Instrucciones de trabajo del corpus global Intecsa."""
    return [
        EntradaManifiesto(
            ruta_pdf=DOCS_DIR / "intecsa" / "instrucciones_trabajo" / "TU" / "LIBRERÍA-DE-CÉLULAS-DIAGRAMAS-DE-INGENIERÍA.pdf",
            metadatos=MetadatosAdministrador(
                empresa="intecsa",
                proyecto_id=None,
                tipo_doc="instruccion_trabajo",
                idioma="es",
            ),
        ),
    ]


def _manifiesto_proyectos() -> list[EntradaManifiesto]:
    """Todos los PDFs de proyectos de clientes (sin duplicados de idioma)."""
    carpeta_raiz = DOCS_DIR / "proyectos_clientes"
    entradas: list[EntradaManifiesto] = []

    for carpeta_proyecto in sorted(carpeta_raiz.iterdir()):
        if not carpeta_proyecto.is_dir():
            continue
        partes = carpeta_proyecto.name.split("_", 1)
        if len(partes) != 2:
            continue
        proyecto_id, empresa = partes

        for pdf in sorted(carpeta_proyecto.glob("*.pdf")):
            if _es_version_duplicada(pdf.name):
                continue
            tipo = _tipo_doc_de_nombre(pdf.name, "instruccion_trabajo")
            entradas.append(
                EntradaManifiesto(
                    ruta_pdf=pdf,
                    metadatos=MetadatosAdministrador(
                        empresa=empresa,
                        proyecto_id=proyecto_id,
                        tipo_doc=tipo,
                        idioma=_idioma_de_nombre(pdf.name),
                        anexo_de=_anexo_de_nombre(pdf.stem) if tipo == "anexo" else None,
                    ),
                )
            )
    return entradas


# ---------------------------------------------------------------------------
# Resumen del documento ingerido
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
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parsea y guarda JSON pero no indexa en ChromaDB.",
    )
    parser.add_argument(
        "--max-procedimientos",
        type=int,
        default=10,
        help="Numero de procedimientos principales a ingestar (default 10).",
    )
    args = parser.parse_args()

    dry_run: bool = args.dry_run
    max_proc: int = args.max_procedimientos

    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Pre-crear todas las colecciones en ChromaDB ────────────────────
    if not dry_run:
        print("Pre-creando colecciones en ChromaDB...")
        colecciones = _leer_colecciones_esperadas()
        precrear_colecciones(colecciones)
        print(f"  {len(colecciones)} colecciones listas: {', '.join(colecciones)}")
    print()

    # ── 2. Construir manifiesto ───────────────────────────────────────────
    procedimientos = _manifiesto_procedimientos(max_proc)
    instrucciones = _manifiesto_instrucciones_intecsa()
    proyectos = _manifiesto_proyectos()
    manifiesto = procedimientos + instrucciones + proyectos

    print(f"ENV={SETTINGS.env}  vision={'ON' if SETTINGS.enable_vision else 'OFF'}")
    print(f"Modo={'DRY-RUN (sin indexar)' if dry_run else 'COMPLETO (parseo + indexado)'}")
    print(f"Procedimientos:     {len(procedimientos)} PDFs (primeros {max_proc} + anexos)")
    print(f"Instrucciones (IT): {len(instrucciones)} PDFs (corpus global Intecsa)")
    print(f"Proyectos:          {len(proyectos)} PDFs (todos los clientes)")
    print(f"Total:          {len(manifiesto)} documentos")
    print(f"Salida JSON ->  {PARSED_DIR}")
    print("-" * 72)

    # ── 3. Ingestar ──────────────────────────────────────────────────────
    errores = 0
    total_children = 0
    total_parents = 0
    t_global = time.perf_counter()

    for i, entrada in enumerate(manifiesto, 1):
        prefijo = f"[{i:3d}/{len(manifiesto)}]"

        if not entrada.ruta_pdf.is_file():
            print(f"{prefijo} [SKIP] No existe: {entrada.ruta_pdf.name}")
            errores += 1
            continue

        print(f"{prefijo} [RUN ] {entrada.ruta_pdf.name}", end="", flush=True)
        t0 = time.perf_counter()

        try:
            documento = ingestar_pdf(entrada.ruta_pdf, entrada.metadatos)
        except Exception as e:  # noqa: BLE001
            print(f"\n{prefijo} [FAIL] {type(e).__name__}: {e}")
            errores += 1
            continue

        # Guardar JSON de inspeccion.
        doc_dict = documento_a_dict(documento)
        out_path = PARSED_DIR / f"{entrada.ruta_pdf.stem}.json"
        out_path.write_text(
            json.dumps(doc_dict, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Indexar en ChromaDB (salvo --dry-run).
        conteo: dict[str, int] = {"children": 0, "parents": 0}
        if not dry_run:
            try:
                conteo = indexar_documento(documento)
            except Exception as e:  # noqa: BLE001
                print(f"\n{prefijo} [FAIL-CHROMA] {type(e).__name__}: {e}")
                errores += 1
                continue

        dt = time.perf_counter() - t0
        total_children += conteo["children"]
        total_parents += conteo["parents"]

        print(
            f"  ({dt:.1f}s)  "
            f"{_resumen(doc_dict)}"
            + (f"  -> +{conteo['children']}ch +{conteo['parents']}p" if not dry_run else "")
        )

    dt_total = time.perf_counter() - t_global
    print("-" * 72)
    print(
        f"Finalizado en {dt_total:.1f}s -- "
        f"docs={len(manifiesto) - errores}/{len(manifiesto)}  "
        f"errores={errores}"
    )
    if not dry_run:
        print(f"ChromaDB: {total_children} children + {total_parents} parents indexados")

    return 0 if errores == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
