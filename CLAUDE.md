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

- Solo se indexan documentos de **texto y tablas** — sin imágenes, sin diagramas, sin capturas de pantalla. No se usa GPT-4o vision.
- El corpus se limita a dos tipos: **procedimientos generales de Intecsa** y **documentos de proyectos con clientes**.
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
| Parser de documentos | Docling (Unstructured como alternativa) | Docling (Unstructured como alternativa) |
| Demo sin despliegue | ngrok | — |

> GPT-4o vision no se usa en la beta. Todos los documentos son texto con tablas extraíbles.

### Decisiones clave

**Mismo modelo de embeddings en dev y producción:** Se usa `text-embedding-3-small` en ambos entornos. Esto elimina la necesidad de reindexar al migrar ya que los vectores son compatibles.

**LlamaIndex sobre LangChain:** Elegido por su foco específico en RAG, el concepto de `Node` con metadatos encaja con el modelo de documentos por proyecto, y el `RouterQueryEngine` es la base natural del Query Router.

**Streaming SSE:** El endpoint de query expone la respuesta como stream (Server-Sent Events) para que el frontend muestre los tokens progresivamente.

**ChromaDB → Azure AI Search:** Chroma cloud para dev. Azure AI Search en prod. LlamaIndex tiene wrappers con interfaz idéntica para ambos.

**ngrok para demos sin despliegue:** Para mostrar la beta a la empresa sin necesidad de desplegar en Azure, ngrok crea un túnel desde internet hasta la aplicación corriendo en local. Genera una URL pública temporal que cualquier persona puede abrir desde su navegador. Solo requiere tener la aplicación arrancada en local y ejecutar ngrok apuntando al puerto de FastAPI y al de Next.js.

**Docling como parser principal, Unstructured como alternativa:** Docling es una librería open source de IBM (2024) especializada en parseo de documentos para RAG. Exporta tablas directamente en Markdown y detecta bien la estructura de secciones. Unstructured se mantiene como alternativa de fallback. Ambos tienen la misma interfaz con LlamaIndex.

**Descripción de imágenes vía Ollama (dev local):** En desarrollo local, la descripción de imágenes se delega a Ollama (`localhost:11434`) con el modelo `ibm/granite-docling:258m`. Ollama corre como proceso separado con su propio stack de GPU (llama.cpp), independiente del PyTorch del proceso Python. En producción (Azure) se usará GPT-4o vision directamente.

**CPU para modelos de Docling en dev local:** La GTX 960M (CUDA CC 5.0) no es compatible con PyTorch 2.6+ (mínimo CC 7.5 en las wheels oficiales). Downgrade a PyTorch 2.0.x requeriría Python ≤ 3.11, incompatible con el entorno. Se fuerza CPU con `os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")` en `parser.py` antes de importar Docling. Esta línea se elimina al desplegar en Azure. Los modelos de layout y TableFormer corren en CPU; solo la descripción de imágenes usa GPU a través de Ollama.

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
                                         ├── Vector search + filtro metadatos
                                         ├── Reranker (cross-encoder)
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

**Corpus por proyecto** — documentos generados en proyectos con clientes: especificaciones técnicas, instrucciones de trabajo, informes. Una colección por proyecto: `{codigo}_empresa`.

### Criterios de selección de documentos para la beta

Solo se incluyen documentos que cumplan todos estos criterios:

- Formato PDF con texto extraíble digitalmente — sin documentos escaneados.
- Contenido principalmente textual — se admiten tablas simples con texto extraíble, sin imágenes relevantes ni diagramas.
- Idioma identificable — español, inglés o francés.
- Los documentos que son el mismo contenido en distintos idiomas se eliminan antes de la ingestión, conservando únicamente la versión en el idioma principal.

---

## Pipeline de ingestión

El pipeline recibe un PDF y los metadatos del administrador y produce chunks indexados en el vector store.

### Flujo general

