# INTECSA RAG — Contexto del Proyecto

## Descripción
Sistema RAG multi-colección para INTECSA (ingeniería industrial).
Permite consultar procedimientos internos y especificaciones de clientes
en lenguaje natural con referencias exactas a documento y página.

## Stack
- Base vectorial: ChromaDB (desarrollo) → Azure AI Search (producción)
- Embeddings: OpenAI text-embedding-3-small
- LLM: gpt-4o-mini (consultas) / gpt-4o (comparaciones)
- Backend: FastAPI
- Frontend: Streamlit
- Orquestación: LangChain + LangGraph

## Estructura de colecciones
- intecsa_procedimientos_generales
- intecsa_it_{af|ap|co|dcd|el|gc|id|in|me|oc|pe|pr|prl|so|tu}
- proyecto_{código}_{cliente}
- procedimientos_otras_empresas

## Convenciones
- Respuestas en función del idioma que haya preguntado el usuario.
- Metadatos obligatorios: source_file, page, collection_id, owner, area
- chunk_size=1000, chunk_overlap=200
- Batches de 100 chunks para llamadas a la API de embeddings
