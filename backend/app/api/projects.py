from fastapi import APIRouter

from app.rag.vector_store import colecciones_disponibles

router = APIRouter()


@router.get("/projects")
def projects() -> list[dict]:
    """Lista los scopes disponibles (colecciones con documentos indexados)."""
    scopes = []
    for nombre in colecciones_disponibles():
        if nombre == "intecsa":
            scopes.append({
                "coleccion": nombre,
                "proyecto_id": None,
                "empresa": "intecsa",
                "label": "Intecsa (Global)",
            })
        elif "_" in nombre:
            proyecto_id, empresa = nombre.split("_", 1)
            scopes.append({
                "coleccion": nombre,
                "proyecto_id": proyecto_id,
                "empresa": empresa,
                "label": f"Proyecto {proyecto_id}",
            })
    scopes.sort(key=lambda s: (s["proyecto_id"] is not None, s["label"]))
    return scopes
