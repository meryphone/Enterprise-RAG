# Codebase Cleanup & Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename backend modules to English, add uniform Google-style docstrings to all Python files, add brief English inline comments to TypeScript, and write a developer-portfolio README.

**Architecture:** Three independent layers — (1) structural rename + import updates, (2) docstring/comment pass on all source files, (3) new documentation files. Each layer produces its own commit.

**Tech Stack:** Python 3.13 / FastAPI / Next.js 14 / TypeScript / ChromaDB / Cohere / OpenAI GPT-4o

---

## File Map

| Action | Path |
|---|---|
| Rename dir | `backend/app/procesamiento/` → `backend/app/ingestion/` |
| Rename dir | `backend/app/servicios/` → `backend/app/rag/` |
| Rename file | `ingestion/elementos.py` → `ingestion/elements.py` |
| Rename file | `ingestion/patrones.py` → `ingestion/patterns.py` |
| Modify | All `.py` files with `app.procesamiento` or `app.servicios` imports |
| Modify | `backend/app/config.py` |
| Modify | `backend/app/main.py` |
| Modify | `backend/app/api/health.py`, `projects.py`, `query.py` |
| Modify | `backend/app/ingestion/*.py` (7 files) |
| Modify | `backend/app/rag/*.py` (3 files) |
| Modify | `frontend/lib/types.ts`, `frontend/lib/api.ts` |
| Create | `.env.example` |
| Replace | `README.md` |

---

### Task 1: Rename folders and files

**Files:** `backend/app/procesamiento/` → `backend/app/ingestion/`, `backend/app/servicios/` → `backend/app/rag/`

- [ ] **Step 1: Run git mv for all renames**

```bash
git mv backend/app/procesamiento backend/app/ingestion
git mv backend/app/ingestion/elementos.py backend/app/ingestion/elements.py
git mv backend/app/ingestion/patrones.py backend/app/ingestion/patterns.py
git mv backend/app/servicios backend/app/rag
```

- [ ] **Step 2: Verify the resulting structure**

```bash
ls backend/app/ingestion/
ls backend/app/rag/
```

Expected `ingestion/`: `__init__.py  chunker.py  elements.py  parser.py  pipeline.py  patterns.py  prompts.py  vision.py`
Expected `rag/`: `__init__.py  query.py  retrieval.py  vector_store.py`

- [ ] **Step 3: Commit rename**

```bash
git add -A
git commit -m "refactor: rename procesamiento→ingestion, servicios→rag, elementos→elements, patrones→patterns"
```

---

### Task 2: Update all Python imports

**Files:** Every `.py` file in `backend/` that imports from `app.procesamiento` or `app.servicios`.

- [ ] **Step 1: Replace module path references with sed**

```bash
find backend -name "*.py" | xargs sed -i \
  -e 's/from app\.procesamiento/from app.ingestion/g' \
  -e 's/import app\.procesamiento/import app.ingestion/g' \
  -e 's/from app\.servicios/from app.rag/g' \
  -e 's/import app\.servicios/import app.rag/g'
```

- [ ] **Step 2: Replace renamed module symbol references**

```bash
find backend -name "*.py" | xargs sed -i \
  -e 's/ingestion\.elementos/ingestion.elements/g' \
  -e 's/ingestion\.patrones/ingestion.patterns/g' \
  -e 's/from app\.ingestion\.elementos/from app.ingestion.elements/g' \
  -e 's/from app\.ingestion\.patrones/from app.ingestion.patterns/g'
```

- [ ] **Step 3: Fix the module alias in pipeline.py**

In `backend/app/ingestion/pipeline.py`, the two import lines and all usages of `mod_elementos` must become:

```python
from app.ingestion import elements as mod_elements
from app.ingestion import parser as mod_parser
from app.ingestion.chunker import Chunk, chunk_jerarquico
from app.ingestion.elements import MetadatosDocumento
```

And every occurrence of `mod_elementos.` in that file becomes `mod_elements.`:
```bash
sed -i 's/mod_elementos\./mod_elements./g' backend/app/ingestion/pipeline.py
sed -i 's/as mod_elementos/as mod_elements/g' backend/app/ingestion/pipeline.py
```

- [ ] **Step 4: Fix the test file import paths**

In `backend/tests/test_query.py`, update:
```python
# Old:
from app.servicios.retrieval import ChunkRecuperado
from app.servicios.query import _expandir_parents, _construir_contexto
# ...
with patch("app.servicios.query.get_chroma", ...):

# New:
from app.rag.retrieval import ChunkRecuperado
from app.rag.query import _expandir_parents, _construir_contexto
# ...
with patch("app.rag.query.get_chroma", ...):
```

```bash
sed -i \
  -e 's/app\.servicios\.retrieval/app.rag.retrieval/g' \
  -e 's/app\.servicios\.query/app.rag.query/g' \
  backend/tests/test_query.py
```

- [ ] **Step 5: Verify imports resolve correctly**

```bash
cd backend && python -c "from app.main import app; print('OK')"
```

Expected output: `OK`

- [ ] **Step 6: Run existing tests**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: all tests pass (4 tests in test_query.py).

- [ ] **Step 7: Commit import updates**

```bash
git add -A
git commit -m "refactor: update all imports after module rename"
```

---

### Task 3: Docstrings — backend core and API layer

**Files:** `backend/app/config.py`, `backend/app/main.py`, `backend/app/api/health.py`, `backend/app/api/projects.py`, `backend/app/api/query.py`

- [ ] **Step 1: Update module docstring and add field comments in config.py**

