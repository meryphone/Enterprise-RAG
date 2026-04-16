# CLAUDE.md — IntecsaRAG Beta

Fichero de contexto del proyecto para asistencia con IA. Versión beta del sistema RAG — alcance reducido para validar el pipeline base antes de añadir complejidad.

---

## Contexto del proyecto

**Proyecto:** Sistema RAG corporativo para Intecsa (empresa de ingeniería industrial)  
**Objetivo:** Permitir a los empleados consultar en lenguaje natural los procedimientos generales de la empresa y los documentos de proyectos con clientes.  
**Tipo:** TFG de Ingeniería Informática  
**Empresa:** Intecsa — tiene licencia Microsoft, el despliegue final es en Azure.

### Alcance de la beta

Esta versión beta tiene un alcance deliberadamente reducido para validar el pipeline base con documentos simples antes de añadir complejidad:

- El corpus se limita a dos tipos: **procedimientos generales de Intecsa** y **documentos de proyectos con clientes**.
- Las imágenes se procesan si `ENABLE_VISION=1` (GPT-4o vision). Si está desactivado, las imágenes sin texto adyacente se descartan silenciosamente.
- No incluye comparativa con fuentes externas mediante búsqueda web.
- No incluye normativas externas.
- No incluye contratos.

Las funcionalidades excluidas están documentadas como trabajo futuro en la versión completa.

### Características de la beta
- Búsqueda semántica sobre procedimientos generales de Intecsa y documentos de proyectos con clientes
- Organización por scopes: corpus global de Intecsa + corpus por proyecto
- Query Router automático que infiere el scope sin que el usuario lo indique explícitamente
- Citación de fuentes en cada respuesta (documento, sección, página)
- Respuesta en el idioma de la pregunta; los documentos pueden estar en cualquier idioma, aunque no habrá documentos con versiones en distintos idiomas.

### Idioma de los documentos
Los documentos indexados pueden estar en **cualquier idioma** — se han identificado documentos en español, inglés y francés. El modelo de embeddings es multilingüe. El LLM responde en el idioma en que el usuario formula la pregunta, independientemente del idioma del documento fuente.

---

## Fases de desarrollo de la beta

| # | Fase | Duración estimada |
|---|------|-------------------|
| 1 | RAG base — ingestión y búsqueda | ~2 semanas |
| 2 | Scopes y organización por proyecto | ~1.5 semanas |
| 3 | Query Router automático | ~2 semanas |
| 4 | Migración a Azure y despliegue | ~1 semana |

---

## Stack tecnológico

### Principio guía
**"Dev local → Azure sin reescribir."** Todos los clientes (LLM, embeddings, vector store) se abstraen detrás de una capa de configuración. Un flag `ENV=local|production` en `.env` determina qué implementación se instancia. El código de negocio nunca sabe dónde está corriendo.

### Tabla de stack por entorno

| Componente | Desarrollo local | Producción (Azure) |
|---|---|---|
| LLM | OpenAI API directa | Azure OpenAI Service (GPT-4o en tenant Intecsa) |
| Embeddings | `text-embedding-3-small` vía OpenAI API | Azure OpenAI Embeddings (`text-embedding-3-small`) |
| Vector store | ChromaDB cloud, API KEY: ck-KpwgS9zBfSx3XC8s7ckZjK9HNtxs2jSBuZuhP9vXPug TENANT ID: a66be815-8e1b-456e-bd68-c7137590d7ec | Azure AI Search (vector + filtros de metadatos) |
| Documentos | Sistema de archivos local | Azure Blob Storage |
| Framework | LlamaIndex + FastAPI | LlamaIndex + FastAPI (igual) |
| Frontend | Next.js + shadcn/ui | Azure Static Web Apps |
| Parser de documentos | Docling | Docling |
| Vision (opcional) | GPT-4o vía OpenAI API (`ENABLE_VISION=1`) | GPT-4o vía Azure OpenAI |
| BM25 léxico | `rank-bm25` en memoria por colección | `rank-bm25` o BM25 nativo de Azure AI Search |
| Reranker | Cohere Rerank API (`rerank-multilingual-v3.0`) | Cohere Rerank API (igual) |
| Demo sin despliegue | ngrok | — |

