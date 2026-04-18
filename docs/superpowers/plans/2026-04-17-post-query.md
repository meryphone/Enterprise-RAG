# POST /query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar el endpoint `POST /query` que conecta retrieval → expansión de parents → GPT-4o → respuesta en streaming SSE con fuentes.

**Architecture:** La orquestación vive en `servicios/query.py` (expansión de parents, construcción de contexto, llamada GPT-4o streaming). `main.py` solo define la ruta HTTP y delega. El `SYSTEM_PROMPT` se añade a `prompts.py` como constante centralizada.

**Tech Stack:** FastAPI `StreamingResponse`, OpenAI Python SDK streaming, ChromaDB `get()` para expansión de parents, Pydantic v2 para el request model.

---

## Archivos

| Acción | Archivo | Responsabilidad |
|---|---|---|
| Modificar | `backend/app/procesamiento/prompts.py` | Añadir `SYSTEM_PROMPT` |
| Crear | `backend/app/servicios/query.py` | Orquestación completa |
| Modificar | `backend/app/main.py` | Ruta `POST /query` |
| Crear | `backend/tests/test_query.py` | Tests unitarios de orquestación |

---

### Task 1: Añadir SYSTEM_PROMPT a prompts.py

**Files:**
- Modify: `backend/app/procesamiento/prompts.py`

- [ ] **Step 1: Añadir la constante al final del fichero**

```python
SYSTEM_PROMPT = """Eres un asistente técnico especializado en documentación de ingeniería industrial de INTECSA.

Tu función es responder preguntas técnicas basándote EXCLUSIVAMENTE en la documentación proporcionada. Los documentos incluyen procedimientos, especificaciones técnicas, diagramas P&ID, hojas de datos de equipos, y normativa aplicable.

INSTRUCCIONES CRÍTICAS:
1. Base tus respuestas SOLO en la información proporcionada en el contexto
2. Si la información no está en el contexto, di explícitamente "No encuentro esa información en la documentación proporcionada"
3. Cita siempre la fuente (nombre del documento, sección) de donde extraes la información
4. Preserva códigos técnicos exactos (válvulas, equipos, procedimientos) tal como aparecen
5. Si hay contradicciones entre documentos, menciónalas y indica las fuentes

FORMATO DE RESPUESTA:
- Responde de forma clara y estructurada
- Usa listas numeradas para procedimientos paso a paso
- Incluye valores numéricos exactos cuando estén disponibles (presiones, temperaturas, caudales)
- Si hay tablas relevantes en el contexto, referéncialas

CUANDO RESPONDAS:
- Prioriza información de procedimientos aprobados sobre borradores
- Si hay anexos y documentos principales con info similar, prioriza el documento principal
- Indica si la información proviene de una versión antigua del documento

NO hagas suposiciones técnicas ni completes información que no esté explícita en la documentación."""
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/procesamiento/prompts.py
git commit -m "feat: añadir SYSTEM_PROMPT a prompts.py"
```

---

### Task 2: Crear servicios/query.py — expansión de parents y construcción de contexto

**Files:**
- Create: `backend/app/servicios/query.py`
- Create: `backend/tests/test_query.py`

- [ ] **Step 1: Escribir tests para `_expandir_parents` y `_construir_contexto`**

