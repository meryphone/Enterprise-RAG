# Enterprise RAG System

> **A corporate Retrieval-Augmented Generation (RAG) system for querying engineering procedures and client methodologies.**
> 
> ![Python](https://img.shields.io/badge/Python-3.11+-blue.svg) ![Next.js](https://img.shields.io/badge/Next.js-14-black.svg) ![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg) ![ChromaDB](https://img.shields.io/badge/ChromaDB-Cloud-orange.svg) ![License](https://img.shields.io/badge/License-Proprietary-red.svg)

## Overview

This project implements an advanced RAG system tailored for an industrial engineering company. It enables employees to query company-wide procedures and specific client project methodologies using natural language, directly answering queries with citations. Developed as part of a final degree project (TFG) in Computer Engineering.

## Architecture

```text
       ┌───────────┐     ┌───────────┐     ┌───────────┐     ┌────────────┐
PDF ──►│  Docling  ├───►│  Chunker  ├───►│ ChromaDB  │◄────┤ Hybrid Ret.│
       └───────────┘     └───────────┘     └─────┬─────┘     └─────┬──────┘
                                                 │                 │
                                                 ▼                 │
     ┌───────────┐     ┌───────────┐       ┌───────────┐           │
UI ◄──┤    SSE    │◄────┤  GPT-4o   │◄──────┤  Cohere   │◄──────────┘
     └───────────┘     └───────────┘       └───────────┘
```

## Tech Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| LLM | GPT-4o | Superior reasoning and adherence to XML context structures |
| Embeddings | `text-embedding-3-large` | High dimensionality (3072), excellent multilingual performance |
| Vector Store | ChromaDB Cloud | Seamless transition from local to cloud without re-indexing |
| Parser | IBM Docling | Extracts tables as Markdown, understands technical PDF layouts |
| Reranker | Cohere `rerank-multilingual-v3.0` | Improves retrieval relevance over raw cosine distance |
| Sparse Search | BM25 (`rank-bm25`) | Exact-match retrieval for technical document codes (e.g., PR-01) |
| Backend | FastAPI | High-performance async Python, optimal for streaming LLM responses |
| Frontend | Next.js 14 + shadcn/ui | React framework with great SSE streaming capabilities |

## Project Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/        # FastAPI endpoints
│   │   ├── ingestion/  # Parsing, chunking, and document processing
│   │   └── rag/        # Vector search, BM25, and query generation
│   ├── scripts/        # Ingestion and evaluation cli scripts
│   └── tests/          # Pytest suite
├── data/               # Local data (PDFs, chromadb cache)
│   └── docs/           # Corpus organized by globals/projects
├── frontend/           # Next.js 14 Web UI
│   ├── app/            # App router pages
│   ├── components/     # React UI components (Sidebar, ChatArea, etc.)
│   └── lib/            # Types and utility functions
├── .env.example        # Environment variables template
└── README.md           # This file
```

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+ (Node 20+ recommended)
- API Keys for OpenAI, Cohere, and ChromaDB Platform

Copy the environment template and insert your keys:
```bash
cp .env.example .env
```

### 1. Start the Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 2. Start the Frontend
```bash
cd frontend
npm install
npm run dev
```

### 3. Ingest Documents
```bash
# Ingest the entire corpus
python backend/scripts/ingest_beta.py
```

## Ingestion Pipeline

The system uses a highly optimized processing pipeline:
1. **Docling Parser**: Instantiated as a singleton to avoid 30s initialization penalty. Extracts tables directly to Markdown and identifies standard document metadata.
2. **Hierarchical Chunker**: Separates content into small `children` (~128 tokens) for semantic precision and large `parents` (~1024 tokens) to provide deeper context to the LLM. 
3. **Embedding Strategy**: Document titles and codes are prefixed to the embedding text without polluting the final LLM context space.

## Retrieval Pipeline

1. **Dual Query Rewriting**: GPT-4o-mini generates two parallel expansions: a semantic variation for vector search and a keyword extraction for BM25.
2. **Hybrid Search**: Combines Cosine distance (vector) and `rank-bm25` (lexical), merging scores with a `[0,1]` Min-Max normalization.
3. **Reranking**: Cohere reorders the top candidates against the *original* user query for maximal intent fidelity.
4. **Parent Expansion**: Extends matched 128-token children into their 1024-token parent text chunks directly from ChromaDB.

## Evaluation

We employ the **TruLens** RAG Triad (Context Relevance, Answer Relevance, Groundedness) using GPT-4o as a blind judge.

```bash
cd backend
python scripts/eval_trulens.py --reset --no-dashboard
```

## Roadmap

- **Query Router**: Automatically infer scope (global vs. project) directly from user questions with a zero-shot classifier.
- **POST /ingest**: Allow administrators to upload new PDFs from the UI.
- **Document-level Pre-filter**: Pre-filter ChromaDB by specific document names when users explicitly provide technical codes in their intent.

