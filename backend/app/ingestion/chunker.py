"""Chunking jerárquico de ElementoProcesado usando LlamaIndex.

Produce dos niveles de chunk:
- **child** (~128 tokens): indexado con embeddings. Unidad de retrieval precisa.
- **parent** (~1024 tokens): contexto más amplio recuperado por ID cuando
  se encuentra un child, pasado al LLM para la generación.

Usa HierarchicalNodeParser de LlamaIndex para los segmentos de prosa. Las tablas
(indivisibles) se chunkean manualmente como un único child sin parent, porque
partirlas por frases perdería su estructura.

Filtros previos al chunking aplicados en ``chunk_jerarquico()``:
- Elementos con ``seccion=None`` (portada, antes de la primera cabecera).
- Elementos de prosa más cortos que ``_LONGITUD_MINIMA_CHARS`` (ruido de layout).
  Las tablas están exentas — su longitud no indica irrelevancia.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from llama_index.core.node_parser import HierarchicalNodeParser
from llama_index.core.node_parser.relational.hierarchical import (
    get_leaf_nodes,
    get_root_nodes,
)
from llama_index.core.schema import Document, NodeRelationship, TextNode

from app.config import SETTINGS
from app.ingestion.elements import ElementoProcesado

logger = logging.getLogger(__name__)

# Longitud mínima de texto (caracteres) para que un elemento de prosa entre al
# chunker. Elimina fragmentos cortos de ruido que escaparon a los filtros de
# elements.py (códigos de documento sueltos, cabeceras residuales, etc.).
# Las tablas están exentas: su longitud no indica irrelevancia.
_LONGITUD_MINIMA_CHARS = 20

# Número máximo de saltos a recorrer por la cadena PARENT al buscar el root.
_MAX_PROFUNDIDAD_PARENT = 10


@dataclass
class Chunk:
    chunk_id: str
    texto: str
    nivel: str                         # "child" | "parent"
    parent_id: str | None              # None para parents
    pagina_inicio: int | None
    pagina_fin: int | None
    seccion: str | None
    es_imagen: bool = False
    dentro_de_anexo: bool = False


# ---------------------------------------------------------------------------
# Singleton del parser de LlamaIndex (caro de inicializar).
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
# Construcción de "segmentos" desde los elementos procesados.
#
# Un segmento es un bloque contiguo de elementos chunkeados juntos:
#  - "prosa": elementos de texto consecutivos (unidad lógica que se pasa a
#    HierarchicalNodeParser).
#  - "tabla": un único elemento indivisible convertido manualmente sin pasar
#    por el splitter de llama_index.
# Se respetan las fronteras de sección: un cambio de sección abre un segmento
# nuevo para que los parents no mezclen contenido entre secciones.
# ---------------------------------------------------------------------------


@dataclass
class _Segmento:
    tipo: str                          # "prosa" | "tabla"
    elementos: list[ElementoProcesado]


def _segmentar(elementos: list[ElementoProcesado]) -> list[_Segmento]:
    """Agrupa elementos en segmentos contiguos del mismo tipo.

    Un cambio de sección fuerza un nuevo segmento de prosa, evitando que los
    parents mezclen contenido a través de las fronteras de sección.

    Args:
        elementos: Lista pre-filtrada de ElementoProcesado.

    Returns:
        Lista de _Segmento, cada uno tipado como "prosa" o "tabla".
    """
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
    """Metadatos que se adjuntan a cada nodo de llama_index.

    Estos metadatos se adjuntan al Document y los heredan todos los nodos
    (parents y children) que produzca el splitter.
    """
    paginas = [e.pagina for e in elementos if e.pagina is not None]
    seccion = next((e.seccion for e in elementos if e.seccion), None)
    return {
        "pagina_inicio": min(paginas) if paginas else None,
        "pagina_fin": max(paginas) if paginas else None,
        "seccion": seccion,
        "es_imagen": any(e.es_imagen for e in elementos),
        "dentro_de_anexo": any(e.dentro_de_anexo for e in elementos),
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
        es_imagen=bool(meta.get("es_imagen")),
        dentro_de_anexo=bool(meta.get("dentro_de_anexo")),
    )


# ---------------------------------------------------------------------------
# Chunking por tipo de segmento.
# ---------------------------------------------------------------------------


def _agrupar_leaves_por_root(
    leaves: list[TextNode],
    all_nodes: list[TextNode],
    root_ids: set[str],
) -> dict[str, list[TextNode]]:
    """Devuelve {root_id: [leaves descendientes]} en una sola pasada por nodo.

    Recorre la cadena PARENT de cada hoja hasta encontrar un root_id conocido
    o agotar la profundidad máxima.
    """
    por_id = {n.node_id: n for n in all_nodes}
    grupos: dict[str, list[TextNode]] = {rid: [] for rid in root_ids}
    for leaf in leaves:
        actual: TextNode | None = leaf
        for _ in range(_MAX_PROFUNDIDAD_PARENT):
            if actual is None:
                break
            rel = actual.relationships.get(NodeRelationship.PARENT)
            if rel is None:
                break
            if rel.node_id in root_ids:
                grupos[rel.node_id].append(leaf)
                break
            actual = por_id.get(rel.node_id)
    return grupos


def _chunkear_prosa(segmento: _Segmento) -> list[Chunk]:
    """Chunkea un segmento de prosa con HierarchicalNodeParser.

    Devuelve los chunks parent seguidos de sus children. Si el texto es
    demasiado corto para que LlamaIndex produzca un child distinto, solo se
    emite el parent (con parent_id="" para que se indexe directamente con
    embeddings).
    """
    texto = _texto_segmento(segmento.elementos)
    if not texto.strip():
        return []

    metadata = _metadata_segmento(segmento.elementos)
    doc = Document(text=texto, metadata=metadata)
    # Excluimos los metadatos del cálculo de tamaño: los gestionamos nosotros
    # en el dataclass Chunk; LlamaIndex no debería contarlos como texto.
    doc.excluded_llm_metadata_keys = list(metadata.keys())
    doc.excluded_embed_metadata_keys = list(metadata.keys())

    parser = _get_parser()
    nodes = parser.get_nodes_from_documents([doc])

    root_nodes = get_root_nodes(nodes)
    leaf_nodes = get_leaf_nodes(nodes)
    root_ids = {p.node_id for p in root_nodes}
    leaves_por_root = _agrupar_leaves_por_root(leaf_nodes, nodes, root_ids)

    chunks: list[Chunk] = []
    # Emitimos cada parent seguido de sus children para que el JSON serializado
    # se lea en orden narrativo.
    for parent in root_nodes:
        chunks.append(_nodo_a_chunk(parent, nivel="parent", parent_id=None))
        # Evita emitir un child idéntico al parent (puede pasar con textos muy cortos).
        contenido_parent = parent.get_content()
        for leaf in leaves_por_root.get(parent.node_id, []):
            if leaf.get_content() != contenido_parent:
                chunks.append(_nodo_a_chunk(leaf, nivel="child", parent_id=parent.node_id))

    return chunks


def _chunkear_tabla(segmento: _Segmento) -> list[Chunk]:
    """Emite una tabla como un único child indivisible sin parent.

    Las tablas son su propio contexto — un parent que solo contuviera la tabla
    sería redundante y gastaría el slot de parent sin aportar información.
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
            es_imagen=metadata["es_imagen"],
            dentro_de_anexo=metadata["dentro_de_anexo"],
        )
    ]