```python
# backend/tests/test_query.py
from unittest.mock import MagicMock, patch
from app.servicios.retrieval import ChunkRecuperado
from app.servicios.query import _expandir_parents, _construir_contexto


def _chunk(chunk_id, texto, nivel="child", parent_id="pid-1", score=0.9,
           nombre_fichero="doc.pdf", titulo="TITULO", seccion="3. PROC",
           pagina_inicio=4, pagina_fin=5, dentro_de_anexo=False):
    return ChunkRecuperado(
        chunk_id=chunk_id,
        texto=texto,
        score=score,
        metadatos={
            "nivel": nivel,
            "parent_id": parent_id,
            "nombre_fichero": nombre_fichero,
            "titulo_documento": titulo,
            "seccion": seccion,
            "pagina_inicio": pagina_inicio,
            "pagina_fin": pagina_fin,
            "dentro_de_anexo": dentro_de_anexo,
        },
    )


def test_expandir_parents_child_con_parent():
    """Un child con parent_id se sustituye por el texto del parent."""
    chunk = _chunk("child-1", "texto child", nivel="child", parent_id="parent-1")

    mock_col = MagicMock()
    mock_col.get.return_value = {
        "ids": ["parent-1"],
        "documents": ["texto expandido del parent"],
        "metadatas": [chunk.metadatos],
    }
    mock_chroma = MagicMock()
    mock_chroma.get_collection.return_value = mock_col

    with patch("app.servicios.query.get_chroma", return_value=mock_chroma):
        resultado = _expandir_parents([chunk], coleccion="intecsa")

    assert len(resultado) == 1
    assert resultado[0].texto == "texto expandido del parent"


def test_expandir_parents_tabla_pasa_directa():
    """Una tabla (parent_id=='') no se expande."""
    tabla = _chunk("tabla-1", "| col1 | col2 |", nivel="child", parent_id="")

    with patch("app.servicios.query.get_chroma"):
        resultado = _expandir_parents([tabla], coleccion="intecsa")

    assert len(resultado) == 1
    assert resultado[0].texto == "| col1 | col2 |"


def test_expandir_parents_deduplica_mismo_parent():
    """Dos children con el mismo parent_id producen un solo chunk expandido."""
    c1 = _chunk("c1", "child 1", parent_id="shared-parent")
    c2 = _chunk("c2", "child 2", parent_id="shared-parent")

    mock_col = MagicMock()
    mock_col.get.return_value = {
        "ids": ["shared-parent"],
        "documents": ["texto del parent compartido"],
        "metadatas": [c1.metadatos],
    }
    mock_chroma = MagicMock()
    mock_chroma.get_collection.return_value = mock_col

    with patch("app.servicios.query.get_chroma", return_value=mock_chroma):
        resultado = _expandir_parents([c1, c2], coleccion="intecsa")

    assert len(resultado) == 1


def test_construir_contexto_formato():
    """El contexto tiene cabecera numerada y texto del chunk."""
    chunk = _chunk("c1", "El manómetro debe calibrarse a 6 bar.",
                   nombre_fichero="PR-08.pdf", seccion="3. PROCEDIMIENTO",
                   pagina_inicio=4, pagina_fin=4)

    contexto = _construir_contexto([chunk])

    assert "[1]" in contexto
    assert "PR-08.pdf" in contexto
    assert "3. PROCEDIMIENTO" in contexto
    assert "El manómetro debe calibrarse a 6 bar." in contexto
```

- [ ] **Step 2: Ejecutar tests para verificar que fallan**

```bash
cd /home/maria/Escritorio/Enterprise-RAG/backend
python -m pytest tests/test_query.py -v
```

Expected: `ImportError` o `ModuleNotFoundError` — `query.py` no existe aún.

- [ ] **Step 3: Crear `backend/app/servicios/query.py` con las funciones internas**

