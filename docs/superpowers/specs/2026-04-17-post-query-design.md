# Diseño: POST /query

**Fecha:** 2026-04-17  
**Fase:** 1 — RAG base  

## Contexto

El pipeline de ingesta y retrieval están implementados. Falta el endpoint que los conecta con el LLM y devuelve la respuesta al cliente. `POST /query` es la pieza que cierra el ciclo RAG: recibe una pregunta, recupera los chunks relevantes, expande a parents, construye el contexto y genera la respuesta en streaming SSE.

---

## Módulos

| Archivo | Rol |
|---|---|
| `backend/app/servicios/query.py` | Orquestación completa (expansión, contexto, LLM) |
| `backend/app/main.py` | Ruta HTTP, `QueryRequest`, `StreamingResponse` |
| `backend/app/procesamiento/prompts.py` | Añadir `SYSTEM_PROMPT` |

---

## Request

```python
class QueryRequest(BaseModel):
    query: str
    proyecto_id: str | None = None
    empresa: str = "intecsa"
    tipo_doc: str | None = None
```

El `historial` se omite en esta fase (single-shot). Se añadirá en Fase 2/3 cuando haya persistencia de sesión.

---

## Flujo en `query.py`

```
recuperar(query, proyecto_id, empresa, tipo_doc)
    → list[ChunkRecuperado]

_expandir_parents(chunks, coleccion)
    → list[ChunkExpandido]   # children → parent por ID; tablas pasan tal cual

_construir_contexto(chunks_expandidos)
    → str                    # [1] Doc | Sección | Pág.\n{texto}\n\n[2]...

_stream_respuesta(query, contexto, chunks_expandidos)
    → AsyncGenerator[str]    # eventos SSE
```

---

## Expansión de parents

- Si `metadatos["nivel"] == "child"` y `metadatos["parent_id"] != ""`:  
  recuperar el parent por ID desde la colección `{coleccion}__parents`.
- Si `parent_id == ""` (tabla): pasar el chunk directamente sin expansión.
- Deduplicar por `parent_id`: si dos children comparten parent, expandir una sola vez.
- Usar `get_chroma()` y `coleccion_parents()` de `vector_store.py`.

---

## Construcción del contexto

Formato por chunk:

```
[1] Documento: 14090-IT-01.pdf | Sección: 3. PROCEDIMIENTO | Pág. 4-5
{texto}

[2] Documento: PR-08.pdf | Sección: 2. ALCANCE | Pág. 2
{texto}
```

Los índices `[n]` enlazan el texto del LLM con el array `sources` del SSE.

---

## System prompt

```
Eres un asistente técnico especializado en documentación de ingeniería industrial de INTECSA.

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

NO hagas suposiciones técnicas ni completes información que no esté explícita en la documentación.
```

Se añade a `prompts.py` como `SYSTEM_PROMPT`.

---

## Contrato SSE

Tres tipos de evento en orden:

```
data: {"type": "token", "content": "La válvula"}
data: {"type": "token", "content": " de control..."}
...
data: {"type": "sources", "sources": [
    {
        "doc": "14090-IT-01.pdf",
        "titulo": "INSTRUCCIÓN DE TRABAJO",
        "seccion": "3. PROCEDIMIENTO",
        "pagina_inicio": 4,
        "pagina_fin": 5,
        "score": 0.91,
        "es_anexo": false
    }
]}
data: {"type": "done"}
```

Las fuentes se emiten una sola vez al final, tras el último token.

---

## Fuentes (`sources`)

Se construyen desde los metadatos de los chunks expandidos:

| Campo | Origen |
|---|---|
| `doc` | `metadatos["nombre_fichero"]` |
| `titulo` | `metadatos["titulo_documento"]` |
| `seccion` | `metadatos["seccion"]` |
| `pagina_inicio` | `metadatos["pagina_inicio"]` |
| `pagina_fin` | `metadatos["pagina_fin"]` |
| `score` | `chunk.score` |
| `es_anexo` | `metadatos["dentro_de_anexo"]` |

---

## Verificación

1. Arrancar FastAPI: `uvicorn app.main:app --reload` desde `backend/`
2. Enviar query con curl:
   ```bash
   curl -N -X POST http://localhost:8000/query \
     -H "Content-Type: application/json" \
     -d '{"query": "¿Cuál es el procedimiento para calibrar un manómetro?"}'
   ```
3. Verificar que llegan eventos `token` progresivos, luego `sources` con al menos 1 fuente, luego `done`
4. Verificar que `sources` referencia documentos del corpus indexado