Replace the existing module docstring at the top of `backend/app/config.py`:
```python
"""Central configuration loaded from environment variables.

All settings are read once at import time via ``Settings.from_env()``.
Production (Azure) swaps OpenAI direct calls for Azure OpenAI Service;
no other code needs to change.
"""
```

Add inline English comments to the `Settings` dataclass fields (replace existing Spanish ones):
```python
@dataclass(frozen=True)
class Settings:
    env: str                        # "local" | "production"
    openai_api_key: str | None      # OpenAI key (dev) or None when absent
    llm_model: str                  # Chat model for generation and vision
    embedding_model: str            # Embedding model — identical in dev and prod
    child_chunk_tokens: int         # Target token size for child chunks
    parent_chunk_tokens: int        # Target token size for parent chunks
    enable_vision: bool             # Whether to call GPT-4o vision for images/tables
    chroma_api_key: str | None      # ChromaDB Cloud API key
    chroma_tenant: str | None       # ChromaDB Cloud tenant ID
    chroma_database: str            # ChromaDB database name
    cohere_api_key: str | None      # Cohere API key for reranking
    cohere_rerank_model: str        # Cohere rerank model identifier
    retrieval_top_k: int            # Candidate pool size after hybrid fusion
    retrieval_top_n: int            # Final results returned after rerank
    retrieval_peso_vector: float    # Weight for vector score in fusion (0–1)
    retrieval_peso_bm25: float      # Weight for BM25 score in fusion (0–1)
```

- [ ] **Step 2: Add module docstring to main.py**

Replace the existing docstring at the top of `backend/app/main.py`:
```python
"""FastAPI application entry point.

Registers API routers and CORS middleware. Business logic lives in
``app.ingestion``, ``app.rag``, and ``app.api``; this file only wires them up.
"""
```

- [ ] **Step 3: Update api/health.py**

Replace the full content of `backend/app/api/health.py`:
```python
"""Health-check endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Return service liveness status."""
    return {"status": "ok"}
```

- [ ] **Step 4: Update api/projects.py**

Replace the full content of `backend/app/api/projects.py`:
```python
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
```

- [ ] **Step 5: Update api/query.py**

Replace the full content of `backend/app/api/query.py`:
```python
"""Query endpoint — streams RAG responses via Server-Sent Events."""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.rag.query import ejecutar_query

router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    proyecto_id: str | None = None
    empresa: str = "intecsa"
    tipo_doc: str | None = None


@router.post("/query")
async def query(req: QueryRequest) -> StreamingResponse:
    """Execute a RAG query and stream the response as SSE.

    Event types emitted: ``token`` (incremental text), ``sources`` (citations
    JSON array), ``done`` (stream end), ``error`` (on failure).
    """
    return StreamingResponse(
        ejecutar_query(
            query=req.query,
            proyecto_id=req.proyecto_id,
            empresa=req.empresa,
            tipo_doc=req.tipo_doc,
        ),
        media_type="text/event-stream",
    )
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/main.py backend/app/api/
git commit -m "docs: add English docstrings to config, main, and API layer"
```

---

### Task 4: Docstrings — ingestion layer

**Files:** `backend/app/ingestion/patterns.py`, `backend/app/ingestion/elements.py`, `backend/app/ingestion/parser.py`, `backend/app/ingestion/chunker.py`, `backend/app/ingestion/pipeline.py`, `backend/app/ingestion/vision.py`, `backend/app/ingestion/prompts.py`

- [ ] **Step 1: Update patterns.py module docstring and section comments**

Replace the module docstring and all Spanish section headers in `backend/app/ingestion/patterns.py`:

```python
"""Compiled regular expressions shared across the ingestion pipeline.

Centralised here so they are compiled once and easy to tune or test in isolation.
"""
import re

# ── Document structure ────────────────────────────────────────────────────────

# Annex sections — flags content as lower-priority during reranking.
# Matches only when ANNEX/ANEXO appears at the start of the heading or at the
# end with an identifier (e.g. "ANNEX I"), to avoid false positives on titles
# that merely reference an annex.
PATRON_ANEXO = re.compile(...)  # keep existing regex body unchanged

# Table-of-contents sections — content is discarded during element extraction.
PATRON_INDICE = re.compile(...)  # keep existing regex body unchanged

# ── Corporate page header ─────────────────────────────────────────────────────

# Repeated header block on every page (e.g. "EDICION 6  HOJA 3 DE 10").
# Two variants: with explicit EDICION/EDITION keyword, or doc-code + page counter.
PATRON_CABECERA = re.compile(...)  # keep existing regex body unchanged

# ── Document title ────────────────────────────────────────────────────────────

# Candidate SectionHeaderItem for the document title: starts with an uppercase
# letter and contains at least 10 allowed characters.
PATRON_TITULO = re.compile(...)  # keep existing regex body unchanged

# ── Section title normalisation ───────────────────────────────────────────────

# Docling sometimes omits the space between a section number and its title:
# "3.NOTES" → normalised to "3. NOTES".
PATRON_NUMERO_TITULO = re.compile(...)  # keep existing regex body unchanged

# ── Repeated page headers/footers ────────────────────────────────────────────

# Applied to both SectionHeaderItem and TextItem to discard layout noise:
# page numbers, edition tokens, date strings, standalone document codes, etc.
PATRON_PIE_PAGINA = re.compile(...)  # keep existing regex body unchanged

# ── Edition number extraction ─────────────────────────────────────────────────

PATRON_EDICION = re.compile(...)      # keep existing regex body unchanged
PATRON_SOLO_NUMERO = re.compile(...)  # keep existing regex body unchanged

# ── Degraded table detection ─────────────────────────────────────────────────

# Merged cells rendered as excessive whitespace between pipes in Markdown.
PATRON_TABLA_DEGRADADA = re.compile(...)  # keep existing regex body unchanged

# ── Page header tokens ────────────────────────────────────────────────────────

# Standalone document code (e.g. PR-01, IT-TU-16, 13187-IT-01).
PATRON_CODIGO_DOC = re.compile(...)  # keep existing regex body unchanged
```