```python
"""Orquestador de POST /query.

Flujo:
    1. recuperar()           → ChunkRecuperado desde retrieval híbrido + rerank
    2. _expandir_parents()   → sustituir children por su parent (contexto ampliado)
    3. _construir_contexto() → texto numerado [1][2]... para el LLM
    4. _stream_respuesta()   → GPT-4o streaming → eventos SSE
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from openai import AsyncOpenAI

from app.config import SETTINGS
from app.procesamiento.prompts import SYSTEM_PROMPT
from app.servicios.retrieval import ChunkRecuperado, recuperar
from app.servicios.vector_store import coleccion_parents, get_chroma, nombre_coleccion


# ---------------------------------------------------------------------------
# Expansión de parents
# ---------------------------------------------------------------------------


def _expandir_parents(
    chunks: list[ChunkRecuperado],
    coleccion: str,
) -> list[ChunkRecuperado]:
    """Sustituye children por sus parents. Tablas (parent_id='') pasan tal cual.

    Deduplica: si varios children comparten el mismo parent_id, expande una vez.
    """
    col_parents = coleccion_parents(coleccion)
    chroma = get_chroma()

    vistos: dict[str, ChunkRecuperado] = {}   # parent_id → chunk expandido
    resultado: list[ChunkRecuperado] = []
    tablas: list[ChunkRecuperado] = []

    for chunk in chunks:
        pid = chunk.metadatos.get("parent_id", "")

        if pid == "":
            # Tabla o parent directo: sin expansión
            tablas.append(chunk)
            continue

        if pid in vistos:
            # Ya expandimos este parent — descartamos el duplicado
            continue

        # Recuperar parent por ID
        col = chroma.get_collection(name=col_parents)
        data = col.get(ids=[pid], include=["documents", "metadatas"])

        if data["ids"]:
            expandido = ChunkRecuperado(
                chunk_id=pid,
                texto=data["documents"][0],
                metadatos=data["metadatas"][0] if data["metadatas"] else chunk.metadatos,
                score=chunk.score,
                score_vector=chunk.score_vector,
                score_bm25=chunk.score_bm25,
                score_fusion=chunk.score_fusion,
            )
            vistos[pid] = expandido
            resultado.append(expandido)
        else:
            # Parent no encontrado — usar el child tal cual
            resultado.append(chunk)

    return resultado + tablas


# ---------------------------------------------------------------------------
# Construcción del contexto
# ---------------------------------------------------------------------------


def _construir_contexto(chunks: list[ChunkRecuperado]) -> str:
    """Numera y formatea los chunks para el LLM.

    Formato por chunk:
        [n] Documento: {nombre_fichero} | Sección: {seccion} | Pág. {inicio}-{fin}
        {texto}
    """
    partes: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.metadatos
        nombre = meta.get("nombre_fichero", "")
        seccion = meta.get("seccion", "")
        p_ini = meta.get("pagina_inicio", -1)
        p_fin = meta.get("pagina_fin", -1)

        paginas = f"Pág. {p_ini}" if p_ini == p_fin else f"Pág. {p_ini}-{p_fin}"
        if p_ini == -1:
            paginas = ""

        cabecera_partes = [f"Documento: {nombre}"]
        if seccion:
            cabecera_partes.append(f"Sección: {seccion}")
        if paginas:
            cabecera_partes.append(paginas)

        cabecera = " | ".join(cabecera_partes)
        partes.append(f"[{i}] {cabecera}\n{chunk.texto}")

    return "\n\n".join(partes)


# ---------------------------------------------------------------------------
# Construcción de fuentes para SSE
# ---------------------------------------------------------------------------


def _construir_fuentes(chunks: list[ChunkRecuperado]) -> list[dict]:
    fuentes = []
    for chunk in chunks:
        meta = chunk.metadatos
        fuentes.append({
            "doc": meta.get("nombre_fichero", ""),
            "titulo": meta.get("titulo_documento", ""),
            "seccion": meta.get("seccion", ""),
            "pagina_inicio": meta.get("pagina_inicio", -1),
            "pagina_fin": meta.get("pagina_fin", -1),
            "score": round(chunk.score, 4),
            "es_anexo": bool(meta.get("dentro_de_anexo", False)),
        })
    return fuentes


# ---------------------------------------------------------------------------
# Streaming SSE
# ---------------------------------------------------------------------------


async def _stream_respuesta(
    query: str,
    contexto: str,
    fuentes: list[dict],
) -> AsyncGenerator[str, None]:
    """Genera eventos SSE: tokens progresivos → sources → done."""
    client = AsyncOpenAI(api_key=SETTINGS.openai_api_key)

    stream = await client.chat.completions.create(
        model=SETTINGS.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Contexto:\n\n{contexto}\n\nPregunta: {query}"},
        ],
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"

    yield f"data: {json.dumps({'type': 'sources', 'sources': fuentes})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


async def ejecutar_query(
    query: str,
    proyecto_id: str | None,
    empresa: str = "intecsa",
    tipo_doc: str | None = None,
) -> AsyncGenerator[str, None]:
    """Punto de entrada para el endpoint POST /query."""
    coleccion = nombre_coleccion(empresa, proyecto_id)
    chunks = recuperar(query, proyecto_id, empresa, tipo_doc)
    chunks_expandidos = _expandir_parents(chunks, coleccion)
    contexto = _construir_contexto(chunks_expandidos)
    fuentes = _construir_fuentes(chunks_expandidos)
    return _stream_respuesta(query, contexto, fuentes)
```

