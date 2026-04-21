# CLAUDE.md — IntecsaRAG Beta

Sistema RAG corporativo para Intecsa (ingeniería industrial). Permite a los empleados consultar en lenguaje natural los procedimientos generales de la empresa y documentos de proyectos con clientes. TFG de Ingeniería Informática — despliegue final en Azure (licencia Microsoft).

---

## Stack

| Componente | Dev local | Producción (Azure) |
|---|---|---|
| LLM | OpenAI GPT-4o (API directa) | Azure OpenAI Service |
| Embeddings | `text-embedding-3-large` (3072 dims) | Azure OpenAI Embeddings |
| Vector store | ChromaDB Cloud | Azure AI Search |
| Parser | Docling (IBM, 2024) | Docling |
| Reranker | Cohere `rerank-multilingual-v3.0` | Cohere (igual) |
| BM25 | `rank-bm25` en memoria | `rank-bm25` o BM25 nativo Azure AI Search |
| Backend | FastAPI + uvicorn | Azure Container Apps |
| Frontend | Next.js 14 + shadcn/ui | Azure Static Web Apps |

Mismo modelo de embeddings en dev y producción: los vectores son compatibles y no hay que reindexar al migrar.

---

## Pipeline de ingestión

**Ficheros:** `procesamiento/parser.py` → `elementos.py` → `chunker.py` → `servicios/vector_store.py`

```
PDF → DoclingDocument → [ElementoProcesado] → [Chunk] → ChromaDB
```

### Parser — Docling

**Por qué Docling:** exporta tablas a Markdown (3-4× más eficiente en tokens que HTML) y detecta bien la estructura de secciones en PDFs de ingeniería. El `DocumentConverter` se instancia como singleton por proceso — la inicialización cuesta ~30s.

**Cómo:** `parser.py` llama a `DocumentConverter` de Docling con `do_ocr=True`, `images_scale=2.0`, `TableFormerMode.ACCURATE`. Extrae el título del documento con regex sobre los primeros 35 items (primer `SectionHeaderItem` que supera filtros de longitud y charset) y la edición con el patrón `EDICION/EDITION`. Sin llamadas a API en esta fase.

La GTX 960M (CUDA CC 5.0) no es compatible con PyTorch 2.6+. Se fuerza CPU con `os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")` antes de importar Docling. En Azure no hay esta restricción.

### Procesado de elementos

**Por qué:** cada tipo de elemento (texto, tabla, imagen, cabecera) necesita tratamiento diferente antes de llegar al chunker.

**Cómo:** `elementos.py` recorre el `DoclingDocument` y produce una lista plana de `ElementoProcesado`:

- **Cabeceras de sección:** no generan elemento. Actualizan `seccion_actual` y el flag `dentro_de_anexo` (si el título contiene ANEXO/APPENDIX/ANNEX). Se filtran también los bloques repetidos del tipo `EDICION 6  HOJA 7 DE 10` (regex `PATRON_CABECERA`) y las secciones de índice completas.
- **Texto y listas:** se usa directamente tras limpiar espacios.
- **Tablas:** se exportan a Markdown con `export_to_markdown()`. Se eliminan los code fences que añade Docling, los data URIs base64 de símbolos (se conserva solo el alt text), y se detectan tablas degradadas con `\|\s{6,}\|`. Si `tabla_degradada=True` y `ENABLE_VISION=1`, se llama a `vision.describir_tabla()` con la imagen más enfocada disponible (crop de Docling → crop manual con bbox → página completa).
- **Imágenes:** la primera imagen del documento se descarta siempre (logo corporativo). El resto se describe con GPT-4o si `ENABLE_VISION=1`. Si la imagen está en la misma página que el elemento anterior, su descripción se fusiona en ese texto (`es_imagen=True`); si no, se emite como chunk standalone.

### Chunking jerárquico

**Por qué:** un chunk de 128 tokens es preciso para retrieval pero demasiado corto como contexto para el LLM. El modelo padre-hijo combina precisión en la búsqueda con contexto amplio en la respuesta.