# ---------------------------------------------------------------------------
# API pública.
# ---------------------------------------------------------------------------


def _filtrar_elementos(
    elementos: list[ElementoProcesado],
) -> tuple[list[ElementoProcesado], int, int]:
    """Descarta elementos sin sección o de prosa demasiado corta.

    Las tablas (indivisibles) están exentas de ambos filtros.

    Returns:
        Tupla ``(elementos_validos, num_sin_seccion, num_demasiado_cortos)``.
    """
    validos: list[ElementoProcesado] = []
    sin_seccion = 0
    demasiado_cortos = 0
    for elem in elementos:
        if not elem.indivisible and elem.seccion is None:
            sin_seccion += 1
            continue
        if not elem.indivisible and len(elem.texto) < _LONGITUD_MINIMA_CHARS:
            demasiado_cortos += 1
            continue
        validos.append(elem)
    return validos, sin_seccion, demasiado_cortos


def chunk_jerarquico(elementos: list[ElementoProcesado]) -> list[Chunk]:
    """Orquesta el chunking: filtrar → segmentar → chunkear por tipo → unir en orden.

    Args:
        elementos: Lista plana del paso de extracción de elementos.

    Returns:
        Lista plana de Chunk (parents antes que sus children) en orden de documento.
    """
    elementos, sin_seccion, demasiado_cortos = _filtrar_elementos(elementos)

    if sin_seccion or demasiado_cortos:
        logger.info(
            "chunk_jerarquico: descartados sin_seccion=%d demasiado_cortos=%d (umbral=%d chars) → %d pasan",
            sin_seccion, demasiado_cortos, _LONGITUD_MINIMA_CHARS, len(elementos),
        )

    resultado: list[Chunk] = []
    for segmento in _segmentar(elementos):
        if segmento.tipo == "tabla":
            resultado.extend(_chunkear_tabla(segmento))
        else:
            resultado.extend(_chunkear_prosa(segmento))
    return resultado
