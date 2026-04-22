"""Projects endpoint — lists available document collections."""
from fastapi import APIRouter, Depends

from app.auth.dependencies import require_auth
from app.rag.vector_store import colecciones_disponibles

router = APIRouter()


@router.get("/projects", dependencies=[Depends(require_auth)])
def projects() -> list[dict]:
    """Return all indexed scopes (ChromaDB collections, excluding __parents).

    Collections named ``"intecsa"`` represent the global corporate corpus.
    Collections named ``"{proyecto_id}_{empresa}"`` represent client projects.

    Returns:
        List of scope dicts with keys: coleccion, proyecto_id, empresa, label.
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