Cuatro pasos secuenciales. Primero, Docling parsea el PDF y extrae los metadatos de la cabecera y portada del documento. La cabecera que aparece en todas las páginas contiene el código del documento (ej: PR-17), el título (ej: PROCEDIMIENTO DE ARCHIVO DE DOCUMENTOS) y la edición — Docling los extrae del texto digital directamente. La fecha de la última modificación se obtiene de la tabla de revisiones de la portada, tomando la entrada más reciente. Segundo, Docling devuelve los elementos tipificados del documento. Tercero, cada elemento se procesa según su tipo. Cuarto, los metadatos se ensamblan y el chunk se indexa.

Los metadatos tienen tres orígenes: los extraídos de la portada por Docling, los introducidos por el administrador al subir el documento, y los generados por el pipeline (número de página, fecha de ingesta).

### Arquitectura del pipeline (pipes and filters)

```
DoclingDocument → [ElementoProcesado] → [Chunk] → vector store
```

- `elementos.py`: recorre los items del `DoclingDocument` y produce una lista plana de `ElementoProcesado`. Decide qué hacer con cada tipo (texto tal cual, tabla a Markdown, imagen descrita) y aplica la regla de fusión texto-imagen.
- `chunker.py`: recibe la lista de `ElementoProcesado` y aplica hierarchical chunking con LlamaIndex, produciendo la lista de `Chunk` lista para indexar.
- El código de negocio (pipeline, retrieval) solo ve `Chunk` — nunca sabe qué hizo Docling internamente.

### Procesado por tipo de elemento

**SectionHeaderItem:** no genera `ElementoProcesado`. Solo actualiza `seccion_actual` y el flag `dentro_de_anexo`. Esto evita que secciones sin cuerpo produzcan segmentos de un solo título, que LlamaIndex no puede subdividir y que generan pares parent==child idénticos.

**NarrativeText, ListItem:** el texto se usa directamente.

**Table:** exportado a Markdown con `export_to_markdown()`. Se eligió Markdown sobre HTML porque es 3-4× más eficiente en tokens y produce el mismo resultado para el LLM y los embeddings — Docling concatena el contenido de celdas fusionadas antes de exportar, independientemente del formato de salida. Las tablas con celdas fusionadas (merged cells) se marcan con `tabla_degradada=True` detectando el patrón `\|\s{10,}\|` en el Markdown resultante.

**Image:** la primera `PictureItem` de cada documento es siempre el logo corporativo de Intecsa — se descarta sin procesar. Para el resto:
- Si la imagen es contigua a texto narrativo o list item en la misma página, su descripción se fusiona en el chunk de texto anterior como `[Descripción visual: ...]` y se marca `es_imagen=True`.
- Si no hay fusión posible y `ENABLE_VISION=0`, el elemento se descarta — un marcador `[VISION_DESHABILITADA]` no aporta nada al retrieval.
- Si no hay fusión posible y `ENABLE_VISION=1`, se emite como chunk standalone de tipo `Image`.

### Penalización de chunks de anexos

Los chunks con `tipo_doc: "anexo"` reciben un factor de penalización de 0.7 en el reranker. No se excluyen del retrieval pero son menos competitivos frente a chunks del cuerpo principal. El valor es calibrable con el banco de queries de prueba.

El system prompt incluye la instrucción de indicarle al usuario cuando la información procede de un anexo.

### Hierarchical chunking

Se aplica `HierarchicalNodeParser` de LlamaIndex sobre los segmentos de prosa:

- **Child chunks (~128 tokens):** indexados con embeddings, usados para retrieval preciso.
- **Parent chunks (~512 tokens):** pasados al LLM cuando se recupera un child relevante, proporcionan contexto ampliado para la respuesta.
- Si LlamaIndex no puede subdividir un segmento (texto < 128 tokens), el child idéntico al parent se descarta — solo se indexa el parent.

**Tablas:** se emiten como un único chunk de nivel `child` con `parent_id=None`. No tienen parent porque la tabla completa es su propio contexto — un parent idéntico no aportaría nada al LLM. Cuando el retrieval recupera un chunk de tabla con `parent_id=None`, lo pasa directamente al LLM sin expansión.

---

## Modelo de metadatos

Cada chunk indexado en el vector store lleva los siguientes metadatos:

