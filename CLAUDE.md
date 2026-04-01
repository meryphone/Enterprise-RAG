# CLAUDE.md — IntecsaRAG

Fichero de contexto del proyecto para asistencia con IA. Contiene todas las decisiones de diseño, stack tecnológico y estructura del sistema RAG desarrollado como TFG.

---

## Contexto del proyecto

**Proyecto:** Sistema RAG corporativo para Intecsa (empresa de ingeniería industrial)  
**Objetivo:** Permitir a los empleados consultar en lenguaje natural los procedimientos y especificaciones técnicas de la empresa y de sus clientes, con capacidad de comparar con fuentes externas mediante búsqueda web.  
**Tipo:** TFG de Ingeniería Informática  
**Empresa:** Intecsa — tiene licencia Microsoft, el despliegue final es en Azure.

### Características principales
- Búsqueda semántica sobre documentos internos (procedimientos, especificaciones técnicas)
- Organización por scopes: corpus global de Intecsa + corpus por proyecto/cliente
- Query Router automático que infiere el scope sin que el usuario lo indique explícitamente
- Comparativa con empresas externas mediante búsqueda web bajo demanda
- Citación de fuentes en cada respuesta (documento, sección, página)
- Respuesta en el idioma de la pregunta; los documentos pueden estar en cualquier idioma

### Idioma de los documentos
Los documentos indexados pueden estar en **cualquier idioma** — se han identificado documentos en español, inglés y francés, y puede haber otros. El modelo de embeddings debe ser multilingüe para soportar búsqueda semántica entre documentos en distintos idiomas. El LLM responde en el idioma en que el usuario formula la pregunta, independientemente del idioma del documento fuente.

---

## Fases de desarrollo

| # | Fase | Duración estimada |
|---|------|-------------------|
| 1 | RAG base — ingestión y búsqueda | ~2 semanas |
| 2 | Scopes y organización por proyecto | ~1.5 semanas |
| 3 | Query Router automático | ~2 semanas |
| 4 | Búsqueda web y comparativa externa | ~1 semana |
| 5 | Migración a Azure y despliegue | ~1 semana |

---

## Stack tecnológico

### Principio guía
**"Dev local → Azure sin reescribir."** Todos los clientes (LLM, embeddings, vector store) se abstraen detrás de una capa de configuración. Un flag `ENV=local|production` en `.env` determina qué implementación se instancia. El código de negocio nunca sabe dónde está corriendo.

### Tabla de stack por entorno

| Componente | Desarrollo local | Producción (Azure) |
|---|---|---|
| LLM | OpenAI API directa | Azure OpenAI Service (GPT-4o en tenant Intecsa) |
| Embeddings | `text-embedding-3-small` vía OpenAI API | Azure OpenAI Embeddings (`text-embedding-3-small`) |
| Vector store | ChromaDB (en disco, sin configuración) | Azure AI Search (vector + filtros de metadatos) |
| Documentos | Sistema de archivos local | Azure Blob Storage |
| Búsqueda web | Tavily API (tier gratuito) | Tavily API o Azure Bing Search API |
| Framework | LlamaIndex + FastAPI | LlamaIndex + FastAPI (igual) |
| Frontend | Next.js + shadcn/ui | Azure Static Web Apps |
| Parser de documentos | Docling (Unstructured como alternativa) | Docling (Unstructured como alternativa) |
| Visión | GPT-4o vision (OpenAI API) | GPT-4o vision (Azure OpenAI) |

### Decisiones clave

**Mismo modelo de embeddings en dev y producción:** Se usa `text-embedding-3-small` en ambos entornos. Esto elimina la necesidad de reindexar al migrar ya que los vectores son compatibles.

**LlamaIndex sobre LangChain:** Elegido por su foco específico en RAG, el concepto de `Node` con metadatos encaja con el modelo de documentos por proyecto, y el `RouterQueryEngine` es la base natural del Query Router.

**Streaming SSE:** El endpoint de query expone la respuesta como stream (Server-Sent Events) para que el frontend muestre los tokens progresivamente.

**ChromaDB → Azure AI Search:** Chroma para dev. Azure AI Search en prod. LlamaIndex tiene wrappers con interfaz idéntica para ambos.