### Decisiones clave

**Mismo modelo de embeddings en dev y producción:** Se usa `text-embedding-3-small` en ambos entornos. Esto elimina la necesidad de reindexar al migrar ya que los vectores son compatibles. Dimensión: 1536. Llamadas en lotes de 100 textos por petición a la API.

**LlamaIndex sobre LangChain:** Elegido por su foco específico en RAG, el concepto de `Node` con metadatos encaja con el modelo de documentos por proyecto, y el `RouterQueryEngine` es la base natural del Query Router.

**Streaming SSE:** El endpoint de query expone la respuesta como stream (Server-Sent Events) para que el frontend muestre los tokens progresivamente.

**ChromaDB → Azure AI Search:** Chroma cloud para dev. Azure AI Search en prod. LlamaIndex tiene wrappers con interfaz idéntica para ambos.

**ngrok para demos sin despliegue:** Para mostrar la beta a la empresa sin necesidad de desplegar en Azure, ngrok crea un túnel desde internet hasta la aplicación corriendo en local. Genera una URL pública temporal que cualquier persona puede abrir desde su navegador. Solo requiere tener la aplicación arrancada en local y ejecutar ngrok apuntando al puerto de FastAPI y al de Next.js.

**Docling como parser principal:** Docling es una librería open source de IBM (2024) especializada en parseo de documentos para RAG. Exporta tablas directamente en Markdown y detecta bien la estructura de secciones. Configuración en uso: `do_picture_images=True`, `do_picture_description=true` (la descripción se hace con GPT-4o, integrandolo con docling), `images_scale=2.0`, `do_ocr=True`, `TableFormerMode.ACCURATE`. El `DocumentConverter` se instancia como singleton por proceso (inicialización costosa).


**CPU para modelos de Docling en dev local:** La GTX 960M (CUDA CC 5.0) no es compatible con PyTorch 2.6+ (mínimo CC 7.5 en las wheels oficiales). Downgrade a PyTorch 2.0.x requeriría Python ≤ 3.11, incompatible con el entorno. Se fuerza CPU con `os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")` en `parser.py` antes de importar Docling. Esta línea se elimina al desplegar en Azure. Los modelos de layout y TableFormer corren en CPU; GPT-4o vision se llama por API, sin GPU local.

**Dos colecciones paralelas por namespace en ChromaDB:** Los child chunks (con embeddings) se indexan en `{nombre}` y los parent chunks (sin embeddings, solo recuperación por ID) en `{nombre}__parents`. Métrica de distancia: coseno (`hnsw:space=cosine`).

---

## Arquitectura del sistema

```
Usuario
  │
  ▼
Query Router
  ├── Extractor de entidades (¿proyecto? ¿cliente? ¿tipo doc?)
  ├── Clasificador de intención → {scope, tipo, confianza}
  └── Si confianza < umbral → pregunta de clarificación al usuario
  │
  ├──► Scope: Global Intecsa   ─┐
  ├──► Scope: Proyecto/cliente ─┤──► Retrieval Engine
  └──► Scope: Multi-scope      ─┘        │
                                         ├── Hybrid search (vector + BM25)
                                         ├── Filtro de metadatos (tipo_doc, ...)
                                         ├── Reranker (Cohere Rerank)
                                         └── Construcción de contexto con citas
                                                     │
                                                     ▼
                                         LLM + Generación de respuesta
                                                     │
                                                     ▼
                                 Respuesta + chips de fuente (doc, sección, página)
```

---

## Corpus de la beta

### Documentos incluidos

**Corpus global Intecsa** — procedimientos generales de la empresa aplicables a todos los proyectos. Colección `intecsa`.

**Corpus por proyecto** — documentos generados en proyectos con clientes: especificaciones técnicas, instrucciones de trabajo, informes. Una colección por proyecto: `{proyecto_id}_{empresa}`.

### Criterios de selección de documentos para la beta

