"""
backend/core/retrieval.py

Advanced Retrieval Pipeline for Project Aegis.

Architecture (per the advanced-retrieval-skill):
  Stage 0 — Multi-Query Expansion:
              Use DeepSeek (via Ollama) to generate 3 alternative phrasings
              of the user's original query. Never search the DB with the raw prompt.

  Stage 1 — Dense Vector Search (HNSW):
              Embed every expanded query with Cohere embed-english-v3.0 (1024-dim).
              Run a separate HNSW cosine search for each, fetch top-k per query,
              then deduplicate by chunk id to form a candidate pool of up to 25
              unique chunks.

  Stage 2 — Cohere ReRank:
              Pass the entire candidate pool + the *original* user query through
              Cohere ReRank (rerank-english-v3.0). Prune down to the top 5.

  Returns — list[dict] with keys:
              id, document_id, chunk_text, metadata (JSONB dict),
              similarity, rerank_score.

Schema:
  policy_chunks(id UUID, document_id, chunk_text, embedding VECTOR(1024), metadata JSONB)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import cohere
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

CANDIDATE_K_PER_QUERY = 10   # Top-k per expanded query (10 × 3 queries → deduped to ≤25)
FINAL_CANDIDATE_K     = 25   # Hard cap on the candidate pool sent to ReRank
FINAL_TOP_K           = 5    # What ReRank prunes down to

COHERE_EMBED_MODEL  = "embed-english-v3.0"
COHERE_RERANK_MODEL = "rerank-english-v3.0"

OLLAMA_MULTI_QUERY_PROMPT = """\
You are an expert query expansion assistant for an enterprise policy retrieval system.

Given the user's question, generate exactly 3 alternative phrasings that:
  • Capture the same intent from different angles
  • Use different vocabulary (synonyms, formal vs. informal, more specific vs. broader)
  • Would help retrieve relevant policy chunks a keyword search might miss

Respond ONLY with a valid JSON array of 3 strings. No explanation. No markdown fences.

