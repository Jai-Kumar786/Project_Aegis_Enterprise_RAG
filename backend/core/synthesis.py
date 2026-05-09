"""
backend/core/synthesis.py

Synthesis layer for Project Aegis (per advanced-retrieval-skill Rule 4).

Receives the top-5 reranked chunks from the retrieval pipeline and instructs
DeepSeek (via Ollama Cloud) to produce a grounded, citation-annotated answer.

Citation format enforced:
  - Inline: [1], [2], …  mapped to chunk document_ids.
  - No hallucination: the LLM is explicitly told to answer ONLY from the
    provided context, and to say "I don't have enough information" if the
    context is insufficient.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import json
# pyrefly: ignore [missing-import]
import ollama as ollama_sdk

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Prompt Templates
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are Project Aegis, a secure and authoritative enterprise policy assistant.
Your SOLE purpose is to answer employee questions about company policies using
ONLY the document excerpts provided in the context below.

CRITICAL RULES — you must follow every one of these without exception:

1. ONLY USE THE CONTEXT. Never use outside knowledge, general world knowledge,
   or anything not explicitly written in the provided policy excerpts.

2. IF THE ANSWER IS NOT IN THE CONTEXT, respond with exactly:
   "I'm sorry, but I don't have enough information in the current policy documents to answer this question. Please contact HR or your manager for clarification."
   Do NOT attempt to guess, infer, or extrapolate.

3. REFUSE OFF-TOPIC REQUESTS. If the user asks you to write creative content
   (poems, stories, code, jokes), discuss topics unrelated to company policy,
   or act as a general-purpose AI, respond with:
   "I'm a policy assistant for Project Aegis and can only answer questions about company policies. I'm not able to help with that request."

4. CITE EVERY CLAIM. Every factual statement must end with an inline citation
   like [1], [2], etc., mapped to the Source numbers in the context.

5. DO NOT FABRICATE. Never invent document names, dates, dollar amounts,
   percentages, policy rules, or people.

6. STAY PROFESSIONAL. Be clear, concise, and formal at all times.
"""

# Minimum Cohere rerank score for a chunk to be considered relevant.
# Queries that return no chunks above this threshold are rejected before
# hitting the LLM — preventing hallucination on truly off-topic questions.
RERANK_RELEVANCE_THRESHOLD = 0.10

CONTEXT_TEMPLATE = """\
--- Source [{index}] | Document: {document_id} | Category: {policy_category} | Section: {section} ---
{chunk_text}
"""

USER_PROMPT_TEMPLATE = """\
Context (use ONLY these sources to answer):
{context_block}

Employee question: {question}

Answer (with inline citations like [1], [2]):"""



# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

import json

async def generate_answer_stream(
    user_query: str,
    top_chunks: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
):
    """
    Generate a grounded answer using DeepSeek (via Ollama Cloud) and stream tokens.

    Yields SSE formatted strings containing either metadata or text chunks:
      {"type": "metadata", "citations": [...], "chunks_used": N}
      {"type": "chunk", "text": "..."}
    """
    if not top_chunks:
        yield f"data: {json.dumps({'type': 'metadata', 'citations': [], 'chunks_used': 0})}\n\n"
        msg = "I'm sorry, but I don't have enough information in the current policy documents to answer this question. Please contact HR or your manager for clarification."
        yield f"data: {json.dumps({'type': 'chunk', 'text': msg})}\n\n"
        return

    # ── Relevance gate: reject off-topic queries before hitting the LLM ─
    top_score = top_chunks[0].get("rerank_score") or 0.0
    if top_score < RERANK_RELEVANCE_THRESHOLD:
        logger.warning(
            "Query rejected by relevance gate (top rerank_score=%.4f < %.4f): '%s'",
            top_score, RERANK_RELEVANCE_THRESHOLD, user_query,
        )
        yield f"data: {json.dumps({'type': 'metadata', 'citations': [], 'chunks_used': 0})}\n\n"
        msg = "I'm a policy assistant for Project Aegis and can only answer questions about company policies. I don't have any relevant policy information for your request."
        yield f"data: {json.dumps({'type': 'chunk', 'text': msg})}\n\n"
        return

    # ── Build the numbered context block ────────────────────────────
    context_parts: list[str] = []
    cited_ids: list[str] = []

    for i, chunk in enumerate(top_chunks, start=1):
        meta = chunk.get("metadata", {})
        if isinstance(meta, str):
            meta = json.loads(meta)

        doc_id     = chunk.get("document_id", "unknown")
        category   = meta.get("policy_category", "N/A")
        section    = meta.get("section_header", "General")

        context_parts.append(CONTEXT_TEMPLATE.format(
            index=i,
            document_id=doc_id,
            policy_category=category,
            section=section or "General",
            chunk_text=chunk.get("chunk_text", ""),
        ))
        cited_ids.append(doc_id)

    context_block = "\n".join(context_parts)
    user_prompt   = USER_PROMPT_TEMPLATE.format(
        context_block=context_block,
        question=user_query,
    )

    # ── Call DeepSeek via Ollama SDK with Streaming ──────────────────
    ollama_base = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com").rstrip("/")
    ollama_key  = os.environ.get("OLLAMA_API_KEY", "")
    model       = os.environ.get("LLM_MODEL", "deepseek-v3.1:671b-cloud")

    # ── Build messages: system → history → current user turn ──────────
    history_messages = [
        {"role": h["role"], "content": h["content"]}
        for h in (history or [])
        # Only pass completed turns (skip empty streaming placeholders)
        if h.get("content") and h.get("role") in ("user", "assistant")
    ]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history_messages,
        {"role": "user",   "content": user_prompt},
    ]

    # First, yield the metadata so the frontend knows what was cited
    yield f"data: {json.dumps({'type': 'metadata', 'citations': cited_ids, 'chunks_used': len(top_chunks)})}\n\n"

    try:
        async_client = ollama_sdk.AsyncClient(
            host=ollama_base,
            headers={"Authorization": f"Bearer {ollama_key}"} if ollama_key else {},
        )

        async for chunk in await async_client.chat(
            model=model,
            messages=messages,
            stream=True,
        ):
            content = chunk["message"]["content"]
            if content:
                yield f"data: {json.dumps({'type':'chunk','text':content})}\n\n"

        logger.info("DeepSeek streaming synthesis complete.")

    except Exception as exc:
        logger.error("DeepSeek synthesis stream failed: %s", exc)
        yield json.dumps({"type": "chunk", "text": "\n\n*[Error: Synthesis connection dropped]*"}) + "\n"