**Docling como parser principal, Unstructured como alternativa:** Docling es una librería open source de IBM (2024) especializada en parseo de documentos para RAG. Usa modelos de visión propios (DocLayNet) entrenados sobre documentación técnica e industrial, lo que le da mejor detección de tablas complejas, mejor manejo de PDFs escaneados, y exportación nativa a Markdown. Tiene integración oficial con LlamaIndex via `DoclingReader`. Unstructured se mantiene como alternativa de fallback para casos donde Docling no rinda bien en documentos concretos del corpus. Ambos tienen la misma interfaz con LlamaIndex, por lo que el cambio entre uno y otro es transparente para el resto del pipeline.

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
  ├──► Scope: Global Intecsa      ─┐
  ├──► Scope: Proyecto/cliente    ─┤
  ├──► Scope: Multi-scope         ─┤──► Retrieval Engine
  └──► Scope: Comparativa externa ─┘        │
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

## Formato de documentos

**El único formato aceptado para ingestión es PDF.** Los documentos existentes de Intecsa han sido convertidos previamente a PDF. Cualquier documento nuevo que la empresa desee incorporar al RAG debe entregarse en formato PDF.

La conversión desde Word debe hacerse desde el propio Word, no desde LibreOffice, para preservar fuentes, tablas complejas y objetos incrustados. LibreOffice puede usarse como alternativa para documentos antiguos donde no hay otra opción, pero los PDFs resultantes deben revisarse manualmente antes de ingestar.

### Alcance: Excel operacional fuera del RAG

Los Excel de datos operacionales (MTOs mensuales, documentos de medición desglosada, Key Quantities con miles de filas de cantidades numéricas) están **fuera del scope del RAG** en esta versión. Su tratamiento preciso requeriría un componente de análisis de datos separado. Documentar como trabajo futuro en la memoria del TFG.

Los Excel de documentación (preciarios, listas de conceptos, procedimientos) sí se incluyen, convertidos previamente a PDF desde Excel.

---

## Pipeline de ingestión

El pipeline de ingestión es el script central del sistema. Recibe un PDF y los metadatos del administrador y produce chunks indexados en el vector store con todos sus metadatos.

### Flujo general

El pipeline tiene cuatro pasos secuenciales. Primero extrae los metadatos automáticos de la portada del documento usando GPT-4o vision — código del documento, edición y fecha. Segundo, Docling parsea el PDF completo y devuelve una lista de elementos tipificados con su estructura y posición en la página. Tercero, cada elemento se procesa según su tipo. Cuarto, los metadatos se ensamblan y el chunk se indexa en el vector store.

Los metadatos tienen tres orígenes que se combinan en el momento de crear cada chunk: los extraídos automáticamente de la portada por GPT-4o, los introducidos manualmente por el administrador al subir el documento, y los generados automáticamente por el pipeline (número de página, fecha de ingesta, tipo de elemento).

### Procesado por tipo de elemento

Docling clasifica cada elemento del PDF en un tipo. El tratamiento varía según el tipo:

**Title, NarrativeText, ListItem:** el texto se usa directamente. Docling ya lo ha extraído con alta fidelidad y con su estructura Markdown preservada. No se necesita GPT-4o.

**Image:** se aplica GPT-4o vision. Antes de la llamada se comprueba si la imagen es ilustrativa de ejemplo — si el texto previo en el documento contiene palabras como "ejemplo", "se puede ver", "como se muestra" o "example", se usa un prompt que describe la estructura y propósito de la imagen sin transcribir sus datos. Si es contenido real, se usa el prompt completo de descripción técnica.

**Fusión texto-imagen en la misma página:** cuando Docling devuelve un elemento `Image` contiguo a elementos de texto en la misma página — como ocurre en páginas donde una captura de software ilustra directamente las instrucciones del párrafo adyacente — ambos se fusionan en un único chunk. La descripción generada por GPT-4o de la imagen se concatena al texto del párrafo con la etiqueta `[Descripción visual:]`. Esto preserva el contexto completo en un solo chunk y mejora la precisión del embedding, que representa tanto el concepto textual como el visual juntos.

**Table:** Docling exporta las tablas directamente en Markdown preservando filas, columnas y estructura. Para tablas que son imágenes (capturas de Excel, tablas escaneadas) se aplica GPT-4o vision con instrucción explícita de devolver el resultado en Markdown, garantizando consistencia de formato en todo el índice. El chunking de tablas respeta su estructura — tablas de elementos independientes se dividen por fila, tablas jerárquicas se dividen por categoría principal, tablas de datos densos ilustrativos se describen sin transcribir los datos.