- [ ] **Step 4: Ejecutar tests para verificar que pasan**

```bash
cd /home/maria/Escritorio/Enterprise-RAG/backend
python -m pytest tests/test_query.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/servicios/query.py backend/tests/test_query.py
git commit -m "feat: añadir query.py con expansión de parents y construcción de contexto"
```

---

### Task 3: Añadir ruta POST /query en main.py

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Reemplazar el contenido de main.py**

```python
"""Aplicación FastAPI — punto de entrada del backend."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.servicios.query import ejecutar_query

app = FastAPI(title="IntecsaRAG", version="0.1.0")


class QueryRequest(BaseModel):
    query: str
    proyecto_id: str | None = None
    empresa: str = "intecsa"
    tipo_doc: str | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/query")
async def query(req: QueryRequest) -> StreamingResponse:
    generator = await ejecutar_query(
        query=req.query,
        proyecto_id=req.proyecto_id,
        empresa=req.empresa,
        tipo_doc=req.tipo_doc,
    )
    return StreamingResponse(generator, media_type="text/event-stream")
```

- [ ] **Step 2: Arrancar el servidor y verificar que arranca sin errores**

```bash
cd /home/maria/Escritorio/Enterprise-RAG/backend
uvicorn app.main:app --reload
```

Expected: `INFO: Application startup complete.` sin errores de import.

- [ ] **Step 3: Verificar /health sigue funcionando**

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: añadir POST /query con streaming SSE"
```

---

### Task 4: Test de integración manual end-to-end

**Files:**
- No se crean archivos nuevos.

- [ ] **Step 1: Asegurarse de que hay documentos indexados en ChromaDB**

```bash
cd /home/maria/Escritorio/Enterprise-RAG/backend
python -c "
from app.servicios.vector_store import get_chroma, listar_colecciones
print(listar_colecciones())
"
```

Expected: lista con al menos una colección (e.g. `['intecsa']`).

- [ ] **Step 2: Enviar query al endpoint con curl**

```bash
curl -N -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Cuál es el procedimiento para calibrar un manómetro?"}'
```

Expected: stream de eventos SSE. Primero tokens, luego:
```
data: {"type": "sources", "sources": [...]}
data: {"type": "done"}
```

- [ ] **Step 3: Verificar que sources contiene documentos del corpus**

El campo `"doc"` en cada source debe corresponder a un fichero PDF indexado (e.g. `"PR-08.pdf"`), no estar vacío.

- [ ] **Step 4: Verificar comportamiento cuando no hay documentos relevantes**

```bash
curl -N -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Cuál es la capital de Francia?"}'
```

Expected: el LLM responde con "No encuentro esa información en la documentación proporcionada" (o similar), y `sources` es una lista de chunks del corpus aunque sean poco relevantes.

- [ ] **Step 5: Commit final**

```bash
git add .
git commit -m "feat: POST /query operativo — Fase 1 completada"
```
