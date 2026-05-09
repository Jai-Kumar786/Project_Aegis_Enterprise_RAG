<div align="center">
  <img src="https://img.shields.io/badge/Status-Production_Ready-success?style=for-the-badge" alt="Status" />
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=next.js&logoColor=white" alt="Next.js" />
  <img src="https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
</div>

<br />

<div align="center">
  <h1 align="center">Project Aegis</h1>
  <p align="center">
    <strong>Advanced Enterprise Retrieval-Augmented Generation (RAG) System</strong>
    <br />
    A highly performant, secure, and context-aware AI assistant designed to navigate dense corporate policies and documentation.
  </p>
</div>

---

## 📖 Overview

Project Aegis solves the enterprise knowledge discovery problem by enabling employees to ask natural language questions and receive highly accurate, strictly grounded answers based entirely on internal corporate policies. 

Moving beyond "naive RAG", Aegis employs a sophisticated **3-stage retrieval pipeline**, conversational memory, and strict anti-hallucination guardrails to ensure that AI responses are both relevant and factually secure.

## 🏗️ Architecture & Tech Stack

Aegis is built on a decoupled, modern architecture designed for scale and maintainability:

### Frontend
- **Framework:** Next.js (App Router), React, TypeScript
- **Styling:** Tailwind CSS (Custom Dark Glassmorphism Aesthetic)
- **Features:** Real-time token streaming (SSE), Markdown rendering, Passcode-protected Document Management Sidebar.

### Backend
- **Framework:** FastAPI (Python 3.11+)
- **Data Contracts:** Pydantic models for strict type validation between layers.

### Database & Search
- **Vector Database:** Neon (Serverless PostgreSQL)
- **Indexing:** `pgvector` with HNSW (Hierarchical Navigable Small World) indexes for rapid, high-dimensional semantic search.

### AI & Embeddings
- **Embeddings:** Qwen 3 (4096 dimensions) via HuggingFace Inference API.
- **ReRanker:** Cohere ReRank (cross-encoder optimization).
- **Generator / LLM:** DeepSeek V3 (via Ollama/Local Inference).

---

## ✨ Key Features

- **Multi-Format Document Ingestion:** Seamlessly upload and process Markdown (`.md`), Text (`.txt`), and Digital PDFs (`.pdf`). Text is automatically extracted, chunked, and vectorized.
- **Advanced 3-Stage Retrieval:**
  1. **Multi-Query Expansion:** The user's prompt is rewritten into multiple semantic variations by the LLM.
  2. **Vector Search:** Fast HNSW similarity search retrieves top candidate chunks from PostgreSQL.
  3. **ReRanking:** Cohere's cross-encoder accurately scores and sorts the candidates, drastically improving relevance.
- **Strict Anti-Hallucination Guardrails:** An integrated *Relevance Gate* calculates the similarity score of retrieved chunks. If the query is off-topic (e.g., "What is the capital of France?"), the pipeline short-circuits *before* hitting the LLM, returning a canned rejection.
- **Stateful Conversational Memory:** The frontend passes session history to the backend, enabling the LLM to understand and respond accurately to short follow-up questions.
- **Meta-Query Interception:** System intelligently bypasses the vector search for structural meta-queries (e.g., "List all policies"), hitting standard SQL endpoints for zero-hallucination, instantaneous results.
- **Secure Document Management:** Document uploads and deletions are protected by environment-level `X-Upload-Passcode` headers to prevent unauthorized database modifications.

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm
- PostgreSQL Database (Neon DB recommended)
- API Keys: Cohere, HuggingFace
- Ollama (running DeepSeek model locally)

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python -m venv aegis-env
source aegis-env/bin/activate  # On Windows: aegis-env\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure Environment Variables
cp .env.example .env
# Edit .env with your NEON_DATABASE_URL, COHERE_API_KEY, HF_TOKEN, etc.

# Initialize Database Schema
python -m db.init_db

# Start the FastAPI Server
fastapi dev main.py
```

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start the Next.js Development Server
npm run dev
```

### 3. Usage
Navigate to `http://localhost:3000` in your browser. 
1. Open the sidebar menu (or tap the hamburger menu on mobile).
2. Click **Upload Document**, enter your admin passcode, and upload a policy PDF or Markdown file.
3. Start chatting! Ask questions about the policy, ask follow-up questions, or ask it to "List all ingested policies."

---

## 🛡️ Security & Guardrails
Aegis prioritizes data integrity and factual accuracy:
- **No Prompt Injection Execution:** The system prompt strictly bounds the AI to the provided context.
- **Fail-Fast Gating:** LLM tokens are only generated if the ReRanker confidence score exceeds the `RERANK_RELEVANCE_THRESHOLD`.

## 📄 License
This project is proprietary and confidential. Unauthorized copying, distribution, or use of this project is strictly prohibited.
