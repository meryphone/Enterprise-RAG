"""Inspección de solo lectura del corpus indexado en ChromaDB Cloud.

Conecta con la base de datos configurada en el .env (CHROMA_DATABASE) y analiza
los chunks ya indexados: conteo por colección, distribución de tokens y salud de
metadatos. Con --anexo audita qué secciones están marcadas como `dentro_de_anexo`.

Uso:
    cd backend
    python scripts/inspect_chroma.py                 # resumen global (todas las colecciones)
    python scripts/inspect_chroma.py --coleccion intecsa
    python scripts/inspect_chroma.py --anexo          # auditoría de anexos
    python scripts/inspect_chroma.py --coleccion intecsa --anexo --muestra 5
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import SETTINGS  # noqa: E402
from app.rag.vector_store import get_chroma  # noqa: E402

try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")
    _tok = lambda s: len(_ENC.encode(s))  # noqa: E731
except Exception:  # pragma: no cover - fallback sin tiktoken
    _tok = lambda s: int(len(s.split()) * 1.3)  # noqa: E731


def _fetch_all(col) -> list[tuple[str, dict]]:
    """Pagina col.get() en bloques de 300 (límite de ChromaDB Cloud)."""
    out: list[tuple[str, dict]] = []
    off = 0
    while True:
        r = col.get(limit=300, offset=off, include=["metadatas", "documents"])
        docs, metas = r["documents"], r["metadatas"]
        if not docs:
            break
        out.extend(zip(docs, metas))
        off += len(docs)
        if len(docs) < 300:
            break
    return out


def _es_tabla(m: dict) -> bool:
    te = str(m.get("tipos_elemento") or "").lower()
    return "tabla" in te or "table" in te or bool(m.get("tabla_degradada"))


def _percentiles(xs: list[int]) -> str:
    if not xs:
        return "(0)"
    xs = sorted(xs)
    p = lambda q: xs[min(len(xs) - 1, int(len(xs) * q))]  # noqa: E731
    return (
        f"n={len(xs):5} min={min(xs):3} med={p(.5):4} "
        f"p90={p(.9):4} p95={p(.95):4} max={max(xs):5}"
    )


def _colecciones_principales(chroma, filtro: str | None) -> list:
    cols = [c for c in chroma.list_collections() if not c.name.endswith("__parents")]
    if filtro:
        cols = [c for c in cols if c.name == filtro]
    return sorted(cols, key=lambda x: x.name)


def resumen(chroma, filtro: str | None) -> None:
    print(f"Base de datos: {SETTINGS.chroma_database}\n")
    child_prosa: list[int] = []
    child_tabla: list[int] = []
    orphans: list[int] = []
    parents: list[int] = []
    sin_seccion = anexo = img = degradada = total = 0

    for col in _colecciones_principales(chroma, filtro):
        for d, m in _fetch_all(col):
            total += 1
            t = _tok(d)
            if _es_tabla(m):
                child_tabla.append(t)
            elif (m.get("parent_id") or "") == "":
                orphans.append(t)
            else:
                child_prosa.append(t)
            if not (m.get("seccion") and m.get("seccion") != "vacío"):
                sin_seccion += 1
            anexo += bool(m.get("dentro_de_anexo"))
            img += bool(m.get("es_imagen"))
            degradada += bool(m.get("tabla_degradada"))
        try:
            parents += [_tok(d) for d, _ in _fetch_all(chroma.get_collection(f"{col.name}__parents"))]
        except Exception:
            pass

    if not total:
        print("(sin chunks)")
        return

    print("=== DISTRIBUCIÓN DE TOKENS ===")
    print(f"  CHILDREN prosa            {_percentiles(child_prosa)}")
    print(f"  CHILDREN tabla            {_percentiles(child_tabla)}")
    print(f"  PARENTS huérfanos (ppal)  {_percentiles(orphans)}")
    print(f"  PARENTS (col __parents)   {_percentiles(parents)}")
    print(f"\n=== SALUD DE METADATOS (sobre {total} children) ===")
    pct = lambda n: f"{n:4} ({100 * n / total:.0f}%)"  # noqa: E731
    print(f"  sin sección:       {pct(sin_seccion)}")
    print(f"  dentro de anexo:   {pct(anexo)}")
    print(f"  con imagen:        {pct(img)}")
    print(f"  tabla degradada:   {pct(degradada)}")
    print(f"  tablas totales:    {pct(len(child_tabla))}")
    print(f"  parents huérfanos: {pct(len(orphans))}")
    sobre = sum(1 for x in child_tabla if x > 8191)
    print(f"  tablas > 8191 tok (límite embed): {sobre}")


def auditar_anexos(chroma, filtro: str | None, muestra: int) -> None:
    print(f"=== AUDITORÍA DE ANEXOS (database: {SETTINGS.chroma_database}) ===\n")
    for col in _colecciones_principales(chroma, filtro):
        data = _fetch_all(col)
        anexos = [(d, m) for d, m in data if m.get("dentro_de_anexo")]
        if not anexos:
            continue
        pct = 100 * len(anexos) / len(data) if data else 0
        print(f"── {col.name}: {len(anexos)}/{len(data)} chunks en anexo ({pct:.0f}%)")
        secciones = Counter((m.get("seccion") or "(vacío)") for _, m in anexos)
        for sec, n in secciones.most_common(10):
            print(f"     {n:3}×  {sec[:70]}")
        for d, m in anexos[:muestra]:
            print(f"     · [{m.get('nombre_fichero')}] pág {m.get('pagina_inicio')} | {str(m.get('seccion'))[:45]!r}")
            print(f"       {d[:100]!r}")
        print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coleccion", default=None, help="Colección a inspeccionar (default: todas)")
    ap.add_argument("--anexo", action="store_true", help="Auditar chunks marcados dentro_de_anexo")
    ap.add_argument("--muestra", type=int, default=3, help="Nº de chunks de ejemplo por colección en la auditoría")
    args = ap.parse_args()

    chroma = get_chroma()
    if args.anexo:
        auditar_anexos(chroma, args.coleccion, args.muestra)
    else:
        resumen(chroma, args.coleccion)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
