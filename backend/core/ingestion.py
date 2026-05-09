"""
backend/core/ingestion.py

Enterprise document ingestion pipeline for Project Aegis.

Rules (from document-ingestion-skill):
  1. Never split text by arbitrary character counts.
  2. Always use MarkdownHeaderTextSplitter as the primary splitter.
  3. Fallback chunking uses a max of 1024 tokens with 10% overlap.
  4. Tables are always flattened to Markdown; column headers are re-appended
     to any chunk that contains split table rows.
  5. Metadata is validated through the PolicyMetadata Pydantic model.

Schema alignment:
  - Persists to: id (UUID), document_id, chunk_text, embedding (1536-dim), metadata (JSONB)
  - HNSW index is used (1536 dims is within pgvector's 2000-dim HNSW limit).
  - Embedding model: BAAI/bge-large-en-v1.5 via HuggingFace (1024-dim)
    OR sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (768-dim).
    Configure EMBEDDING_MODEL in .env; default is set to a 1536-dim compatible model.
"""

from __future__ import annotations

import re
import os
import logging
import json
from typing import Any

import psycopg2
from psycopg2.extras import execute_values
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from backend.models.schemas import ChunkMetadata, PolicyMetadata

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

HEADERS_TO_SPLIT_ON = [
    ("#", "H1"),
    ("##", "H2"),
    ("###", "H3"),
    ("####", "H4"),
]

EMBEDDING_DIM = 1024

# Fallback splitter: ~1024 tokens × 4 chars/token; 10% overlap
FALLBACK_CHUNK_SIZE = 1024 * 4
FALLBACK_CHUNK_OVERLAP = int(FALLBACK_CHUNK_SIZE * 0.10)


# ──────────────────────────────────────────────
# Table Utilities
# ──────────────────────────────────────────────

def _extract_table_header(text: str) -> str | None:
    """Return the first header row of a Markdown table found in *text*, or None."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            return line
    return None


def _flatten_table(text: str) -> str:
    """Ensure Markdown tables are separated from prose by blank lines."""
    text = re.sub(r"(\|[^\n]+\|)\n(?!\|)", r"\1\n\n", text)
    text = re.sub(r"(?<!\n\n)(\|[^\n]+\|)", r"\n\n\1", text)
    return text


def _reattach_table_headers(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-prepend table header rows to chunks that lost them during splitting."""
    result = []
    last_header: str | None = None

    for chunk in chunks:
        content: str = chunk["chunk_text"]
        lines = content.splitlines()
        has_table_row = any(l.strip().startswith("|") for l in lines)
        has_header_row = any(
            l.strip().startswith("|") and "---" in l for l in lines
        )

        if has_table_row:
            potential_header = _extract_table_header(content)
            if potential_header:
                last_header = potential_header
            if has_table_row and not has_header_row and last_header:
                content = f"{last_header}\n|---|---|\n{content}"
                chunk = {**chunk, "chunk_text": content}

        result.append(chunk)

    return result


# ──────────────────────────────────────────────
# Splitter
# ──────────────────────────────────────────────

def split_document(markdown_text: str) -> list[dict[str, Any]]:
    """
    Split a Markdown policy document into semantically coherent chunks.

    Returns a list of dicts with keys: ``chunk_text``, ``section_header``.
    """
    markdown_text = _flatten_table(markdown_text)

    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=False,
    )
    primary_chunks = splitter.split_text(markdown_text)

    fallback_splitter = RecursiveCharacterTextSplitter(
        chunk_size=FALLBACK_CHUNK_SIZE,
        chunk_overlap=FALLBACK_CHUNK_OVERLAP,
    )

    final_chunks: list[dict[str, Any]] = []
    for doc in primary_chunks:
        content = doc.page_content.strip()
        if not content:
            continue

        header_parts = [v for k, v in sorted(doc.metadata.items()) if v]
        section_header = " > ".join(header_parts) if header_parts else None

        if len(content) > FALLBACK_CHUNK_SIZE:
            for sub in fallback_splitter.split_text(content):
                final_chunks.append(
                    {"chunk_text": sub.strip(), "section_header": section_header}
                )
        else:
            final_chunks.append(
                {"chunk_text": content, "section_header": section_header}
            )

    final_chunks = _reattach_table_headers(final_chunks)
    return final_chunks


# ──────────────────────────────────────────────
# Embedding (1536 dims via HuggingFace)
# ──────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate 1024-dim embeddings via the Cohere API."""
    import cohere

    api_key = os.environ["COHERE_API_KEY"]
    co = cohere.Client(api_key)
    
    response = co.embed(
        texts=texts,
        model="embed-english-v3.0",
        input_type="search_document"
    )
    return response.embeddings


# ──────────────────────────────────────────────
# Database Persistence
# ──────────────────────────────────────────────

def _get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(os.environ["NEON_DATABASE_URL"])


def ingest_document(
    markdown_text: str,
    metadata: PolicyMetadata,
    batch_size: int = 32,
) -> int:
    """
    Full ingestion pipeline:
      1. Split the document into chunks.
      2. Embed each chunk in batches (1536 dims).
      3. Persist to `policy_chunks` (id, document_id, chunk_text, embedding, metadata JSONB).

    Returns the number of chunks ingested.
    """
    chunks = split_document(markdown_text)
    logger.info("Split '%s' into %d chunks.", metadata.document_id, len(chunks))

    all_embeddings: list[list[float]] = []
    texts = [c["chunk_text"] for c in chunks]
    for start in range(0, len(texts), batch_size):
        batch = texts[start: start + batch_size]
        logger.info("Embedding batch %d–%d…", start, start + len(batch))
        all_embeddings.extend(embed_texts(batch))

    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            rows = [
                (
                    metadata.document_id,
                    chunks[i]["chunk_text"],
                    embedding,
                    json.dumps({
                        "policy_category": metadata.policy_category,
                        "effective_date": str(metadata.effective_date),
                        "target_audience": metadata.target_audience,
                        "chunk_index": i,
                        "section_header": chunks[i].get("section_header"),
                        "token_count": len(chunks[i]["chunk_text"].split()),
                    }),
                )
                for i, embedding in enumerate(all_embeddings)
            ]
            execute_values(
                cur,
                """
                INSERT INTO policy_chunks
                    (document_id, chunk_text, embedding, metadata)
                VALUES %s
                """,
                rows,
                template="(%s, %s, %s::vector, %s::jsonb)",
            )
        conn.commit()
        logger.info("Persisted %d chunks for '%s'.", len(rows), metadata.document_id)
        return len(rows)
    finally:
        conn.close()

if __name__ == "__main__":
    from dotenv import load_dotenv
    import os
    
    # Load the .env file from the backend folder
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    
    # Configure basic logging for the test
    logging.basicConfig(level=logging.INFO)
    
    # Dummy policy text
    sample_markdown = """
# Remote Work Policy
## 1. Overview
Employees may work remotely up to 3 days a week.

## 2. Equipment
The company provides a laptop and monitor.

| Item | Allowance |
|---|---|
| Desk | $500 |
| Chair | $300 |
"""
    
    # Dummy metadata
    sample_meta = PolicyMetadata(
        document_id="POL-TEST-001",
        policy_category="HR",
        effective_date="2024-05-01",
        target_audience="All Employees"
    )
    
    logger.info("Testing ingestion pipeline...")
    chunks_inserted = ingest_document(sample_markdown, sample_meta)
    logger.info(f"Test completed. Inserted {chunks_inserted} chunks.")

