"""Hierarchical chunking sobre la lista de `ElementoProcesado` usando LlamaIndex.

Producimos dos niveles de chunk:

- child (~128 tokens): unidad indexada con embeddings. Representa una idea
  concreta → su embedding es preciso.
- parent (~512 tokens): contexto ampliado que se pasa al LLM cuando uno de sus
  child chunks es recuperado.

Usamos `HierarchicalNodeParser` de LlamaIndex para la prosa: divide primero en
parents y luego cada parent en children con su `parent_id` correctamente
relacionado. Para las tablas (indivisibles), construimos el par parent/child
manualmente porque LlamaIndex las partiría por frases.

La salida final es una lista plana de `Chunk` (nuestro dataclass) en orden de
documento, donde los parents aparecen antes que sus children correspondientes.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from llama_index.core.node_parser import HierarchicalNodeParser
from llama_index.core.node_parser.relational.hierarchical import (
    get_leaf_nodes,
    get_root_nodes,
)
from llama_index.core.schema import Document, NodeRelationship, TextNode

from app.config import SETTINGS
from app.procesamiento.elementos import ElementoProcesado


@dataclass
class Chunk:
    chunk_id: str
    texto: str
    nivel: str                         # "child" | "parent"
    parent_id: str | None              # None para parents
    pagina_inicio: int | None
    pagina_fin: int | None
    seccion: str | None
    tipos_elemento: list[str] = field(default_factory=list)
    es_imagen: bool = False
    dentro_de_anexo: bool = False
    tabla_degradada: bool = False


# ---------------------------------------------------------------------------
# Singleton del parser de LlamaIndex (inicialización cara).
# ---------------------------------------------------------------------------

_PARSER: HierarchicalNodeParser | None = None


def _get_parser() -> HierarchicalNodeParser:
    global _PARSER
    if _PARSER is None:
        _PARSER = HierarchicalNodeParser.from_defaults(
            chunk_sizes=[SETTINGS.parent_chunk_tokens, SETTINGS.child_chunk_tokens],
            chunk_overlap=20,
        )
    return _PARSER


# ---------------------------------------------------------------------------
# Construcción de "segmentos" a partir de elementos procesados.
#
# Un segmento es un bloque contiguo de elementos que se chunkean juntos:
#  - "prosa": elementos de texto consecutivos (mismo documento lógico que pasar
#    al HierarchicalNodeParser).
#  - "tabla": un único elemento indivisible que se convierte manualmente en un
#    par parent/child sin pasar por el splitter de llama_index.
# Respetamos los cortes por sección: cuando cambia la sección, abrimos un
# segmento nuevo. Así los parents no mezclan varias secciones.
# ---------------------------------------------------------------------------


@dataclass
class _Segmento:
    tipo: str                          # "prosa" | "tabla"
    elementos: list[ElementoProcesado]


def _segmentar(elementos: list[ElementoProcesado]) -> list[_Segmento]:
    segmentos: list[_Segmento] = []
    buffer: list[ElementoProcesado] = []
    seccion_buffer: str | None = None

    def _flush():
        if buffer:
            segmentos.append(_Segmento(tipo="prosa", elementos=list(buffer)))
            buffer.clear()

    for elem in elementos:
        if elem.indivisible:
            _flush()
            seccion_buffer = None
            segmentos.append(_Segmento(tipo="tabla", elementos=[elem]))
            continue
        if buffer and elem.seccion != seccion_buffer:
            _flush()
        if not buffer:
            seccion_buffer = elem.seccion
        buffer.append(elem)

    _flush()
    return segmentos


# ---------------------------------------------------------------------------
# Conversión a Document de llama_index + extracción de metadatos agregados.
# ---------------------------------------------------------------------------


def _metadata_segmento(elementos: list[ElementoProcesado]) -> dict:
    """Metadatos que viajarán con cada nodo de llama_index.

    Estos metadatos se adjuntan al Document y se heredan en todos los nodes
    (parents y children) que el splitter produzca.
    """
    paginas = [e.pagina for e in elementos if e.pagina is not None] # Tomamos los números de página que abarcan los elementos.
    seccion = next((e.seccion for e in elementos if e.seccion), None) # Tomamos la primera sección no vacía que encontremos, asumiendo que todos los elementos del segmento pertenecen a la misma sección.
    tipos = list(dict.fromkeys(e.tipo_elemento for e in elementos)) # Tomamos la lista de tipos de elemento, eliminando duplicados pero preservando el orden.
    return {
        "pagina_inicio": min(paginas) if paginas else None,
        "pagina_fin": max(paginas) if paginas else None,
        "seccion": seccion,
        "tipos_elemento": tipos,
        "es_imagen": any(e.es_imagen for e in elementos),
        "dentro_de_anexo": any(e.dentro_de_anexo for e in elementos),
        "tabla_degradada": any(e.tabla_degradada for e in elementos),
    }


def _texto_segmento(elementos: list[ElementoProcesado]) -> str:
    return "\n\n".join(e.texto for e in elementos if e.texto)


def _nodo_a_chunk(node: TextNode, nivel: str, parent_id: str | None) -> Chunk:
    meta = node.metadata or {}
    return Chunk(
        chunk_id=node.node_id,
        texto=node.get_content(),
        nivel=nivel,
        parent_id=parent_id,
        pagina_inicio=meta.get("pagina_inicio"),
        pagina_fin=meta.get("pagina_fin"),
        seccion=meta.get("seccion"),
        tipos_elemento=list(meta.get("tipos_elemento") or []),
        es_imagen=bool(meta.get("es_imagen")),
        dentro_de_anexo=bool(meta.get("dentro_de_anexo")),
        tabla_degradada=bool(meta.get("tabla_degradada")),
    )


# ---------------------------------------------------------------------------
# Chunking de cada tipo de segmento.
# ---------------------------------------------------------------------------


def _chunkear_prosa(segmento: _Segmento) -> list[Chunk]:
    """Usa HierarchicalNodeParser para generar parents y children."""
    texto = _texto_segmento(segmento.elementos)
    if not texto.strip():
        return []

    metadata = _metadata_segmento(segmento.elementos)
    doc = Document(text=texto, metadata=metadata)
    # Excluir metadatos del cálculo de tamaño: los gestionamos nosotros en
    # el dataclass Chunk, no necesitamos que LlamaIndex los cuente como texto.
    doc.excluded_llm_metadata_keys = list(metadata.keys())
    doc.excluded_embed_metadata_keys = list(metadata.keys())

    parser = _get_parser()
    nodes = parser.get_nodes_from_documents([doc])

    # Separamos por nivel: root nodes = parents; leaf nodes = children.
    root_nodes = get_root_nodes(nodes)
    leaf_nodes = get_leaf_nodes(nodes)

    chunks: list[Chunk] = []

    # Emitimos primero cada parent seguido de sus children, para que el JSON
    # serializado se lea en orden narrativo.
    for parent in root_nodes:
        chunks.append(_nodo_a_chunk(parent, nivel="parent", parent_id=None))
        # Hijos (nietos en realidad — el segundo nivel del HierarchicalNodeParser
        # son los hojas). Filtramos los que pertenecen a este parent siguiendo
        # la relación PARENT del nodo hasta llegar al root.
        for leaf in leaf_nodes:
            if _es_descendiente(leaf, parent.node_id, nodes):
                if leaf.get_content() != parent.get_content():  # Evitamos emitir un child idéntico al parent (puede pasar con textos muy cortos).
                    chunks.append(
                        _nodo_a_chunk(leaf, nivel="child", parent_id=parent.node_id)
                    )

    return chunks


def _es_descendiente(leaf: TextNode, root_id: str, all_nodes: list[TextNode]) -> bool:
    """Sube por la cadena de PARENT hasta encontrar root_id (o agotar)."""
    id_por_node = {n.node_id: n for n in all_nodes}
    actual: TextNode | None = leaf
    visitados = 0
    while actual is not None and visitados < 10:
        rel = actual.relationships.get(NodeRelationship.PARENT)
        if rel is None:
            return False
        if rel.node_id == root_id:
            return True
        actual = id_por_node.get(rel.node_id)
        visitados += 1
    return False


def _chunkear_tabla(segmento: _Segmento) -> list[Chunk]:
    """Una tabla es indivisible: se emite como un único chunk de nivel 'child'.

    No tiene parent asociado porque la tabla ya es su propio contexto completo —
    un parent idéntico no aportaría nada al LLM. El chunk se indexa con embeddings
    y cuando se recupera se usa directamente como contexto.
    """
    texto = _texto_segmento(segmento.elementos)
    if not texto.strip():
        return []
    metadata = _metadata_segmento(segmento.elementos)

    return [
        Chunk(
            chunk_id=uuid.uuid4().hex,
            texto=texto,
            nivel="child",
            parent_id=None,
            pagina_inicio=metadata["pagina_inicio"],
            pagina_fin=metadata["pagina_fin"],
            seccion=metadata["seccion"],
            tipos_elemento=metadata["tipos_elemento"],
            es_imagen=metadata["es_imagen"],
            dentro_de_anexo=metadata["dentro_de_anexo"],
            tabla_degradada=metadata["tabla_degradada"],
        )
    ]


# ---------------------------------------------------------------------------
# API pública.
# ---------------------------------------------------------------------------


def chunk_jerarquico(elementos: list[ElementoProcesado]) -> list[Chunk]:
    """Orquesta el chunking: segmenta → chunk por tipo → concatena en orden."""
    resultado: list[Chunk] = []
    for segmento in _segmentar(elementos):
        if segmento.tipo == "tabla":
            resultado.extend(_chunkear_tabla(segmento))
        else:
            resultado.extend(_chunkear_prosa(segmento))
    return resultado