Solo se incluyen documentos que cumplan todos estos criterios:

- Formato PDF con texto extraíble digitalmente — sin documentos escaneados.
- Contenido principalmente textual — se admiten tablas y, si `ENABLE_VISION=1`, imágenes con descripción automática.
- Idioma identificable — español, inglés o francés.
- Los documentos que son el mismo contenido en distintos idiomas se eliminan antes de la ingestión, conservando únicamente la versión en el idioma principal.

---

## Pipeline de ingestión

El pipeline recibe un PDF y los metadatos del administrador y produce chunks indexados en el vector store.

### Flujo general

Pasos secuenciales:

1. **Parseo:** Docling convierte el PDF en `DoclingDocument` con elementos tipificados.
2. **Extracción de metadatos de cabecera (texto, sin coste):** regex sobre los primeros 35 items del documento para extraer título (primer `SectionHeaderItem` que supera los filtros de longitud y charset) y edición (patrón `EDICION/EDITION`). Ninguna llamada a API.
3. **Procesado de elementos:** cada item del `DoclingDocument` se transforma en `ElementoProcesado` aplicando las reglas por tipo.
4. **Chunking:** los elementos procesados se segmentan y pasan por `HierarchicalNodeParser`.
5. **Indexación:** los chunks se serializan con metadatos aplanados y se suben a ChromaDB.

Los metadatos tienen tres orígenes: extraídos del documento con regex sobre la cabecera, introducidos por el administrador al subir el documento, y generados por el pipeline (fecha de ingesta, IDs).

### Arquitectura del pipeline (pipes and filters)

```
PDF → DoclingDocument → [ElementoProcesado] → [Chunk] → ChromaDB
```

- `parser.py`: convierte el PDF con Docling y extrae metadatos de cabecera.
- `vision.py`: describe imágenes y extrae metadatos de portada vía GPT-4o.
- `elementos.py`: recorre los items del `DoclingDocument` y produce una lista plana de `ElementoProcesado`. Decide qué hacer con cada tipo (texto tal cual, tabla a Markdown, imagen descrita) y aplica la regla de fusión texto-imagen.
- `chunker.py`: recibe la lista de `ElementoProcesado`, pre-segmenta por tipo y sección, aplica `HierarchicalNodeParser` y produce la lista de `Chunk` lista para indexar.
- `vector_store.py`: serializa y sube los chunks a ChromaDB, gestionando las dos colecciones paralelas.
- El código de negocio (pipeline, retrieval) solo ve `Chunk` — nunca sabe qué hizo Docling internamente.

### Filtrado de cabeceras, pies y tabla de contenidos

Antes de procesar el contenido, `elementos.py` descarta:

- **Bloques de cabecera completos** (patrón `PATRON_CABECERA`): líneas del tipo `EDICION 6  HOJA 7 DE 10` que aparecen repetidas en todas las páginas.
- **Fragmentos de cabecera aislados** (`PATRON_PIE_PAGINA`, `_es_fragmento_cabecera_puro`): componentes individuales cuando Docling los extrae en items separados.
- **Secciones de índice** (patrón `PATRON_INDICE`): el contenido de secciones cuyo título contiene patrones de tabla de contenidos se descarta completamente — un índice no aporta nada al retrieval.

Este filtrado es multilingual (español, inglés, francés).

### Procesado por tipo de elemento

**SectionHeaderItem:** no genera `ElementoProcesado`. Solo actualiza `seccion_actual`, el flag `dentro_de_anexo` (si el título contiene ANEXO/APPENDIX/ANNEX) y el flag `dentro_de_indice`. Normaliza el formato: "3.NOTAS" → "3. NOTAS". Esto evita que secciones sin cuerpo produzcan segmentos de un solo título, que LlamaIndex no puede subdividir y que generan pares parent==child idénticos.

**NarrativeText, ListItem:** el texto se usa directamente tras limpiar espacios. Se filtra si está vacío, si coincide con los patrones de cabecera/pie, o si reproduce el título del documento.