**Cómo:** `chunker.py` pre-segmenta los elementos por tipo y sección (para evitar que un parent mezcle una tabla con prosa de otra sección), luego aplica `HierarchicalNodeParser` de LlamaIndex:

- **Child (~128 tokens):** indexado con embeddings en la colección principal. Usado para retrieval.
- **Parent (~1024 tokens):** almacenado sin embeddings en la colección `__parents`. Recuperado por ID cuando se encuentra un child relevante, para dar contexto ampliado al LLM.
- **Tablas:** siempre un único chunk con `parent_id=""`. La tabla completa es su propio contexto — no tiene sentido subdividirla.
- **Parents huérfanos:** si el texto es < 128 tokens y LlamaIndex no puede generar un child distinto, se indexa solo el parent (con embeddings) en la colección principal, con `parent_id=""`.

Se eligió 1024 tokens para el parent (probado con 512): con 512 el Context Relevance cayó significativamente — los fragmentos eran demasiado cortos para preguntas que requieren contexto de sección completa.

### Indexación en ChromaDB

**Por qué dos colecciones:** los parents más largos contaminarían el espacio vectorial y distorsionarían el ranking de similitud si se indexaran junto a los children.

**Cómo:** `vector_store.py` crea dos colecciones por scope:
- `{nombre}` — children con embeddings (métrica coseno). También recibe parents huérfanos.
- `{nombre}__parents` — parents sin embeddings, solo para recuperación por ID.

El texto embebido es distinto del texto almacenado. El embedding incluye prefijos de contexto:
```
{tipo_doc}\n\n{codigo_doc}\n\n{titulo_documento}\n\n{seccion}\n\n{texto_chunk}
```
El texto almacenado en ChromaDB es solo `chunk.texto`. Esta separación es clave: el embedding captura contexto del documento completo, el texto almacenado es lo que lee el LLM.

- **`codigo_doc`** (ej: `PR-02`): embebe el código del fichero. Mejora el retrieval para queries que mencionan códigos explícitos.
- **`titulo_documento`**: ancla el chunk al documento. Reduce el problema de secciones homólogas (OBJETO, FUNCIONES, RESPONSABILIDADES aparecen en todos los procedimientos con embeddings casi idénticos).
- **`tipo_doc`**: diferencia procedimientos de instrucciones con secciones del mismo nombre.

Requiere reingesta cuando se modifica este formato.

ChromaDB Cloud limita `col.get()` a 300 items por llamada. La indexación y el índice BM25 paginan en bloques de 300 — sin paginación el índice solo cubría el 41% del corpus.

---

## Pipeline de retrieval

**Fichero:** `servicios/retrieval.py` — función pública `recuperar(query, proyecto_id, empresa, ...)`

```
query → rewriting dual → vector search + BM25 → fusión → rerank Cohere → [ChunkRecuperado]
```

### Query rewriting dual

**Por qué:** vector y BM25 se benefician de tipos de expansión distintos. Usar la misma query expandida para ambos dilata el espacio vectorial.

**Cómo:** `_reescribir_query()` llama a GPT-4o-mini con `PROMPT_REESCRITURA_QUERY` y parsea dos líneas:
- `VECTOR: <reformulación semántica>` — añade contexto implícito, mejora recall semántico.
- `BM25: <bolsa de palabras>` — sinónimos léxicos expandidos (ej: `aprueba firma autoriza valida Dirección General`), mejora recall léxico.

Cohere rerank siempre usa la query **original** para máxima fidelidad a la intención del usuario.

### Búsqueda híbrida

**Por qué:** vector captura semántica, BM25 captura códigos técnicos literales (PR-01, JDAP, IT-02) que el modelo de embeddings puede diluir.

