"""Endpoints exclusivos del rol administrador."""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.auth.dependencies import require_auth
from app.ingestion.pipeline import MetadatosAdministrador, ingestar_pdf
from app.rag.vector_store import colecciones_disponibles, get_chroma, indexar_documento

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")


def _require_admin(user: dict = Depends(require_auth)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere rol administrador.")
    return user


@router.get("/stats", dependencies=[Depends(_require_admin)])
def stats() -> dict:
    """Devuelve estadísticas reales del índice de ChromaDB para el panel de administración.

    Devuelve la lista de corpus con su número de chunks, el total de chunks y el total de corpus.
    Cada entrada de corpus incluye nombre, chunks y si es el corpus global.
    """
    chroma = get_chroma()
    nombres = colecciones_disponibles()

    corpus = []
    total_chunks = 0
    for nombre in nombres:
        try:
            col = chroma.get_collection(name=nombre)
            count = col.count()
        except Exception:
            count = 0
        total_chunks += count
        corpus.append({
            "nombre": nombre,
            "chunks": count,
            "es_global": nombre == "intecsa",
        })

    corpus.sort(key=lambda c: (not c["es_global"], c["nombre"]))

    return {
        "corpus": corpus,
        "total_chunks": total_chunks,
        "total_corpus": len(corpus),
    }


async def _ingestar_archivo(
    upload: UploadFile,
    meta: MetadatosAdministrador,
) -> dict:
    """Ejecuta el pipeline completo de ingesta sobre un fichero subido. Devuelve un dict de resultado."""
    nombre = upload.filename or "desconocido.pdf"
    data = await upload.read()

    with tempfile.NamedTemporaryFile(suffix=Path(nombre).suffix, delete=False) as f:
        f.write(data)
        tmp_path = Path(f.name)

    try:
        documento = await asyncio.to_thread(ingestar_pdf, tmp_path, meta)
        documento.nombre_fichero = nombre  
        conteo = await asyncio.to_thread(indexar_documento, documento)
        logger.info("[%s] ingesta completada: %d children, %d parents", nombre, conteo["children"], conteo["parents"])
        return {"file": nombre, "children": conteo["children"], "parents": conteo["parents"]}

    except Exception as exc:
        logger.error("[%s] ingesta fallida: %s", nombre, exc)
        return {"file": nombre, "error": str(exc)}

    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/ingest", dependencies=[Depends(_require_admin)])
async def ingest(
    files: list[UploadFile] = File(...),
    empresa: str = Form(...),
    proyecto_id: str = Form(""),
    tipo_doc: str = Form(...),
    idioma: str = Form("es"),
) -> dict:
    """Indexa uno o varios ficheros subidos en ChromaDB.

    Acepta multipart/form-data con el/los fichero(s) y los campos de metadatos.
    Ejecuta el pipeline completo (parse → elements → chunks → index) por cada fichero.
    Devuelve un objeto JSON con los resultados por fichero.
    """
    meta = MetadatosAdministrador(
        empresa=empresa,
        proyecto_id=proyecto_id or None,
        tipo_doc=tipo_doc,
        idioma=idioma,
    )
    results = []
    for upload in files:
        result = await _ingestar_archivo(upload, meta)
        results.append(result)

    return {"ok": True, "results": results}