### Prompts de GPT-4o vision

**Prompt para extracción de metadatos de portada:**
"Esta es la portada de un documento técnico de Intecsa. Contiene una tabla de revisiones con varias entradas de fecha, edición y aprobación. Extrae en formato JSON: codigo_documento, edicion (la más reciente), fecha_edicion (la fecha más reciente de la tabla de revisiones), aprobado_por (nombre o iniciales del aprobador de la edición más reciente)."

**Prompt para imágenes de contenido real:**
"Analiza esta imagen de un documento técnico de ingeniería industrial. Describe con el máximo detalle todo su contenido: si hay texto, transcríbelo fielmente; si hay tablas, describe las columnas y extrae los datos que contienen; si hay diagramas o esquemas técnicos, describe los elementos, conexiones y etiquetas visibles; si hay capturas de pantalla de software, describe qué muestra la interfaz y qué acción representa. El objetivo es que alguien que no vea la imagen pueda responder preguntas técnicas basándose únicamente en tu descripción."

**Prompt para tablas en imagen (captura de Excel, tabla escaneada):**
"Esta imagen contiene una tabla de un documento técnico. Extrae su contenido y devuélvelo en formato Markdown, respetando la estructura de filas y columnas. Incluye los encabezados de columna. Si la tabla es demasiado densa o es claramente un ejemplo ilustrativo, describe su estructura y propósito en lugar de transcribir los datos."

**Prompt para imágenes ilustrativas de ejemplo:**
"Esta imagen es un ejemplo ilustrativo dentro de un documento técnico. No transcribas los datos que contiene. Describe únicamente: qué tipo de documento o tabla muestra, qué columnas o campos tiene, y para qué sirve según el contexto."

### Contenido visual no reproducible: enlace al documento original

Para contenido donde la imagen es la fuente de verdad —librerías de símbolos técnicos, diagramas P&ID complejos, planos, esquemas de proceso— el RAG no intenta reproducir el contenido visual. La estrategia es generar una descripción suficientemente rica para que el retrieval lo encuentre, y redirigir al usuario al documento original para que vea el contenido real.

Esto se implementa a través del chip de fuente en el frontend. Cada chunk tiene los metadatos `nombre_fichero` y `pagina`, con los que el frontend construye un enlace directo al PDF en la página exacta. En producción, los PDFs están en Azure Blob Storage y el enlace tiene el formato `url_blob/nombre_fichero.pdf#page=X`, que los visores PDF modernos soportan directamente.

Un empleado pregunta "¿qué símbolo se usa para un recipiente con techo flotante?". El RAG recupera el chunk que describe la tabla de símbolos, el LLM genera una respuesta describiendo el símbolo, y el chip de fuente lleva al usuario directamente a la página del documento donde está la tabla para que lo vea visualmente.

Este patrón es una decisión de diseño consciente: el RAG actúa como índice inteligente que lleva al usuario exactamente donde necesita ir, sin intentar sustituir el documento original. Documentar como decisión de diseño en la memoria del TFG.

El prompt para tablas de símbolos y librerías técnicas debe capturar suficientes términos descriptivos para que el retrieval funcione bien — mencionar todos los tipos de equipos, códigos visibles y categorías es más importante que una descripción perfectamente estructurada.

**Prompt para diagramas de flujo y esquemas de proceso:**
"Esta imagen es un diagrama técnico de ingeniería con cajas conectadas por líneas que establecen relaciones jerárquicas o de flujo. Describe todos los elementos que aparecen y las relaciones entre ellos: qué contiene cada caja, cómo están conectadas, y qué representa el flujo o jerarquía del diagrama. No intentes convertirlo a tabla o Markdown — descríbelo en prosa estructurada."

**Prompt para librerías de símbolos técnicos:**
"Esta imagen es una tabla o librería de símbolos técnicos de ingeniería industrial usados en diagramas de proceso. Para cada símbolo visible describe: su forma geométrica, los elementos que lo componen (líneas, cruces, círculos, flechas), y la etiqueta o código que lo acompaña si la tiene. Agrupa los símbolos por las categorías que aparecen en la imagen. El objetivo es que un ingeniero pueda encontrar este símbolo buscando por descripción o por código, y luego ir al documento original para verlo."