**Cómo:**
1. **Vector:** embedding de `query_vector` con `text-embedding-3-large`, `col.query(n_results=top_k)` sobre la colección del scope. Distancia coseno.
2. **BM25:** índice `BM25Okapi` construido lazy la primera vez, cacheado en memoria por colección. Tokenización preserva códigos con guión (`PR-01`, `IT-02`). El índice tokeniza `titulo_documento + seccion + texto` por chunk. `_reescribir_query` produce `query_bm25` para este paso.
3. **Fusión:** scores normalizados min-max [0,1], combinados con pesos `VECTOR=0.7 / BM25=0.3`. Top-K candidatos pasan al rerank.

Pesos calibrados: el corpus técnico de Intecsa tiene terminología consistente — el vector domina. BM25 complementa para identificadores literales.

### Rerank con Cohere

**Por qué:** los scores de fusión híbrida no son comparables entre sí ni reflejan bien la relevancia real. Cohere reordena según relevancia semántica a la query original.

**Cómo:** `co.rerank(model="rerank-multilingual-v3.0", query=query_original, documents=textos_top_k, top_n=3)`. Devuelve `ChunkRecuperado` con `score=relevance_score` de Cohere.

`RETRIEVAL_TOP_N=3` (reducido de 5): con 5 chunks el LLM veía contexto de documentos incorrectos y mezclaba respuestas.

### Expansión a parents

**Por qué:** el retrieval encuentra children precisos pero el LLM necesita más contexto para responder.

**Cómo:** `query.py → _expandir_parents()` hace `col.get(ids=[parent_ids])` sobre la colección `__parents` y sustituye cada child por su parent. Tablas (`parent_id=""`) se pasan directamente sin expansión. La expansión ocurre en el orquestador, no en el módulo de retrieval.

---

## Generación de respuesta

**Fichero:** `servicios/query.py`

### Contexto XML

**Por qué XML:** GPT-4o está entrenado masivamente con XML y lo reconoce como delimitador estructural, no como texto citable. El atributo `doc=` permite al LLM identificar la procedencia sin que los metadatos contaminen el texto recuperable.

**Cómo:** `_construir_contexto()` envuelve cada chunk:
```xml
<fuente id="1" doc="PR-02" edicion="8" seccion="Procedimientos Generales" paginas="3">
texto del chunk
</fuente>
```

Los metadatos completos (doc, título, versión, sección, páginas, score, es_anexo) viajan por separado en el evento `sources` del SSE. El frontend usa ese payload para renderizar los chips — el LLM nunca escribe metadatos en su respuesta.

**Sin marcadores de cita `[N]`:** TruLens penaliza `[1]`, `(PR-01)` como afirmaciones no verificables contra el contexto, hundiendo la métrica Groundedness. La trazabilidad al usuario se resuelve en el frontend.

### Streaming SSE

**Por qué:** el usuario ve tokens progresivamente en lugar de esperar la respuesta completa.

**Cómo:** `_stream_respuesta()` usa `client.chat.completions.create(stream=True)` y emite eventos SSE:
```
data: {"type": "token",   "content": "..."}   ← uno por token de GPT-4o
data: {"type": "sources", "sources": [...]}    ← tras el último token
data: {"type": "done"}                         ← cierre del stream
data: {"type": "error",   "message": "..."}    ← solo si falla el LLM
```

---

## API — FastAPI

**Estructura:** routers separados en `app/api/` (health.py, projects.py, query.py). `main.py` solo registra routers y configura CORS. Permite `localhost:3000–3009` en dev.

**`GET /projects`:** llama a `colecciones_disponibles()` de `vector_store.py` y parsea los nombres: `intecsa` → scope global; `{proyecto_id}_{empresa}` → scope de proyecto. Filtra colecciones `__parents`.

**`POST /query`:** recibe `{query, proyecto_id, empresa, tipo_doc}` y devuelve `StreamingResponse` con `media_type="text/event-stream"`.

---

## Frontend — Next.js 14

**Ficheros:** `app/page.tsx`, `components/Sidebar.tsx`, `components/ChatArea.tsx`, `components/ChatMessage.tsx`, `components/SourceChip.tsx`, `lib/api.ts`

### Decisiones de implementación

