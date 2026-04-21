"""Central configuration loaded from environment variables.

All settings are read once at import time via ``Settings.from_env()``.
Production (Azure) swaps OpenAI direct calls for Azure OpenAI Service;
no other code needs to change.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Cargamos .env desde la raíz del proyecto (un nivel arriba de backend/).
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_FILE, override=False)

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = DATA_DIR / "docs"
PARSED_DIR = DATA_DIR / "parsed"  # salida del pipeline de ingesta (JSON inspectable)


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

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.getenv("ENV", "local").lower()
        api_key = os.getenv("OPENAI_API_KEY") or None
        return cls(
            env=env,
            openai_api_key=api_key,
            llm_model=os.getenv("LLM_MODEL", "gpt-4o"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            child_chunk_tokens=int(os.getenv("CHILD_CHUNK_TOKENS", "128")),
            parent_chunk_tokens=int(os.getenv("PARENT_CHUNK_TOKENS", "512")),
            enable_vision=bool(api_key) and os.getenv("ENABLE_VISION", "1") == "1",
            chroma_api_key=os.getenv("CHROMA_API_KEY") or None,
            chroma_tenant=os.getenv("CHROMA_TENANT") or None,
            chroma_database=os.getenv("CHROMA_DATABASE", "default"),
            cohere_api_key=os.getenv("COHERE_API_KEY") or None,
            cohere_rerank_model=os.getenv("COHERE_RERANK_MODEL", "rerank-multilingual-v3.0"),
            retrieval_top_k=int(os.getenv("RETRIEVAL_TOP_K", "30")),
            retrieval_top_n=int(os.getenv("RETRIEVAL_TOP_N", "5")),
            retrieval_peso_vector=float(os.getenv("RETRIEVAL_PESO_VECTOR", "0.5")),
            retrieval_peso_bm25=float(os.getenv("RETRIEVAL_PESO_BM25", "0.5")),
        )


SETTINGS = Settings.from_env()