**Table:** exportado a Markdown con `export_to_markdown()`. Se eligió Markdown sobre HTML porque es 3-4× más eficiente en tokens y produce el mismo resultado para el LLM y los embeddings. Las tablas con celdas fusionadas (merged cells) se marcan con `tabla_degradada=True` detectando el patrón `\|\s{10,}\|` en el Markdown resultante. Si la tabla está degradada y `ENABLE_VISION=1`, se llama a GPT-4o para obtener una descripción más fiel de la tabla. Las tablas son siempre `indivisible=True` — el chunker no las subdivide.

**PictureItem:** la primera imagen de cada documento se descarta siempre (logo corporativo de Intecsa). Para el resto, cadena de fallback para obtener descripción:
1. `DescriptionAnnotation` de Docling (si Docling usó `PictureDescriptionApiOptions` — actualmente desactivado).
2. GPT-4o vision (si `ENABLE_VISION=1`): prompt `PROMPT_IMAGEN_CONTENIDO` para imágenes de contenido general; `PROMPT_IMAGEN_EJEMPLO` para imágenes donde el texto adyacente sugiere "ejemplo/example".
3. Si ninguna opción disponible → imagen descartada silenciosamente.

Regla de fusión: si la imagen está en la misma página que el `ElementoProcesado` anterior (NarrativeText o ListItem), su descripción se añade al texto anterior como `[Descripción visual: ...]` y se marca `es_imagen=True`. Si no hay elemento anterior en la misma página y `ENABLE_VISION=1`, se emite como chunk standalone de tipo `Image`.

### Penalización de chunks de anexos

Pendiente de implementación: los chunks con `dentro_de_anexo=True` recibirán un factor de penalización de 0.7 aplicado post-rerank sobre el score de Cohere. No se excluyen del retrieval pero son menos competitivos frente a chunks del cuerpo principal. El valor es calibrable con el banco de queries de prueba.

El system prompt incluirá la instrucción de indicarle al usuario cuando la información procede de un anexo.

### Hierarchical chunking

Pre-segmentación antes del parser: `chunker.py` agrupa los `ElementoProcesado` en segmentos respetando dos fronteras — cambio de tipo (prosa vs. tabla) y cambio de sección. Esto impide que un parent mezcle secciones distintas y trata los elementos indivisibles (tablas) por separado.

**Chunking de prosa:** se aplica `HierarchicalNodeParser` de LlamaIndex con solapamiento de 20 tokens:

- **Child chunks (~128 tokens):** indexados con embeddings, usados para retrieval preciso.
- **Parent chunks (~512 tokens):** recuperados por ID cuando se encuentra un child relevante, proporcionan contexto ampliado para la respuesta.
- Los tamaños son configurables vía `CHILD_CHUNK_TOKENS` y `PARENT_CHUNK_TOKENS` en `.env`.
- Si LlamaIndex no puede subdividir un segmento (texto < 128 tokens), el child idéntico al parent se descarta — solo se indexa el parent.
- Los parents se emiten antes que sus hijos en la salida JSON para mantener orden narrativo.

**Tablas:** se emiten como un único chunk de nivel `child` con `parent_id=None`. No tienen parent porque la tabla completa es su propio contexto — un parent idéntico no aportaría nada al LLM. Cuando el retrieval recupera un chunk de tabla con `parent_id=None`, lo pasa directamente al LLM sin expansión.

**Propagación de metadatos:** los metadatos de sección, flags de tipo y páginas se adjuntan al `Document` de LlamaIndex y se excluyen del conteo de tokens del LLM y los embeddings (`excluded_llm_metadata_keys`, `excluded_embed_metadata_keys`). Se propagan automáticamente a todos los nodos (parents e hijos).

---

## Modelo de metadatos

Cada chunk indexado en ChromaDB lleva 20 metadatos. ChromaDB requiere tipos primitivos (str/int/float/bool) — las listas se serializan como strings separados por comas; los campos ausentes usan -1 (enteros) o "" (strings). La serialización se hace en `vector_store.py → _meta_chunk()`.