### Penalización de chunks procedentes de anexos

Los chunks con `tipo_doc: "anexo"` reciben una penalización en su score en el reranker — factor de penalización 0.7 como punto de partida, calibrable con el banco de queries de prueba. Esto no los excluye del retrieval pero los hace menos competitivos frente a chunks del cuerpo principal que traten el mismo tema. Solo prevalecen si no hay información equivalente en el cuerpo principal.

El system prompt incluye la instrucción: cuando el contexto recuperado tenga `tipo_doc: "anexo"`, usarlo solo como referencia de apoyo e indicarle al usuario que la información procede de un anexo.

### Hierarchical chunking

Tras el procesado de cada elemento, se aplica HierarchicalNodeParser de LlamaIndex para construir dos niveles de chunks. Los child chunks de aproximadamente 128 tokens son los que se indexan con embeddings y se usan para retrieval — su embedding es preciso porque representa una idea concreta. Los parent chunks de aproximadamente 512 tokens son los que se pasan al LLM cuando se recupera un child relevante — proporcionan el contexto ampliado necesario para generar una buena respuesta.

Las tablas no se subdividen en el hierarchical chunking. La tabla completa o la sección de tabla es su propio nodo indivisible.

---

## Modelo de metadatos

Cada chunk indexado en el vector store lleva los siguientes metadatos:

| Campo | Origen | Descripción |
|---|---|---|
| `doc_id` | Pipeline | UUID del documento original |
| `nombre_fichero` | Pipeline | Nombre del fichero PDF |
| `titulo_documento` | Portada (GPT-4o) | Código del documento, ej: IT-CD-09_E |
| `version` | Portada (GPT-4o) | Edición más reciente del documento |
| `fecha_documento` | Portada (GPT-4o) | Fecha de la última modificación en ISO 8601 — se extrae la entrada más reciente de la tabla de revisiones |
| `aprobado_por` | Portada (GPT-4o) | Nombre o iniciales de quien aprobó la última edición |
| `pagina` | Pipeline | Número de página |
| `seccion` | Docling | Título de sección detectado automáticamente |
| `es_imagen` | Pipeline | True si el chunk proviene de GPT-4o vision |
| `tipo_elemento` | Docling | Title, NarrativeText, Table, Image, ListItem |
| `empresa` | Administrador | "intecsa" o nombre del cliente |
| `proyecto_id` | Administrador | Código del proyecto; None si es corpus global |
| `tipo_doc` | Administrador / Pipeline | procedimiento, especificacion, normativa, plano, informe, presentacion, contrato, anexo. El valor "anexo" lo asigna el administrador al ingestar documentos que son enteramente un anexo, o el pipeline automáticamente a los chunks de secciones cuyo título contenga "ANEXO", "APPENDIX" o "ANNEX" dentro de documentos mixtos. |
| `idioma` | Administrador | Código ISO 639-1 del idioma principal del documento — "es", "en", "fr", etc. |
| `fecha_ingesta` | Pipeline | Fecha de procesado en ISO 8601 |

### Nota sobre `empresa`

El campo `empresa` reemplaza los campos `scope` y `cliente` de diseños anteriores. El scope se infiere comparando `empresa` con "intecsa". El filtrado multi-scope se expresa como empresa IN ["intecsa", "nombre_cliente"].

### Organización de colecciones

- **Corpus global Intecsa:** colección `intecsa_global` — procedimientos y especificaciones internas aplicables a todos los proyectos.
- **Corpus por proyecto:** colección `proyecto_{codigo}` — documentos del cliente y normativas específicas del proyecto.
- El retrieval filtra siempre por colección **antes** de la búsqueda vectorial.

---

## Tratamiento de contratos

Los contratos tienen características específicas que requieren decisiones de diseño propias.

### Indexación de cláusulas

Los contratos y plantillas de contrato se indexan completos en el RAG, incluyendo los chunks con placeholders como [NOMBRE CLIENTE] o [FECHA]. El LLM está instruido mediante el system prompt para identificar estos campos variables y advertir al usuario que deben rellenarse según el caso concreto. Esto permite consultar el contenido de las cláusulas — "¿qué dice nuestra cláusula estándar de confidencialidad?" — sin perder la utilidad de las plantillas.