**Babel en lugar de SWC:** Node.js 18.19.1 en dev local es incompatible con el binario SWC de Next.js 14 (SIGBUS al cargar el `.node` nativo). Se usa Babel (`next/babel` en `.babelrc`) con `@babel/runtime` instalado localmente para evitar que webpack resuelva la versión del sistema en `/usr/share/nodejs/`. En producción (Azure, Node 20+) se puede eliminar `.babelrc`.

**`fetch` en lugar de `EventSource`:** `EventSource` no admite POST con body. El streaming SSE se lee con `ReadableStreamDefaultReader` en `lib/api.ts::streamQuery()`, parseando líneas `data: {...}` del buffer.

**Estado de scope en `page.tsx`:** el scope activo se gestiona en el componente raíz para que Sidebar y ChatArea compartan la misma fuente de verdad. Al cambiar scope, ChatArea limpia el historial de mensajes (via `useEffect` sobre `scope.coleccion`).

**Chips de fuente:** badge azul para fuentes normales, ámbar para `es_anexo=true`. Tooltip con `titulo · seccion · páginas` al hover usando Radix UI Tooltip (sin `EventSource`). Los chips se muestran al recibir el evento `sources`, una vez finalizado el streaming.

**Sidebar:** llama a `GET /projects` al montar. Agrupa scopes por empresa (sección "General" para el corpus global, sección `{Empresa}` para proyectos). Usa `Building2` y `FolderOpen` de lucide-react para diferenciar visualmente.

---

## Evaluación con TruLens

**Fichero:** `scripts/eval_trulens.py`

**Por qué TruLens:** evalúa automáticamente la tríada RAG (Context Relevance, Answer Relevance, Groundedness) usando GPT-4o como juez, sin necesidad de ground truth manual.

**Cómo:** `RAGPipeline` es una clase síncrona instrumentada por TruLens que envuelve el pipeline real. El endpoint SSE no se puede instrumentar directamente (TruLens requiere funciones síncronas y respuesta completa). `recuperar_contexto()` guarda los chunks completos en `self._last_chunks` antes de devolver `list[str]` a TruLens — `generar_respuesta()` los usa para construir el contexto XML con metadatos correctos.

**Banco de 10 queries** basadas en datos concretos de los documentos (no secciones genéricas). 7 del corpus global Intecsa + 3 del proyecto Repsol. Queries sobre secciones homólogas (OBJETO, FUNCIONES) se excluyen porque deprimen AR artificialmente.

**Rate limit:** 30k TPM (tier 1 OpenAI). Cada query consume ~15-20k tokens (respuesta + 3 feedbacks) → 1 query cada 18s. `eval_trulens.py --reset` para borrar evaluaciones anteriores.

**GR cae con marcadores de cita:** TruLens penaliza `[1]`, `(PR-01)` como afirmaciones no verificables. El SYSTEM_PROMPT de producción no usa marcadores.

---

## Pendiente de implementar

**Query Router** — infiere automáticamente el scope (corpus global vs proyecto) a partir de la pregunta. Incluye extractor de entidades, clasificador con umbral de confianza, pregunta de clarificación cuando la confianza es baja, y topbar en el frontend mostrando el scope inferido con opción de corrección manual.

**POST /ingest** — endpoint de administrador para subir PDFs desde la UI con validación de metadatos (empresa, proyecto_id, tipo_doc, idioma).

**Filtro por documento para queries explícitas** — cuando la query menciona un código de documento (PR-01, IT-02), pre-filtrar ChromaDB por `nombre_fichero` antes del retrieval vectorial. Mitiga el problema de secciones homólogas para este tipo de queries.

### Fuera del alcance de la beta

- GPT-4o vision para todas las imágenes (actualmente solo tablas degradadas).
- Búsqueda web externa (Tavily).
- Normativas externas (ISO, EN, UNE, ASME).
- Documentos escaneados con OCR.
- Diagramas P&ID completos procesados como imagen.
- Contratos con deduplicación semántica.
- Historial conversacional