| Campo | Tipo | Origen | Descripción |
|---|---|---|---|
| `doc_id` | str | Pipeline | UUID generado en el momento de la ingesta — identificador interno único del documento |
| `nombre_fichero` | str | Pipeline | Nombre del fichero PDF original |
| `titulo_documento` | str | Docling (regex cabecera) | Título extraído del primer `SectionHeaderItem` que supera los filtros de longitud y charset. `""` si no se detectó. Mapeado desde `metadatos_documento.titulo` |
| `version` | str | Docling (regex cabecera) | Edición del documento extraída por regex del texto de cabecera. `""` si no se detectó. Mapeado desde `metadatos_documento.edicion` |
| `fecha_emision` | str | — | Campo reservado. Actualmente siempre `""` — no se extrae en la beta |
| `fecha_ingesta` | str | Pipeline | Fecha de procesado en ISO 8601 |
| `empresa` | str | Administrador | `"intecsa"` o nombre del cliente (e.g. `"repsol"`) |
| `proyecto_id` | str | Administrador | Código del proyecto (e.g. `"13187"`). `""` si es corpus global |
| `tipo_doc` | str | Administrador / Pipeline | `procedimiento`, `instruccion_trabajo`, `especificacion`, `informe`, `anexo`. `"anexo"` lo asigna el administrador o el pipeline cuando detecta sección ANEXO/APPENDIX/ANNEX |
| `idioma` | str | Administrador | Código ISO 639-1 del idioma principal del documento — `"es"`, `"en"`, `"fr"` |
| `anexo_de` | str | Administrador | Nombre del documento padre si `tipo_doc=="anexo"` (e.g. `"PR-08"`, `"14090-IT-01"`). `""` si no es anexo |
| `nivel` | str | Pipeline | `"child"` o `"parent"` |
| `parent_id` | str | Pipeline | UUID del chunk padre. `""` para chunks padre y para tablas |
| `pagina_inicio` | int | Pipeline | Primera página de los elementos que componen el chunk. `-1` si desconocida |
| `pagina_fin` | int | Pipeline | Última página de los elementos que componen el chunk. `-1` si desconocida |
| `seccion` | str | Docling | Título de la sección actual cuando se procesó el elemento. `""` si no hay sección |
| `tipos_elemento` | str | Pipeline | Tipos de elementos que componen el chunk, separados por coma (`"NarrativeText,ListItem"`, `"Table"`, `"Image"`) |
| `es_imagen` | bool | Pipeline | `true` si el chunk incorpora una descripción visual (fusión texto+imagen o chunk standalone de imagen) |
| `dentro_de_anexo` | bool | Pipeline | `true` si el chunk pertenece a una sección cuyo título contiene ANEXO/APPENDIX/ANNEX, o si el administrador declaró `tipo_doc="anexo"` |
| `tabla_degradada` | bool | Pipeline | `true` si la tabla tiene celdas fusionadas que Docling no pudo separar correctamente. Candidata a re-procesar con vision |

### Nota sobre `empresa` y scopes

El campo `empresa` define el scope. El filtrado multi-scope se expresa como `empresa IN ["intecsa", "nombre_empresa_cliente"]`.

### Organización de colecciones en ChromaDB

- **Corpus global Intecsa:** colección `intecsa` (child) + `intecsa__parents` (parent).
- **Corpus por proyecto:** colección `{proyecto_id}_{empresa}` (child) + `{proyecto_id}_{empresa}__parents` (parent).
- Los child chunks llevan embeddings y son los que se buscan por similitud vectorial.
- Los parent chunks no tienen embeddings — se recuperan por ID para expandir el contexto antes de pasarlo al LLM.
- El retrieval filtra siempre por colección **antes** de la búsqueda vectorial.

---

## Pipeline de retrieval (Fase 1)

Implementado en `backend/app/servicios/retrieval.py`. Función pública única: `recuperar(query, proyecto_id, empresa, tipo_doc, ...)`.

### Pipeline MVP

