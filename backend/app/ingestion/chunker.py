"""Hierarchical chunking of ElementoProcesado using LlamaIndex.

Produces two chunk levels:
- **child** (~128 tokens): indexed with embeddings. Precise retrieval unit.
- **parent** (~1024 tokens): wider context retrieved by ID when a child is found,
  passed to the LLM for generation.

Uses LlamaIndex HierarchicalNodeParser for prose segments. Tables (indivisible)
are chunked manually as a single child with no parent, because splitting them
by sentence would lose their structure.

Pre-chunking filters applied in ``chunk_jerarquico()``:
- Elements with ``seccion=None`` (cover page, before the first heading).
- Prose elements shorter than ``_LONGITUD_MINIMA_CHARS`` (layout noise).
  Tables are exempt — their length does not indicate irrelevance.
"""
from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field

from llama_index.core.node_parser import HierarchicalNodeParser
from llama_index.core.node_parser.relational.hierarchical import (
    get_leaf_nodes,
    get_root_nodes,
)
from llama_index.core.schema import Document, NodeRelationship, TextNode

from app.config import SETTINGS
from app.ingestion.elements import ElementoProcesado

# Minimum text length (characters) for a prose element to enter the chunker.
# Removes short noise fragments that escaped the filters in elements.py
# (bare document codes, residual headings, etc.).
# Tables are exempt: their length does not indicate irrelevance.
_LONGITUD_MINIMA_CHARS = 20


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
# LlamaIndex parser singleton (expensive to initialise).
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
# Building "segments" from processed elements.
#
# A segment is a contiguous block of elements chunked together:
#  - "prosa": consecutive text elements (logical unit passed to
#    HierarchicalNodeParser).
#  - "tabla": a single indivisible element converted manually without going
#    through the llama_index splitter.
# Section boundaries are respected: a section change opens a new segment so
# that parents do not mix content across sections.
# ---------------------------------------------------------------------------


@dataclass
class _Segmento:
    tipo: str                          # "prosa" | "tabla"
    elementos: list[ElementoProcesado]


def _segmentar(elementos: list[ElementoProcesado]) -> list[_Segmento]:
    """Group elements into contiguous segments of the same type.

    A section change forces a new prose segment, preventing parents from
    mixing content across section boundaries.

    Args:
        elementos: Pre-filtered list of ElementoProcesado.

    Returns:
        List of _Segmento, each typed as "prosa" or "tabla".
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
# Conversion to llama_index Document + aggregated metadata extraction.
# ---------------------------------------------------------------------------


def _metadata_segmento(elementos: list[ElementoProcesado]) -> dict:
    """Metadata attached to each llama_index node.

    These metadata are attached to the Document and inherited by all nodes
    (parents and children) that the splitter produces.
    """
    paginas = [e.pagina for e in elementos if e.pagina is not None] # Page numbers spanned by the elements.
    seccion = next((e.seccion for e in elementos if e.seccion), None) # First non-empty section; all elements in a segment share the same section.
    tipos = list(dict.fromkeys(e.tipo_elemento for e in elementos)) # Element types, deduplicated while preserving order.
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
# Chunking each segment type.
# ---------------------------------------------------------------------------


def _chunkear_prosa(segmento: _Segmento) -> list[Chunk]:
    """Chunk a prose segment using HierarchicalNodeParser.

    Returns parent chunks followed by their children. If the text is too short
    for LlamaIndex to produce a distinct child, only the parent is emitted
    (with parent_id="" so it is indexed directly with embeddings).
    """
    texto = _texto_segmento(segmento.elementos)
    if not texto.strip():
        return []

    metadata = _metadata_segmento(segmento.elementos)
    doc = Document(text=texto, metadata=metadata)
    # Exclude metadata from size calculation: we manage it ourselves in
    # the Chunk dataclass; LlamaIndex should not count it as text.
    doc.excluded_llm_metadata_keys = list(metadata.keys())
    doc.excluded_embed_metadata_keys = list(metadata.keys())

    parser = _get_parser()
    nodes = parser.get_nodes_from_documents([doc])

    # Split by level: root nodes = parents; leaf nodes = children.
    root_nodes = get_root_nodes(nodes)
    leaf_nodes = get_leaf_nodes(nodes)

    chunks: list[Chunk] = []

    # Emit each parent followed by its children so the serialised JSON reads
    # in narrative order.
    for parent in root_nodes:
        chunks.append(_nodo_a_chunk(parent, nivel="parent", parent_id=None))
        # Children (actually grandchildren — the second level of HierarchicalNodeParser
        # are the leaves). Filter those belonging to this parent by following the
        # PARENT relationship up to the root.
        for leaf in leaf_nodes:
            if _es_descendiente(leaf, parent.node_id, nodes):
                if leaf.get_content() != parent.get_content():  # Avoid emitting a child identical to the parent (can happen with very short texts).
                    chunks.append(
                        _nodo_a_chunk(leaf, nivel="child", parent_id=parent.node_id)
                    )

    return chunks


def _es_descendiente(leaf: TextNode, root_id: str, all_nodes: list[TextNode]) -> bool:
    """Walk the PARENT chain up to root_id (or exhaust it)."""
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
    """Emit a table as a single indivisible child chunk with no parent.

    Tables are their own context — a parent containing only the table would be
    redundant and would waste the parent slot with no extra information.
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
# Public API.
# ---------------------------------------------------------------------------


def chunk_jerarquico(elementos: list[ElementoProcesado]) -> list[Chunk]:
    """Orchestrate chunking: filter → segment → chunk by type → merge in order.

    Args:
        elementos: Flat list from the element extraction step.

    Returns:
        Flat list of Chunk objects (parents before their children) in document order.
    """

    # discard cover-page content (before the first heading)
    sin_seccion = [e for e in elementos if e.seccion is None and not e.indivisible]

    # discard prose elements that are too short
    demasiado_cortos = [
        e for e in elementos
        if not e.indivisible and e.seccion is not None and len(e.texto) < _LONGITUD_MINIMA_CHARS
    ]

    elementos = [
        e for e in elementos
        if (e.indivisible or e.seccion is not None)
        and (e.indivisible or len(e.texto) >= _LONGITUD_MINIMA_CHARS)
    ]

    if sin_seccion or demasiado_cortos:
        print(
            f"[chunker] descartados: sin_seccion={len(sin_seccion)} "
            f"demasiado_cortos={len(demasiado_cortos)} "
            f"(umbral={_LONGITUD_MINIMA_CHARS} chars) "
            f"→ {len(elementos)} elementos pasan",
            file=sys.stderr,
        )

    resultado: list[Chunk] = []
    for segmento in _segmentar(elementos):
        if segmento.tipo == "tabla":
            resultado.extend(_chunkear_tabla(segmento))
        else:
            resultado.extend(_chunkear_prosa(segmento))
    return resultado
