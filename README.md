# Implementación de RAG Empresarial en Azure AI: Automatización de Consultas de Procesos con Benchmarking Externo

---

## Instrucciones de uso

### Requisitos previos

- Python 3.11+
- Node.js 18+
- Fichero `.env` en la raíz con las claves configuradas (`OPENAI_API_KEY`, `COHERE_API_KEY`, `CHROMA_API_KEY`, `CHROMA_TENANT`)

### 1. Instalar dependencias

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

### 2. Arrancar el backend

```bash
cd backend
uvicorn app.main:app --reload
```

API disponible en `http://localhost:8000`. Endpoints: `GET /health`, `GET /projects`, `POST /query`.

### 3. Arrancar el frontend

```bash
cd frontend
npm run dev
```

UI disponible en `http://localhost:3000` (o el siguiente puerto libre).

### 4. Ingestar documentos

```bash
# Un documento
python backend/scripts/ingest_one.py data/docs/intecsa/procedimientos_generales/PR-01.pdf

# Corpus completo
python backend/scripts/ingest_beta.py

# Flags útiles: --tipo, --idioma, --empresa, --proyecto, --anexo-de
```

Tras reingestar, reiniciar el backend para que el índice BM25 se reconstruya con los nuevos datos.

### 5. Evaluar calidad del RAG

```bash
cd backend
python scripts/eval_trulens.py --reset --no-dashboard
```

Métricas: Context Relevance, Answer Relevance, Groundedness (evaluadas con GPT-4o). Requiere `pip install trulens trulens-providers-openai`.

### Demo sin despliegue

Para exponer la aplicación local con una URL pública temporal:

```bash
ngrok http 8000   # túnel para el backend
ngrok http 3000   # túnel para el frontend
```