```
query + scope (proyecto_id)
  │
  ├── 1. Vector search (ChromaDB, cosine, top-k=20)        ─┐
  ├── 2. BM25 search   (rank-bm25, en memoria, top-k=20)   ─┤
  │                                                          │
  └──►  3. Fusión ponderada (min-max + 0.5/0.5)  ◄──────────┘
             │
             ├── 4. Filtro metadatos: scope (colección) + tipo_doc opcional
             │
             └──► 5. Rerank con Cohere (rerank-multilingual-v3.0) → top-n=5
                         │
                         ▼
                    list[ChunkRecuperado]
```

### Hybrid search

- **Vector:** embeddings `text-embedding-3-small` sobre children; distancia coseno; `col.query(n_results=top_k)`.
- **BM25:** índice `rank-bm25` construido en memoria la primera vez que se consulta cada colección. Se cachea como singleton por proceso (`_cache_bm25`). Tokenización multilingüe: `\w+` en minúsculas. Tras indexar nuevos documentos hay que llamar a `invalidar_cache_bm25(coleccion)`.
- **Fusión:** cada retriever normaliza sus scores min-max → [0,1] y se combinan con los pesos `RETRIEVAL_PESO_VECTOR` y `RETRIEVAL_PESO_BM25` del `.env` (default 0.5/0.5). Se conservan las top-k combinadas para pasar al rerank.

### Filtrado por metadatos

- **Scope obligatorio** — el scope (corpus global Intecsa o proyecto concreto) se expresa como la elección de colección ChromaDB; no es un filtro `where` sino la colección sobre la que se busca. Si `proyecto_id=None`, la colección es `intecsa`; si no, `{proyecto_id}_{empresa}`.
- **`tipo_doc` opcional** — se aplica como cláusula `where` de Chroma en la consulta vectorial y como filtro post-hoc sobre los resultados de BM25. Casos típicos: `tipo_doc="procedimiento"` o `tipo_doc="anexo"`.

### Reranking

- **Modelo:** `rerank-multilingual-v3.0` (configurable vía `COHERE_RERANK_MODEL`). Soporta ES/EN/FR nativamente, necesario porque el corpus es multilingüe.
- **Input:** `query` + los top-k textos fusionados (hasta 20).
- **Output:** top-n chunks (default 5) con `relevance_score` entre 0 y 1 que sustituye al score de fusión.

### Parámetros configurables (`.env`)

| Variable | Default | Descripción |
|---|---|---|
| `RETRIEVAL_TOP_K` | 20 | Candidatos tras la fusión, antes del rerank |
| `RETRIEVAL_TOP_N` | 5 | Chunks finales devueltos al orquestador |
| `RETRIEVAL_PESO_VECTOR` | 0.5 | Peso de la señal vectorial en la fusión |
| `RETRIEVAL_PESO_BM25` | 0.5 | Peso de la señal BM25 en la fusión |
| `COHERE_API_KEY` | — | Clave de Cohere (obligatoria si se usa rerank) |
| `COHERE_RERANK_MODEL` | `rerank-multilingual-v3.0` | Modelo de rerank |

### Expansión a parents

No está en el módulo de retrieval. Los `ChunkRecuperado` devueltos son children y exponen `parent_id` en sus metadatos; el orquestador de `/query` se encargará de hacer `get(ids=[parent_id])` sobre la colección `{nombre}__parents` para expandir el contexto antes de pasarlo al LLM. Los chunks de tabla (`parent_id=""`) se pasan tal cual al LLM sin expansión.

### Fase 2 (pospuesta)

Las siguientes técnicas se evaluarán tras medir la baseline y no están implementadas:

- **Query rewriting** con GPT-4o-mini para clarificar queries vagas.
- **Sentence window retrieval** para añadir contexto adyacente al chunk recuperado.
- **Penalización de anexos** con factor × 0.7 sobre el score post-rerank.

### Evaluación

- **Métricas:** Recall@5, MRR, nDCG@5.
- **Test set:** 50–100 pares `(query, ground_truth)` construidos a partir del corpus Intecsa.
- **Enfoque:** baseline vector-only → añadir BM25 → añadir rerank → medir delta en cada paso para justificar cada técnica.

---

## API (FastAPI)

### Endpoints planificados