**Important:** only replace the module docstring and the `# ── ... ──` section comment lines. Do NOT touch the regex bodies themselves.

- [ ] **Step 2: Update elements.py module docstring and key function docstrings**

Replace the module docstring in `backend/app/ingestion/elements.py`:
```python
"""Element extraction from a parsed DoclingDocument.

Iterates the items of a DoclingDocument and converts them into a flat list of
ElementoProcesado — the unit the chunker consumes. Decides per element type
what to do: pass text as-is, export tables to Markdown, describe images with
GPT-4o vision, and apply the text-image merge rule.

No chunks are produced here; only elements ready to be chunked.
"""
```

Update `extraer_metadatos_documento` docstring (find and replace):
```python
def extraer_metadatos_documento(doc: DoclingDocument) -> MetadatosDocumento:
    """Extract title and edition from the first items of the document.

    - **Title**: first SectionHeaderItem in the first 35 items that matches
      PATRON_TITULO (long uppercase text, more than one word).
    - **Edition**: first item containing EDICION/EDITION. If the number follows
      on the same item ("EDICION 6 HOJA 2 DE 10"), it is extracted directly;
      otherwise the next numeric-only item is used.

    Args:
        doc: Parsed DoclingDocument from Docling.

    Returns:
        MetadatosDocumento with title and edition populated where found.
    """
```

Update `procesar_documento` docstring:
```python
def procesar_documento(
    doc: DoclingDocument,
    es_anexo_documento: bool = False,
) -> list[ElementoProcesado]:
    """Convert all items in a DoclingDocument into a flat list of ElementoProcesado.

    Args:
        doc: Parsed DoclingDocument.
        es_anexo_documento: True when the whole file is classified as an annex,
            so all elements start with dentro_de_anexo=True.

    Returns:
        List of ElementoProcesado in document order, ready for chunking.
    """
```

- [ ] **Step 3: Update parser.py module docstring and function docstrings**

Replace the module docstring in `backend/app/ingestion/parser.py`:
```python
"""Docling PDF parser wrapper.

Isolates the rest of the pipeline from Docling's API. Receives a PDF path and
returns a DoclingDocument with images materialised in memory (required for
GPT-4o vision calls downstream).

The DocumentConverter is initialised once as a process-level singleton because
startup takes ~30 s (model loading). Subsequent calls reuse the cached instance.
"""
```

Add/replace the `get_converter` docstring:
```python
def get_converter() -> DocumentConverter:
    """Return the process-level Docling converter singleton, building it on first call."""
```

