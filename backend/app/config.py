"""Configuración central del sistema.
El flag ENV decide qué clientes se instancian; el código de negocio no lo sabe.
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
    openai_api_key: str | None      # clave OpenAI (dev) o None si no hay
    llm_model: str                  # modelo para vision / extracción
    embedding_model: str            # modelo de embeddings (mismo en dev y prod)
    child_chunk_tokens: int         # tamaño aproximado child chunk
    parent_chunk_tokens: int        # tamaño aproximado parent chunk
    enable_vision: bool             # si False, se omiten llamadas GPT-4o vision
    chroma_api_key: str | None      # ChromaDB cloud API key
    chroma_tenant: str | None       # ChromaDB tenant ID
    chroma_database: str            # ChromaDB database name

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
        )


SETTINGS = Settings.from_env()