El chunking por cláusula es la unidad natural para contratos. Docling detecta los títulos de cláusula como elementos `Title`, lo que hace que el hierarchical chunking respete automáticamente los límites entre cláusulas. El metadato `seccion` toma aquí valor especial — "Cláusula 5. Confidencialidad" permite filtrar directamente por tipo de cláusula en el retrieval.

### Documentos duplicados en distintos idiomas

Los documentos que son el mismo contenido en distintos idiomas se eliminan del corpus antes de la ingestión, conservando únicamente la versión en el idioma principal. Esto evita duplicados semánticos en el índice sin necesidad de lógica adicional en el pipeline.

### Deduplicación semántica post-ingestión

Tras indexar todos los documentos se ejecuta un paso de deduplicación semántica. Los chunks con similitud vectorial superior a 0.97 entre distintos documentos se marcan con `es_duplicado: true` en los metadatos y se excluyen del retrieval por defecto. Esto elimina el ruido de cláusulas estándar repetidas entre distintos modelos de contrato.

---



### Endpoints principales

- `POST /query` — recibe la pregunta, el scope opcional y el historial de conversación. Devuelve respuesta en streaming SSE con la respuesta, las fuentes, el scope inferido y la confianza.
- `GET /projects` — devuelve la lista de proyectos disponibles para el usuario.
- `POST /ingest` — recibe un PDF y los metadatos del administrador (empresa, proyecto_id, tipo_doc, idioma). Solo accesible por el administrador.
- `GET /health` — estado del sistema.

### Notas de implementación
- El endpoint `/query` usa streaming SSE con `StreamingResponse` de FastAPI.
- Las llamadas al LLM y a Tavily en la comparativa web se ejecutan en paralelo con `asyncio`.
- El clasificador del router devuelve un JSON con scope, tipo y confianza. Si la confianza está por debajo del umbral, se devuelve una pregunta de clarificación al usuario en lugar de ejecutar el retrieval.

---

## Frontend (Next.js + shadcn/ui)

### Layout principal
- **Sidebar:** lista de scopes disponibles (Global Intecsa + proyectos del usuario). Permite selección manual como fallback al router automático.
- **Topbar:** muestra el scope inferido por el router y la confianza. El usuario puede corregirlo.
- **Chat:** mensajes con streaming. Cada respuesta incluye chips de fuente clicables (documento · sección · página).
- **Caja de clarificación:** cuando el router no tiene suficiente confianza, se renderiza un bloque con opciones para que el usuario elija el scope.

### Despliegue
Azure Static Web Apps con conexión directa a la API en Azure Container Apps.

---

## Notas para el desarrollo

- El pipeline de ingestión es el componente más crítico del sistema. Validarlo con una muestra de documentos reales de Intecsa antes de indexar el corpus completo.
- Documentar el umbral de confianza del router: hiperparámetro a calibrar con un banco de 20-30 queries con scope esperado.
- El reranker opera sobre los top-K fragmentos del vector search. Modelo sugerido: `cross-encoder/ms-marco-MiniLM-L12-v2`.
- Para la comparativa externa (Fase 4): el prompt al LLM debe diferenciar explícitamente fuentes internas y externas en la respuesta.
- Los Excel operacionales están **fuera del scope del RAG**. Documentar como trabajo futuro en la memoria del TFG.
- Las normativas externas que Intecsa usa habitualmente pueden indexarse en la colección `normativas_externas`. Las normativas no disponibles en PDF se cubren con búsqueda web vía Tavily.
- El system prompt del LLM debe incluir instrucción explícita para tratar los placeholders de contratos — cuando el contexto contenga campos como [NOMBRE CLIENTE] o [FECHA], indicar al usuario que son campos variables a rellenar.
- La deduplicación semántica post-ingestión se ejecuta una vez tras indexar el corpus completo y se repite cada vez que se añaden documentos nuevos.
- Los diagramas de flujo y esquemas de proceso no se convierten a Markdown — se describen en prosa estructurada con GPT-4o vision y el chip de fuente lleva al usuario a la página original.
- Para la memoria del TFG: los documentos de ejemplo analizados (TUBE101.CEL — librería de símbolos P&ID, IT-ID-02 — instrucción de trabajo con capturas de Power Query, IT-CD-09_E — estructura Documentum, ANEXO II IT-AP-05 — diagrama de inspección de seccionadores) ilustran los distintos tipos de contenido que el pipeline debe manejar.