Add/replace the `parse_pdf` docstring (add this function's docstring if missing):
```python
def parse_pdf(path: Path) -> DoclingDocument:
    """Parse a PDF and return a DoclingDocument with images in memory.

    Args:
        path: Absolute path to the PDF file.

    Returns:
        Parsed DoclingDocument ready for element extraction.
    """
```

- [ ] **Step 4: Update chunker.py module docstring and key function docstrings**

Replace the module docstring in `backend/app/ingestion/chunker.py`:
```python
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
```

Update `chunk_jerarquico` docstring:
```python
def chunk_jerarquico(elementos: list[ElementoProcesado]) -> list[Chunk]:
    """Orchestrate chunking: filter → segment → chunk by type → merge in order.

    Args:
        elementos: Flat list from the element extraction step.

    Returns:
        Flat list of Chunk objects (parents before their children) in document order.
    """
```

Update `_segmentar` docstring:
```python
def _segmentar(elementos: list[ElementoProcesado]) -> list[_Segmento]:
    """Group elements into contiguous segments of the same type.

    A section change forces a new prose segment, preventing parents from
    mixing content across section boundaries.

    Args:
        elementos: Pre-filtered list of ElementoProcesado.

    Returns:
        List of _Segmento, each typed as "prosa" or "tabla".
    """
```

Update `_chunkear_prosa` docstring:
```python
def _chunkear_prosa(segmento: _Segmento) -> list[Chunk]:
    """Chunk a prose segment using HierarchicalNodeParser.

    Returns parent chunks followed by their children. If the text is too short
    for LlamaIndex to produce a distinct child, only the parent is emitted
    (with parent_id="" so it is indexed directly with embeddings).
    """
```

Update `_chunkear_tabla` docstring:
```python
def _chunkear_tabla(segmento: _Segmento) -> list[Chunk]:
    """Emit a table as a single indivisible child chunk with no parent.

    Tables are their own context — a parent containing only the table would be
    redundant and would waste the parent slot with no extra information.
    """
```

- [ ] **Step 5: Update pipeline.py module docstring**

Replace the module docstring in `backend/app/ingestion/pipeline.py`:
```python
"""Ingestion pipeline orchestrator.

Coordinates the four steps described in CLAUDE.md:
    1. Parse the PDF with Docling (parser.py).
    2. Extract document-level metadata from the header (elements.py).
    3. Process each element by type → list of ElementoProcesado (elements.py).
    4. Hierarchical chunking → parents and children with metadata (chunker.py).

Public interface:
    ingestar_pdf(path, metadatos_admin) → DocumentoIngerido
    documento_a_dict(documento)         → dict (JSON-serialisable)
"""
```

Update `ingestar_pdf` docstring:
```python
def ingestar_pdf(path: Path, metadatos_admin: MetadatosAdministrador) -> DocumentoIngerido:
    """Run the full ingestion pipeline on a PDF and return the result.

    Args:
        path: Path to the PDF file.
        metadatos_admin: Administrator-supplied metadata (company, project, type, language).

    Returns:
        DocumentoIngerido with all chunks ready for indexing in the vector store.
    """
```

Update `documento_a_dict` docstring:
```python
def documento_a_dict(documento: DocumentoIngerido) -> dict:
    """Serialise a DocumentoIngerido to a JSON-compatible dict.

    Used by ingestion scripts to persist parsed output for inspection.
    """
```

- [ ] **Step 6: Update vision.py module docstring and function docstrings**

Replace the module docstring in `backend/app/ingestion/vision.py`:
```python
"""GPT-4o vision calls for elements that Docling cannot represent as text.

Used in two scenarios:
- Degraded tables (merged cells detected by PATRON_TABLA_DEGRADADA): the table
  image is sent to GPT-4o with PROMPT_TABLA_DEGRADADA for a faithful Markdown
  transcription.
- Standalone images (when ENABLE_VISION=1): described with PROMPT_DESCRIPCION_IMAGEN.

Image retrieval priority for tables:
    1. Docling crop (item.get_image) — best quality when available.
    2. Manual crop using the bounding box from prov on the page image.
    3. Full page image — last resort.
"""
```

Update `describir_tabla` docstring:
```python
def describir_tabla(item: TableItem, doc: DoclingDocument, seccion: str | None) -> str | None:
    """Describe a degraded table via GPT-4o vision.

    Returns the Markdown transcription produced by the LLM, or None if no
    image could be obtained or the API call fails.

    Args:
        item: Docling TableItem with prov metadata.
        doc: Parent DoclingDocument (used to retrieve page images).
        seccion: Current section heading, used to select the prompt variant.
    """
```

- [ ] **Step 7: Update prompts.py module docstring**

Replace the module docstring at the top of `backend/app/ingestion/prompts.py`:
```python
"""All LLM prompts used by the ingestion and RAG pipelines.

Centralised in one module so that prompt changes can be reviewed as a unit
and do not require touching pipeline logic.

Prompts exported:
    PROMPT_DESCRIPCION_IMAGEN    — GPT-4o vision: image description for indexing
    PROMPT_TABLA_DEGRADADA       — GPT-4o vision: faithful Markdown for degraded tables
    PROMPT_TABLA_SIN_SECCION     — GPT-4o vision: table without a preceding section heading
    PROMPT_TITULO_CABECERA       — GPT-4o vision: extract document title from header image
    PROMPT_REESCRITURA_QUERY     — GPT-4o-mini: dual query rewriting (VECTOR + BM25 lines)
    SYSTEM_PROMPT                — GPT-4o system prompt for RAG generation
    SYSTEM_PROMPT_EVAL           — Variant without citation markers for TruLens evaluation
"""
```

- [ ] **Step 8: Commit ingestion layer docstrings**

```bash
git add backend/app/ingestion/
git commit -m "docs: add English docstrings to ingestion layer"
```

---

### Task 5: Docstrings — RAG layer

**Files:** `backend/app/rag/vector_store.py`, `backend/app/rag/retrieval.py`, `backend/app/rag/query.py`

- [ ] **Step 1: Update vector_store.py module docstring and key function docstrings**

Replace the module docstring in `backend/app/rag/vector_store.py`:
```python
"""Vector store abstraction layer.

Dev local  → ChromaDB Cloud.
Production → Azure AI Search (swap implementation here only).

Business logic (ingestion pipeline, retrieval) imports this module exclusively
and never references the underlying client directly.

Storage strategy (ChromaDB):
- Collection ``{name}``           → child chunks with embeddings (searched).
- Collection ``{name}__parents``  → parent chunks without embeddings (fetched by ID
                                    to expand context before generation).
- Tables (parent_id=None/empty) are stored only in the main collection.

Embedding text differs from stored text. The embedding includes document-level
context prefixes (type, code, title, section) to anchor the chunk semantically.
The stored text is the raw chunk text that the LLM will read.
"""
```

Update `indexar_documento` docstring:
```python
def indexar_documento(documento: "DocumentoIngerido") -> dict[str, int]:
    """Index all chunks of a document into ChromaDB.

    Children are embedded and stored in the main collection.
    Parents are stored without embeddings in the ``__parents`` collection.
    Orphan parents (no children generated, parent_id="") are embedded and
    stored in the main collection directly.

    Args:
        documento: Fully-ingested document with chunks.

    Returns:
        Dict with keys ``"children"`` and ``"parents"`` showing counts added.
    """
```

Update `colecciones_disponibles` docstring:
```python
def colecciones_disponibles() -> list[str]:
    """Return names of all non-parent collections in ChromaDB.

    Filters out ``__parents`` collections, which are implementation details
    not visible to the API layer.
    """
```

Update `nombre_coleccion` docstring:
```python
def nombre_coleccion(empresa: str, proyecto_id: str | None) -> str:
    """Return the ChromaDB collection name for a given scope.

    Args:
        empresa: Company identifier (e.g. ``"intecsa"``).
        proyecto_id: Project code, or None for the global corporate corpus.

    Returns:
        ``"intecsa"`` for the global corpus, ``"{proyecto_id}_{empresa}"`` for projects.
    """
```

- [ ] **Step 2: Update retrieval.py module docstring and key function docstrings**

Replace the module docstring in `backend/app/rag/retrieval.py`:
```python
"""Hybrid retrieval pipeline with Cohere reranking.

Pipeline:
    1. Dual query rewriting via GPT-4o-mini → VECTOR and BM25 variants.
    2. Dense vector search (ChromaDB, cosine) using the VECTOR query.
    3. Sparse BM25 search (rank-bm25, in-memory) using the BM25 query.
    4. Weighted score fusion (normalised min-max).
    5. Optional metadata filter on ``tipo_doc``.
    6. Cohere rerank on the top-K fusion candidates → top-N final results.

BM25 index is built lazily on first query per collection and cached in memory.
Invalidate with ``invalidar_cache_bm25(coleccion)`` after re-ingesting documents.

Public API: ``recuperar(query, proyecto_id, empresa, ...)``
"""
```

Update `_reescribir_query` docstring:
```python
def _reescribir_query(query: str) -> tuple[str, str]:
    """Produce two query variants via GPT-4o-mini for hybrid retrieval.

    - **VECTOR**: bilingual semantic reformulation (Spanish + English key terms)
      for dense embedding search. Always bilingual to support cross-lingual corpora.
    - **BM25**: keyword bag with synonym expansion and English translations for
      lexical search.

    Cohere reranking always uses the original query for maximum fidelity.
    Falls back to the original query on any API failure.

    Args:
        query: Original user question.

    Returns:
        Tuple of (query_vector, query_bm25).
    """
```

Update `recuperar` docstring:
```python
def recuperar(
    query: str,
    proyecto_id: str | None,
    empresa: str = "intecsa",
    tipo_doc: str | None = None,
    top_k: int | None = None,
    top_n: int | None = None,
    peso_vector: float | None = None,
    peso_bm25: float | None = None,
) -> list[ChunkRecuperado]:
    """Retrieve the most relevant chunks for a query within the given scope.

    Args:
        query: User question in natural language (any language).
        proyecto_id: Project code, or None for the global corpus.
        empresa: Company identifier; defaults to "intecsa".
        tipo_doc: Optional metadata filter (e.g. "procedimiento").
        top_k: Candidate pool size after fusion (default from settings).
        top_n: Final results after rerank (default from settings).
        peso_vector: Vector score weight in fusion (default from settings).
        peso_bm25: BM25 score weight in fusion (default from settings).

    Returns:
        List of ChunkRecuperado ordered by descending Cohere relevance score.
    """
```

Update `invalidar_cache_bm25` docstring:
```python
def invalidar_cache_bm25(coleccion: str | None = None) -> None:
    """Invalidate the in-memory BM25 index cache.

    Call after indexing new documents so the next query rebuilds the index.

    Args:
        coleccion: Collection name to invalidate, or None to clear all caches.
    """
```

Translate remaining Spanish inline comments in `recuperar()` to English:
- `# Vector usa la reformulación semántica; BM25 usa la bolsa de palabras.` →
  `# Vector search uses the semantic reformulation; BM25 uses the keyword bag.`
- `# ── 1. Búsqueda vectorial (reformulación semántica) ──` →
  `# ── 1. Vector search (semantic reformulation) ──────────────────────────────`
- `# ── 2. Búsqueda BM25 ─────` →
  `# ── 2. BM25 search ─────────────────────────────────────────────────────────`
- `# ── 3. Fusión de scores normalizados ─────` →
  `# ── 3. Normalised score fusion ──────────────────────────────────────────────`
- `# ── 4. Rerank con Cohere ─────` →
  `# ── 4. Cohere rerank ─────────────────────────────────────────────────────────`
- `# ── 5. Recuperar partes de tabla descartadas por Cohere ──` →
  `# ── 5. Re-include table parts discarded by Cohere ───────────────────────────`
- `# Pasamos de distancia del coseno en [0, 2] → similitud en [-1, 1]` →
  `# Convert ChromaDB cosine distance [0, 2] to similarity [-1, 1].`
- The `cache_docs` comment at the end of the fusion loop: remove (it restates what the code does).

- [ ] **Step 3: Update rag/query.py module docstring and key function docstrings**

Replace the module docstring in `backend/app/rag/query.py`:
```python
"""RAG generation orchestrator for POST /query.

Coordinates retrieval → parent expansion → table merging → context building
→ GPT-4o streaming. Emits SSE events consumed by the frontend.

SSE event types:
    token   — incremental text token from GPT-4o
    sources — JSON array of source citations (emitted after last token)
    done    — stream closed normally
    error   — LLM or network error occurred
"""
```

Update `_expandir_parents` docstring:
```python
def _expandir_parents(
    chunks: list[ChunkRecuperado],
    coleccion: str,
) -> list[ChunkRecuperado]:
    """Replace child chunks with their parent chunks for wider LLM context.

    Fetches all required parents in a single ChromaDB batch call.
    Tables (parent_id='') are passed through unchanged — the table itself
    is its own complete context.
    Deduplicates by parent_id so two children sharing a parent yield one entry.

    Args:
        chunks: Retrieval results from ``recuperar()``.
        coleccion: Base collection name (used to locate ``{coleccion}__parents``).

    Returns:
        List of ChunkRecuperado with children replaced by their parents.
    """
```

Update `_fusionar_partes_tabla` docstring:
```python
def _fusionar_partes_tabla(chunks: list[ChunkRecuperado]) -> list[ChunkRecuperado]:
    """Merge split table chunks from the same document section into one.

    When the chunker splits a large table, all parts share the same
    nombre_fichero and seccion. This function concatenates them so the LLM
    sees the complete table. Non-table chunks are passed through unchanged.
    """
```

Update `_construir_contexto` docstring:
```python
def _construir_contexto(chunks: list[ChunkRecuperado]) -> str:
    """Wrap each chunk in an XML <fuente> tag with numeric id and source attributes.

    XML is used because GPT-4o treats it as a structural delimiter rather than
    citable text, reducing hallucinated metadata in responses.
    Full metadata (doc, title, version, section, pages, score) is sent separately
    in the SSE ``sources`` event, not embedded in the LLM context.
    """
```

Update `_stream_respuesta` docstring:
```python
async def _stream_respuesta(
    query: str,
    contexto: str,
    fuentes: list[dict],
) -> AsyncGenerator[str, None]:
    """Call GPT-4o with streaming and emit SSE events.

    Emits ``token`` events per chunk, then ``sources`` and ``done`` on completion.
    Emits ``error`` if the LLM stream raises an exception.
    """
```

Update `ejecutar_query` docstring:
```python
async def ejecutar_query(
    query: str,
    proyecto_id: str | None,
    empresa: str = "intecsa",
    tipo_doc: str | None = None,
) -> AsyncGenerator[str, None]:
    """Entry point for POST /query. Runs the full RAG pipeline and streams SSE.

    Args:
        query: User question in natural language.
        proyecto_id: Project scope, or None for the global corpus.
        empresa: Company identifier.
        tipo_doc: Optional document type filter.

    Yields:
        SSE-formatted strings (``data: {...}\\n\\n``).
    """
```

- [ ] **Step 4: Commit RAG layer docstrings**

```bash
git add backend/app/rag/ backend/app/ingestion/
git commit -m "docs: add English docstrings to RAG layer and translate inline comments"
```

---

### Task 6: TypeScript comments

**Files:** `frontend/lib/types.ts`, `frontend/lib/api.ts`

- [ ] **Step 1: Update types.ts with field comments**

Replace the content of `frontend/lib/types.ts`:
```typescript
/** A queryable document collection (corporate corpus or client project). */
export interface Scope {
  coleccion: string;       // ChromaDB collection name
  proyecto_id: string | null;
  empresa: string;
  label: string;           // Human-readable display name
  docs?: number;           // Optional document count
  updated?: string;        // Optional last-updated date
  scope_desc?: string;
}

/** A source chunk cited by the LLM in its response. */
export interface SourceRef {
  ref: number;             // Citation index used in the response text ([N])
  doc: string;             // Filename (e.g. "PR-08.pdf")
  titulo: string;          // Document title extracted during ingestion
  version: string;         // Edition/revision number
  seccion: string;         // Section heading where the chunk was found
  pagina_inicio: number;   // -1 when unavailable
  pagina_fin: number;      // -1 when unavailable
  score: number;           // Cohere relevance score [0, 1]
  es_anexo: boolean;       // True when the source is from an annex section
}

/** A single turn in the conversation thread. */
export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];   // Populated when the SSE "sources" event arrives
  streaming?: boolean;     // True while the SSE token stream is open
  timestamp?: string;
}
```

- [ ] **Step 2: Add brief comments to api.ts**

Replace the content of `frontend/lib/api.ts`:
```typescript
import type { Scope, SourceRef } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Fetch all available document scopes from the backend. */
export async function fetchScopes(): Promise<Scope[]> {
  const res = await fetch(`${API_URL}/projects`);
  if (!res.ok) throw new Error("Error cargando scopes");
  return res.json();
}

/**
 * Stream a RAG query over SSE using fetch + ReadableStream.
 * EventSource is not used because it does not support POST requests with a body.
 */
export async function streamQuery(
  query: string,
  scope: Scope,
  onToken: (token: string) => void,
  onSources: (sources: SourceRef[]) => void,
  onDone: () => void,
  onError: (msg: string) => void,
): Promise<void> {
  const res = await fetch(`${API_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      proyecto_id: scope.proyecto_id,
      empresa: scope.empresa,
    }),
  });

  if (!res.ok || !res.body) {
    onError(`Error del servidor: ${res.status}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";  // keep incomplete line for next chunk

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const evt = JSON.parse(line.slice(6));
        if (evt.type === "token") onToken(evt.content);
        else if (evt.type === "sources") onSources(evt.sources);
        else if (evt.type === "done") onDone();
        else if (evt.type === "error") onError(evt.message);
      } catch {
        // Ignore malformed SSE lines
      }
    }
  }
}
```

- [ ] **Step 3: Commit TypeScript comments**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "docs: add English comments to TypeScript lib layer"
```

---

### Task 7: Create .env.example

**Files:** Create `.env.example` at the project root.

- [ ] **Step 1: Create the file**

Create `/home/maria/Escritorio/Enterprise-RAG/.env.example` with this exact content:

```bash
# ── LLM & Embeddings ─────────────────────────────────────────────────────────
OPENAI_API_KEY=your_openai_api_key_here
LLM_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-large

# ── Vector Store (ChromaDB Cloud) ─────────────────────────────────────────────
CHROMA_API_KEY=your_chromadb_api_key_here
CHROMA_TENANT=your_chromadb_tenant_id_here
CHROMA_DATABASE=default

# ── Reranking (Cohere) ────────────────────────────────────────────────────────
COHERE_API_KEY=your_cohere_api_key_here
COHERE_RERANK_MODEL=rerank-multilingual-v3.0

# ── Retrieval Tuning ──────────────────────────────────────────────────────────
RETRIEVAL_TOP_K=30          # Candidate pool size after hybrid fusion
RETRIEVAL_TOP_N=3           # Final results after Cohere rerank
RETRIEVAL_PESO_VECTOR=0.7   # Vector score weight (0–1)
RETRIEVAL_PESO_BM25=0.3     # BM25 score weight (0–1)

# ── Ingestion Pipeline ────────────────────────────────────────────────────────
CHILD_CHUNK_TOKENS=128      # Target token size for child chunks
PARENT_CHUNK_TOKENS=1024    # Target token size for parent chunks
ENABLE_VISION=1             # 1 = call GPT-4o vision for images and degraded tables

# ── Environment ───────────────────────────────────────────────────────────────
ENV=local                   # "local" | "production"
```

- [ ] **Step 2: Verify .env.example is not in .gitignore**

```bash
grep "env.example" .gitignore
```

Expected: no output (`.env.example` should be committed; only `.env` should be ignored).

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs: add .env.example with placeholder values"
```

---

### Task 8: Write README.md

**Files:** Replace `README.md` at the project root.

- [ ] **Step 1: Replace README.md with the following content**

```markdown
# IntecsaRAG

> Enterprise RAG system for querying industrial engineering documentation in natural language.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)
![ChromaDB](https://img.shields.io/badge/ChromaDB-Cloud-E44C60)
![License](https://img.shields.io/badge/License-MIT-green)

## Overview

IntecsaRAG is a production-grade Retrieval-Augmented Generation (RAG) system built for an industrial engineering firm. It enables employees to query technical documentation — procedures, work instructions, and project specifications — in natural language, with responses grounded in cited sources.

The system handles a multilingual corpus (Spanish/English), implements a hierarchical parent-child chunking strategy for precision-context balance, and uses a hybrid retrieval pipeline combining dense vector search with sparse BM25. Built as a Bachelor's thesis project in Computer Science, with a planned deployment on Azure.

---

## Architecture

### Ingestion Pipeline

```
PDF
 │
 ▼
Docling Parser ──────────────────────────────── OCR + TableFormer (accurate mode)
 │                                              Images materialised in memory
 ▼
Element Extraction ──────────────────────────── Per-type processing:
 │   elements.py                                  text → clean + filter noise
 │                                                tables → Markdown export
 │                                                images → GPT-4o description (optional)
 ▼
Hierarchical Chunker ────────────────────────── LlamaIndex HierarchicalNodeParser
 │   chunker.py
 ├── child chunks (~128 tokens) ─────────────── Embedded with context prefixes
 │                                              Stored in {collection}
 └── parent chunks (~1024 tokens) ──────────── Stored without embeddings
                                               in {collection}__parents
```

### Retrieval & Generation Pipeline

```
User query (Spanish or English)
 │
 ▼
Query Rewriting  ─────────────────────────────── GPT-4o-mini
 │   retrieval.py                                VECTOR: bilingual semantic reformulation
 │                                               BM25:   keyword bag with synonym expansion
 │
 ├── VECTOR query ──► Embedding ──► ChromaDB cosine search  ─┐
 │                    (3072-dim)                              │
 │                                                            ▼
 └── BM25 query ───────────────────────────────────────► Score Fusion
                                                         (0.7 vector + 0.3 BM25,
                                                          min-max normalised)
                                                              │
                                                              ▼
                                                       Cohere Rerank
                                                   rerank-multilingual-v3.0
                                                   query = original (unfmt)
                                                              │
                                                              ▼
                                                    Parent Expansion
                                               child → parent context (+~900 tokens)
                                                              │
                                                              ▼
                                                    GPT-4o (streaming)
                                                    XML-tagged context
                                                              │
                                                       SSE → Next.js UI
```

---

## Tech Stack

| Component | Technology | Notes |
|---|---|---|
| Document parsing | [Docling](https://github.com/DS4SD/docling) (IBM) | TableFormer accurate mode, OCR, Markdown tables |
| LLM | GPT-4o | Streaming, vision for degraded tables/images |
| Embeddings | `text-embedding-3-large` (3072-dim) | Identical model in dev and production |
| Vector store | ChromaDB Cloud → Azure AI Search | Swap at `rag/vector_store.py` only |
| Reranker | Cohere `rerank-multilingual-v3.0` | Cross-lingual; always uses original query |
| BM25 | `rank-bm25` | Lazy-built per collection, cached in memory |
| Chunking | LlamaIndex `HierarchicalNodeParser` | 128 / 1024 token child / parent |
| Backend | FastAPI + uvicorn | Async SSE streaming, no WebSocket needed |
| Frontend | Next.js 14 | Custom CSS design system, no UI library |
| Deployment target | Azure Container Apps + Azure Static Web Apps | |

---

## Project Structure

```
enterprise-rag/
├── backend/
│   ├── app/
│   │   ├── api/                  # FastAPI routers
│   │   │   ├── health.py         # GET /health
│   │   │   ├── projects.py       # GET /projects — available scopes
│   │   │   └── query.py          # POST /query — SSE streaming
│   │   ├── ingestion/            # Document parsing & chunking
│   │   │   ├── parser.py         # Docling wrapper (singleton converter)
│   │   │   ├── elements.py       # Per-type element extraction
│   │   │   ├── patterns.py       # Shared compiled regex patterns
│   │   │   ├── chunker.py        # Hierarchical chunking (LlamaIndex)
│   │   │   ├── pipeline.py       # Ingestion orchestrator
│   │   │   ├── vision.py         # GPT-4o vision for degraded tables
│   │   │   └── prompts.py        # All LLM prompts
│   │   ├── rag/                  # Retrieval & generation
│   │   │   ├── vector_store.py   # ChromaDB abstraction layer
│   │   │   ├── retrieval.py      # Hybrid search + Cohere rerank
│   │   │   └── query.py          # RAG orchestrator (streaming SSE)
│   │   ├── config.py             # Settings loaded from .env
│   │   └── main.py               # FastAPI app + CORS + startup hooks
│   ├── scripts/
│   │   ├── ingest_one.py         # Ingest a single PDF
│   │   ├── ingest_beta.py        # Batch ingest for beta corpus
│   │   └── eval_trulens.py       # RAG quality evaluation (TruLens)
│   └── tests/
│       └── test_query.py
├── frontend/
│   ├── app/                      # Next.js App Router
│   ├── components/               # UI components (Sidebar, ChatArea, etc.)
│   └── lib/                      # API client, types, utilities
├── data/
│   └── docs/                     # PDF documents (not committed)
├── .env.example
└── README.md
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Accounts: [OpenAI](https://platform.openai.com), [ChromaDB Cloud](https://trychroma.com), [Cohere](https://cohere.com)

### 1. Clone and configure

```bash
git clone <repo-url>
cd enterprise-rag
cp .env.example .env
# Fill in your API keys in .env
```

### 2. Install backend dependencies

```bash
cd backend
python -m venv ../.venv
source ../.venv/bin/activate   # Windows: ..\.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

### 4. Ingest documents

Place PDF files under `data/docs/` and run:

```bash
# Single document
python backend/scripts/ingest_one.py data/docs/intecsa/PR-01.pdf \
  --empresa intecsa --tipo procedimiento --idioma es

# Client project document
python backend/scripts/ingest_one.py data/docs/projects/PROJECT_ID-IT-01.pdf \
  --empresa <company> --proyecto <project_id> --tipo instruccion_trabajo --idioma en
```

After ingestion, restart the backend to rebuild the BM25 index.

### 5. Start the backend

```bash
cd backend
uvicorn app.main:app --reload
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### 6. Start the frontend

```bash
cd frontend
npm run dev
# UI available at http://localhost:3000
```

---

## Key Design Decisions

### Hierarchical Parent-Child Chunking

Child chunks (~128 tokens) are indexed with embeddings for precise retrieval. When a child is retrieved, its parent chunk (~1024 tokens) is fetched and passed to the LLM instead — providing ~8× more context without polluting the embedding space with long chunks.

Tables are treated as indivisible units: a single child chunk with no parent, since the table is its own complete context.

**Why 1024 tokens for parents?** Tested with 512 tokens: Context Relevance in TruLens evaluation dropped significantly — fragments were too short for questions requiring full-section context.

### Hybrid Retrieval

Vector search captures semantic meaning; BM25 captures exact technical codes (e.g. `PR-01`, `IT-TU-16`) that embedding models tend to dilute. The two signals are combined with min-max normalised scores (default weights: `0.7 vector / 0.3 BM25`).

Query rewriting (GPT-4o-mini) produces separate reformulations optimised for each modality:
- **VECTOR**: bilingual semantic reformulation (always includes English key terms for cross-lingual corpora)
- **BM25**: keyword bag with synonym expansion and English translations

### Multilingual Queries

The corpus includes both Spanish and English documents. The VECTOR query always includes English translations of key terms, so a Spanish question can retrieve English chunks. Cohere's multilingual reranker handles cross-lingual relevance scoring. GPT-4o is instructed to respond in the language of the question regardless of the context language.

### Embedding Prefix Strategy

The text embedded into the vector store differs from the stored chunk text:
```
{doc_type}\n\n{doc_code}\n\n{doc_title}\n\n{section}\n\n{chunk_text}
```
This anchors each chunk to its document and section, reducing the "homologous sections problem" (OBJECT, FUNCTIONS, RESPONSIBILITIES appear in every procedure with nearly identical embeddings).

---

## Evaluation

Uses [TruLens](https://github.com/truera/trulens) to evaluate the RAG triad with GPT-4o as judge:

| Metric | Description |
|---|---|
| **Context Relevance** | Are the retrieved chunks relevant to the question? |
| **Answer Relevance** | Does the response address the question? |
| **Groundedness** | Are all claims in the response supported by the context? |

```bash
cd backend
pip install trulens trulens-providers-openai
python scripts/eval_trulens.py --reset --no-dashboard
```

Rate limit note: OpenAI Tier 1 allows ~30K TPM. Each query consumes ~15-20K tokens (generation + 3 feedback calls). Allow ~18 seconds between queries.

---

## Roadmap

- [ ] **Query Router** — automatic scope inference from the question (entity extraction, confidence threshold, clarification prompt when ambiguous)
- [ ] **POST /ingest** — admin endpoint for uploading PDFs from the UI with metadata validation
- [ ] **Document-level pre-filter** — when the query explicitly mentions a document code (e.g. `PR-01`), pre-filter ChromaDB by `nombre_fichero` before vector search to mitigate the homologous sections problem
- [ ] **Azure migration** — swap ChromaDB for Azure AI Search, OpenAI direct for Azure OpenAI Service

---

## License

MIT
```

- [ ] **Step 2: Commit README**

```bash
git add README.md
git commit -m "docs: rewrite README as developer portfolio — architecture, setup, design decisions"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Rename `procesamiento/` → `ingestion/` and `servicios/` → `rag/` (Task 1)
- ✅ Rename `elementos.py` → `elements.py` and `patrones.py` → `patterns.py` (Task 1)
- ✅ Update all imports after rename (Task 2)
- ✅ Google-style docstrings on all public Python functions/classes (Tasks 3–5)
- ✅ Spanish inline comments translated to English (Tasks 4–5)
- ✅ English TypeScript comments on interfaces and non-obvious logic (Task 6)
- ✅ `.env.example` with placeholder values, no real keys (Task 7)
- ✅ README with architecture diagrams, tech stack, setup, design decisions (Task 8)
- ✅ No client names or project IDs in README
- ✅ No API keys or sensitive filenames in README

**Placeholder scan:** No TBD or TODO left in plan.

**Type consistency:**
- `ChunkRecuperado` used consistently across Tasks 2 and 5.
- `mod_elementos` → `mod_elements` handled both in sed step and manual fix step.
- `DocumentoIngerido` import path updated in Task 2 sed step.
