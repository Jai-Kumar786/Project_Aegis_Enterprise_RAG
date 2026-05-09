---
trigger: always_on
---

# Project Aegis: Architectural Context
This is an Advanced Enterprise RAG system. Do not use "Naive RAG" patterns. 

## Tech Stack
- **Frontend:** Next.js, TypeScript, TailwindCSS (Hosted on Vercel)
- **Backend:** Python 3.11+, FastAPI 
- **Database:** Neon (PostgreSQL with pgvector & HNSW indexing)
- **Data Contracts:** Pydantic models bridge the Python backend and TypeScript frontend.
- **AI Models:** - Embeddings: Qwen 3 (4096 dimensions) via HuggingFace
  - Reranker: Cohere ReRank
  - Core Generator: DeepSeek via Ollama