| Campo | Origen | Descripción |
|---|---|---|
| `doc_id` | Cabecera (Docling) | Código del documento extraído de la cabecera, ej: PR-17 |
| `titulo_documento` | Cabecera (Docling) | Título del documento extraído de la cabecera, ej: PROCEDIMIENTO DE ARCHIVO DE DOCUMENTOS |
| `version` | Cabecera (Docling) | Edición del documento extraída de la cabecera |
| `fecha_edicion` | Portada (Docling) | Fecha de la última modificación — entrada más reciente de la tabla de revisiones |
| `pagina` | Pipeline | Número de página |
| `seccion` | Docling | Título de sección detectado automáticamente |
| `tipo_elemento` | Docling | Title, NarrativeText, Table, ListItem |
| `empresa` | Administrador | "intecsa" o nombre del cliente |
| `proyecto_id` | Administrador | Código del proyecto; None si es corpus global |
| `tipo_doc` | Administrador / Pipeline | procedimiento, especificacion, informe, anexo. "anexo" lo asigna el administrador o el pipeline cuando detecta una sección con título ANEXO/APPENDIX/ANNEX. | 
| `fecha_ingesta` | Pipeline | Fecha de procesado en ISO 8601 |
| `idioma` | Administrador / Pipeline | Código ISO 639-1 del idioma principal del documento — "es", "en", "fr", etc. |
| `tabla_degradada` | Pipeline | `true` si la tabla tiene celdas fusionadas que Docling no pudo separar (merged cells). Candidata a re-procesar con visión en la versión completa. |
| `es_imagen` | Pipeline | `true` si el chunk incorpora una descripción visual (fusión texto+imagen o chunk standalone de imagen). |
| `dentro_de_anexo` | Pipeline | `true` si el chunk pertenece a una sección cuyo título contiene ANEXO/APPENDIX/ANNEX. |

### Nota sobre `empresa`

El campo `empresa` define el scope. Se infiere comparando con "intecsa". El filtrado multi-scope se expresa como `empresa IN ["intecsa", "nombre_empresa_cliente"]`.

### Organización de colecciones

- **Corpus global Intecsa:** colección `intecsa`.
- **Corpus por proyecto:** colección `{codigo}_empresa`.
- El retrieval filtra siempre por colección **antes** de la búsqueda vectorial.

---

## API (FastAPI)

### Endpoints

- `POST /query` — recibe la pregunta, el scope opcional y el historial. Devuelve respuesta en streaming SSE con la respuesta, las fuentes, el scope inferido y la confianza.
- `GET /projects` — lista de proyectos disponibles para el usuario.
- `POST /ingest` — recibe un PDF y los metadatos del administrador (empresa, proyecto_id, tipo_doc, idioma). Solo accesible por el administrador.
- `GET /health` — estado del sistema.

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

## Notas para el desarrollo

- Validar el pipeline con una muestra de documentos reales antes de indexar el corpus completo.
- Documentar el umbral de confianza del router: hiperparámetro a calibrar con un banco de 20-30 queries con scope esperado.
- El reranker opera sobre los top-K fragmentos. Modelo sugerido: `cross-encoder/ms-marco-MiniLM-L12-v2`.
- Los metadatos de cabecera (título, código, edición) los extrae Docling del texto repetido en la cabecera de cada página. La fecha de última modificación se extrae de la tabla de revisiones de la portada.
- Para dev local: arrancar Ollama con `ollama run ibm/granite-docling:258m` antes de ejecutar el pipeline si se quiere descripción de imágenes activa.
- Para demos sin despliegue: arrancar FastAPI y Next.js en local y exponer con ngrok para generar una URL pública accesible desde cualquier navegador.

---

## Trabajo futuro (versión completa)

Las siguientes funcionalidades están excluidas de la beta y se implementarán en la versión completa:

- Procesado de imágenes, diagramas y capturas de pantalla con GPT-4o vision.
- Comparativa con fuentes externas mediante búsqueda web (Tavily).
- Indexación de normativas externas (ISO, EN, UNE, ASME).
- Tratamiento de contratos con deduplicación semántica.
- Soporte para documentos escaneados con OCR.
- Corpus ampliado: contratos, normativas, presentaciones, planos.
