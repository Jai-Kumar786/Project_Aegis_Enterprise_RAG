---
name: advanced-retrieval-skill
description: Teaches the agent how to build the retrieval and synthesis engine for Project Aegis using Multi-Query, Cohere ReRank, and DeepSeek.
---

# Retrieval Rules for Project Aegis
Whenever you are building the retrieval and synthesis pipelines in `backend/core/retrieval.py` and `backend/core/synthesis.py`, you MUST adhere to these rules:
1. **Query Transformation:** Never search the vector database with the raw user prompt. Always use an LLM to generate 3 alternative phrasing of the user's query (Multi-Query Expansion).
2. **The Funnel (25-to-5):** Query the Neon PostgreSQL database using the expanded queries to retrieve the Top 25 most relevant chunks.
3. **Cross-Encoder Reranking:** You MUST pass the Top 25 chunks and the user's original query through the Cohere ReRank API. Prune the results down to the Top 5 highest-scoring chunks.
4. **Synthesis:** Pass only the Top 5 reranked chunks to the DeepSeek LLM (via Ollama). Instruct the LLM to answer the question strictly based on the context provided, and enforce that it appends footnote citations (e.g., [1], [2]) corresponding to the `document_id` metadata.