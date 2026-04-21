# Design: Codebase Cleanup & Documentation

**Date:** 2026-04-21
**Scope:** Folder rename, uniform comments, README rebuild
**Branch:** beta_test_ingesta

---

## 1. Folder and File Renames

All renames are within `backend/app/`. All internal imports are updated in the same step.

| Current path | New path |
|---|---|
| `backend/app/procesamiento/` | `backend/app/ingestion/` |
| `backend/app/servicios/` | `backend/app/rag/` |
| `ingestion/elementos.py` | `ingestion/elements.py` |
| `ingestion/patrones.py` | `ingestion/patterns.py` |
| All other files in both modules | Same name, new folder |

No frontend changes. Scripts in `backend/scripts/` are updated to use the new import paths.

---

## 2. Comment Style

### Python — Google-style docstrings

Applied to every public function and class. Format:

```python
def function_name(param: type) -> return_type:
    """One-line summary.

    Args:
        param: Description.

    Returns:
        Description of the return value.
    """
```

Inline comments only for non-obvious WHY (design decisions, workarounds, constraints).
Remove comments that merely restate what the code does.

### TypeScript — inline only

No JSDoc. Brief English inline comments where logic is non-obvious.
Interface fields in `types.ts` get a one-line comment if the name is not self-explanatory.

---

## 3. README Structure

Language: English. Target: developer GitHub profile.

Sections:
1. **Header** — title, tagline, badges (Python, Next.js, FastAPI, ChromaDB, license)
2. **Overview** — what it is, TFG context, 2–3 sentences
3. **Architecture** — ASCII pipeline diagram (PDF → Docling → Chunker → ChromaDB ← Hybrid retrieval → Cohere → GPT-4o → SSE → UI)
4. **Tech Stack** — table: component | technology | reason
5. **Project Structure** — annotated folder tree, no sensitive filenames or client IDs
6. **Quick Start** — prerequisites, `.env.example` with placeholder values, backend, frontend, ingest
7. **Ingestion Pipeline** — Docling parser, hierarchical chunker (parent/child), embedding prefix strategy
8. **Retrieval Pipeline** — dual query rewriting, hybrid vector+BM25, Cohere rerank, parent expansion
9. **Evaluation** — TruLens RAG triad (CR, AR, GR), how to run
10. **Roadmap** — query router, POST /ingest endpoint, document-level pre-filter

### Sensitive data policy
- No API keys or placeholder values that reveal key names beyond what's in `.env.example`
- No client project IDs or names
- No internal filenames with numeric project codes
- `.env.example` uses `your_key_here` placeholders
