"""Projects endpoint — lists available document collections."""
from fastapi import APIRouter

from app.rag.vector_store import colecciones_disponibles

router = APIRouter()


@router.get("/projects")
def projects() -> list[dict]:
    """Return all indexed scopes (ChromaDB collections, excluding __parents).

    Each scope is either the global corporate corpus or a client project.
    The client infers the scope type from the presence of ``proyecto_id``.
    """
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