- `POST /query` — recibe la pregunta, el scope opcional y el historial. Devuelve respuesta en streaming SSE con la respuesta, las fuentes, el scope inferido y la confianza.
- `GET /projects` — lista de proyectos disponibles para el usuario.
- `POST /ingest` — recibe un PDF y los metadatos del administrador (empresa, proyecto_id, tipo_doc, idioma). Solo accesible por el administrador.
- `GET /health` — estado del sistema.

### Estado actual de implementación

Solo `GET /health` está implementado (`{"status": "ok"}`). El resto se implementa a medida que avanzan las fases del pipeline. Título de la app FastAPI: "IntecsaRAG" v0.1.0.

### Notas de implementación
- `/query` usa streaming SSE con `StreamingResponse` de FastAPI.
- El clasificador del router devuelve un JSON con scope, tipo y confianza. Si la confianza está por debajo del umbral, se devuelve una pregunta de clarificación al usuario.

---

## Frontend (Next.js + shadcn/ui)

### Layout principal
- **Sidebar:** lista de scopes disponibles (Global Intecsa + proyectos). Permite selección manual como fallback al router.
- **Topbar:** muestra el scope inferido y la confianza. El usuario puede corregirlo.
- **Chat:** mensajes con streaming. Cada respuesta incluye chips de fuente clicables (documento · sección · página).
- **Caja de clarificación:** cuando el router no tiene suficiente confianza, se muestra un bloque con opciones para que el usuario elija el scope.

### Despliegue
Azure Static Web Apps con conexión directa a la API en Azure Container Apps.

---

## Scripts de ingesta

- `ingest_test.py`: 7 documentos representativos que cubren todos los casos del pipeline (tablas, imágenes, anexos, multiidioma). Uso para validación antes de indexar el corpus completo.
- `ingest_all.py`: ingesta del corpus completo con descubrimiento automático vía manifesto. Auto-detecta idioma (inglés/francés en el nombre de fichero), tipo anexo (ANEXO en el nombre), y proyecto (carpeta `{proyecto_id}_{empresa}/`). Soporta modo `--dry-run` para validar sin subir a ChromaDB y salida JSON para inspección manual.
- `ingest_one.py`: ingesta de un único documento por índice.
- `inspect_docling.py`: herramienta de debug que muestra el resultado del parseo de Docling con salida coloreada por tipo de elemento.

---

## Notas para el desarrollo

- Validar el pipeline con `ingest_test.py` (7 docs) antes de lanzar `ingest_all.py` sobre el corpus completo.
- Documentar el umbral de confianza del router: hiperparámetro a calibrar con un banco de 20-30 queries con scope esperado.
- El reranker usa Cohere Rerank (`rerank-multilingual-v3.0`) sobre los top-K fragmentos fusionados. La penalización × 0.7 para chunks con `dentro_de_anexo=True` aún no está implementada — pendiente tras medir la baseline.
- Para activar descripción de imágenes y extracción de metadatos de portada: `ENABLE_VISION=1` en `.env`. Requiere `OPENAI_API_KEY` válida.
- Para demos sin despliegue: arrancar FastAPI y Next.js en local y exponer con ngrok para generar una URL pública accesible desde cualquier navegador.
- La GTX 960M no puede ejecutar los modelos PyTorch de Docling (CUDA CC 5.0 < CC 7.5 mínimo). Docling corre en CPU. Esta restricción no existe en Azure.

---

## Trabajo futuro (versión completa)

Las siguientes funcionalidades están excluidas de la beta y se implementarán en la versión completa:

- Procesado sistemático de imágenes y diagramas con GPT-4o vision en todos los documentos.
- Comparativa con fuentes externas mediante búsqueda web (Tavily).
- Indexación de normativas externas (ISO, EN, UNE, ASME).
- Tratamiento de contratos con deduplicación semántica.
- Soporte para documentos escaneados con OCR.
- Corpus ampliado: contratos, normativas, presentaciones, planos.
- Re-procesado de tablas degradadas (`tabla_degradada=True`) con GPT-4o vision.