User question: {query}
"""


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(os.environ["NEON_DATABASE_URL"])


def _get_cohere_client() -> cohere.Client:
    return cohere.Client(os.environ["COHERE_API_KEY"])


def get_all_policy_ids() -> list[dict[str, Any]]:
    """
    Fetches a distinct list of all uploaded policy document IDs and their categories.
    Used for meta-queries like 'list all policies'.
    """
    try:
        with _get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # We extract the document_id and policy_category from the metadata JSONB
                cur.execute("""
                    SELECT DISTINCT 
                        document_id,
                        metadata->>'policy_category' as category
                    FROM policy_chunks
                    WHERE document_id IS NOT NULL
                    ORDER BY document_id;
                """)
                return cur.fetchall()
    except Exception as exc:
        logger.error("Failed to fetch policy list: %s", exc)
        return []


# ──────────────────────────────────────────────
# Stage 0 — Multi-Query Expansion (DeepSeek)
# ──────────────────────────────────────────────

def _expand_query(original_query: str) -> list[str]:
    """
    Use DeepSeek (via Ollama SDK) to generate 3 alternative phrasings
    of the user's query. Falls back to the original query if the LLM fails.
    """
    import ollama as ollama_sdk

    ollama_base = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com").rstrip("/")
    ollama_api_key = os.environ.get("OLLAMA_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "deepseek-v3.1:671b-cloud")

    prompt = OLLAMA_MULTI_QUERY_PROMPT.format(query=original_query)

    try:
        client = ollama_sdk.Client(
            host=ollama_base,
            headers={"Authorization": f"Bearer {ollama_api_key}"} if ollama_api_key else {},
        )
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )

        content = response["message"]["content"].strip()
        expanded: list[str] = json.loads(content)

        if not isinstance(expanded, list) or len(expanded) == 0:
            raise ValueError("LLM returned empty or non-list response.")

        # Always keep the original query as one of the variants
        all_queries = [original_query] + expanded[:3]
        logger.info(
            "Multi-Query expansion: original + %d variants → %d queries total.",
            len(expanded), len(all_queries),
        )
        return all_queries

    except Exception as exc:
        logger.warning(
            "Multi-Query expansion failed (%s). Falling back to original query only.", exc
        )
        return [original_query]


# ──────────────────────────────────────────────
# Stage 1 — Embed + HNSW Vector Search
# ──────────────────────────────────────────────

def _embed_queries(queries: list[str]) -> list[list[float]]:
    """
    Batch-embed all expanded queries using Cohere embed-english-v3.0 (1024-dim).
    Uses input_type='search_query' for optimal retrieval quality.
    """
    co = _get_cohere_client()
    response = co.embed(
        texts=queries,
        model=COHERE_EMBED_MODEL,
        input_type="search_query",
    )
    return response.embeddings


def _vector_search_single(
    query_embedding: list[float],
    top_k: int,
    filters: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    Run a single HNSW cosine similarity search against policy_chunks.
    Supports optional JSONB metadata filters.
    """
    where_clauses: list[str] = []
    params: list[Any] = []

    if filters:
        if cat := filters.get("policy_category"):
            where_clauses.append("metadata->>'policy_category' = %s")
            params.append(cat)
        if audience := filters.get("target_audience"):
            where_clauses.append("metadata->>'target_audience' = %s")
            params.append(audience)
        if date_gte := filters.get("effective_date_gte"):
            where_clauses.append("(metadata->>'effective_date')::date >= %s::date")
            params.append(date_gte)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    sql = f"""
        SELECT
            id::text,
            document_id,
            chunk_text,
            metadata,
            1 - (embedding <=> %s::vector) AS similarity
        FROM policy_chunks
        {where_sql}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    query_params = [query_embedding] + params + [query_embedding, top_k]

    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, query_params)
            rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _multi_query_vector_search(
    queries: list[str],
    filters: dict[str, Any] | None = None,
    k_per_query: int = CANDIDATE_K_PER_QUERY,
    max_candidates: int = FINAL_CANDIDATE_K,
) -> list[dict[str, Any]]:
    """
    Embed all expanded queries, run a separate HNSW search for each,
    then deduplicate by chunk id, keeping the highest similarity seen.
    Returns a list of up to *max_candidates* unique chunks.
    """
    embeddings = _embed_queries(queries)

    seen: dict[str, dict[str, Any]] = {}  # chunk_id → chunk dict

    for query, embedding in zip(queries, embeddings):
        results = _vector_search_single(embedding, top_k=k_per_query, filters=filters)
        for chunk in results:
            chunk_id = chunk["id"]
            # Keep the highest similarity score seen for this chunk across queries
            if chunk_id not in seen or chunk["similarity"] > seen[chunk_id]["similarity"]:
                seen[chunk_id] = chunk

    # Sort all unique candidates by best similarity, cap at max_candidates
    candidates = sorted(seen.values(), key=lambda c: c["similarity"], reverse=True)
    candidates = candidates[:max_candidates]

    logger.info(
        "Multi-Query search: %d expanded queries → %d unique candidate chunks.",
        len(queries), len(candidates),
    )
    return candidates


# ──────────────────────────────────────────────
# Stage 2 — Cohere ReRank (25 → 5)
# ──────────────────────────────────────────────

def _rerank(
    original_query: str,
    candidates: list[dict[str, Any]],
    top_n: int = FINAL_TOP_K,
) -> list[dict[str, Any]]:
    """
    Rerank the candidate pool using Cohere ReRank against the *original*
    user query (not the expanded variants). Prunes down to top_n chunks.

    Falls back to top-n by similarity if the Cohere API key is missing.
    """
    api_key = os.environ.get("COHERE_API_KEY", "")
    if not api_key:
        logger.warning(
            "COHERE_API_KEY not set — skipping rerank, returning top-%d by similarity.", top_n
        )
        return candidates[:top_n]

    co = _get_cohere_client()
    documents = [c["chunk_text"] for c in candidates]

    response = co.rerank(
        model=COHERE_RERANK_MODEL,
        query=original_query,
        documents=documents,
        top_n=top_n,
        return_documents=False,
    )

    reranked: list[dict[str, Any]] = []
    for result in response.results:
        chunk = dict(candidates[result.index])
        chunk["rerank_score"] = result.relevance_score
        reranked.append(chunk)

    logger.info(
        "Cohere ReRank: %d candidates → top %d returned.", len(candidates), len(reranked)
    )
    return reranked


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def retrieve_documents(
    user_query: str,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Full 3-stage advanced retrieval pipeline (per advanced-retrieval-skill):

      Stage 0 — Multi-Query Expansion:
                  DeepSeek generates 3 alternative query phrasings.

      Stage 1 — HNSW Vector Search (25-to-funnel):
                  Each expanded query is embedded and searched independently.
                  Results are deduplicated → top-25 unique candidate chunks.

      Stage 2 — Cohere ReRank (25→5):
                  Original query + 25 candidates → top 5 by relevance.

    Args:
        user_query: The raw user question.
        filters:    Optional JSONB metadata filters (policy_category,
                    target_audience, effective_date_gte).

    Returns:
        List of up to 5 chunk dicts, each containing:
          id, document_id, chunk_text, metadata, similarity, rerank_score.
    """
    logger.info("retrieve_documents called | query='%s'", user_query[:100])

    # ── Stage 0: Multi-Query Expansion ──────────────
    expanded_queries = _expand_query(user_query)

    # ── Stage 1: Multi-Query HNSW Search → 25 candidates ──
    candidates = _multi_query_vector_search(
        queries=expanded_queries,
        filters=filters,
        k_per_query=CANDIDATE_K_PER_QUERY,
        max_candidates=FINAL_CANDIDATE_K,
    )

    if not candidates:
        logger.warning("No candidates found for query: '%s'", user_query)
        return []

    # ── Stage 2: Cohere ReRank → top 5 ──────────────
    top_chunks = _rerank(
        original_query=user_query,
        candidates=candidates,
        top_n=FINAL_TOP_K,
    )

    return top_chunks
