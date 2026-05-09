---
name: document-ingestion-skill
description: Teaches the agent how to write ingestion pipelines for corporate policies using LangChain MarkdownHeaderTextSplitter and Qwen embeddings.
---

# Ingestion Rules for Project Aegis
Whenever you are asked to write ingestion code in `backend/core/ingestion.py`, you MUST adhere to these rules:
1. Never split text by arbitrary character counts.
2. Always use `MarkdownHeaderTextSplitter` from LangChain.
3. Fallback chunking should use a maximum of 1024 tokens with a 10% overlap.
4. Always flatten tables to Markdown format. If a table splits across chunks, you must append the column headers to the resulting chunks.
5. Generate a Pydantic model for metadata extraction including `document_id`, `policy_category`, `effective_date`, and `target_audience`.