"""
backend/api/routes.py

FastAPI application and route definitions for Project Aegis.

Endpoints:
  POST /ingest      — Ingest a Markdown policy document into the vector DB.
  POST /retrieve    — Hybrid retrieval: dense search + Cohere ReRank.
  GET  /health      — Liveness probe.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

import psycopg2
from datetime import date
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.ingestion import ingest_document
from backend.core.retrieval import retrieve_documents, get_all_policy_ids
from backend.core.synthesis import generate_answer_stream
from backend.models.schemas import PolicyMetadata, ChatRequest, ChatResponse

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ──────────────────────────────────────────────

# Load .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify DB connectivity on startup."""
    logger.info("Project Aegis API starting up…")
    try:
        conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
        conn.close()
        logger.info("Database connection verified ✓")
    except Exception as exc:
        logger.error("Database connection failed: %s", exc)
        raise RuntimeError("Cannot connect to Neon database.") from exc
    yield
    logger.info("Project Aegis API shutting down.")


# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────

app = FastAPI(
    title="Project Aegis — Enterprise RAG API",
    description="Advanced RAG system for corporate policy retrieval.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the Next.js frontend origin
_allowed_origins = [
    o.strip()
    for o in os.environ.get("FRONTEND_URL", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Request / Response Schemas
# ──────────────────────────────────────────────

class IngestRequest(BaseModel):
    """Payload for the /ingest endpoint."""

    markdown_text: str = Field(
        ...,
        description="Full Markdown content of the policy document.",
        min_length=10,
    )
    document_id: str = Field(
        ...,
        description="Unique identifier for this document (e.g. 'POL-2024-HR-001').",
    )
    policy_category: str = Field(
        ...,
        description="High-level category (e.g. 'HR', 'Security', 'Finance').",
    )
    effective_date: date = Field(
        ...,
        description="The date this policy version takes effect (YYYY-MM-DD).",
    )
    target_audience: str = Field(
        ...,
        description="Intended audience (e.g. 'All Employees', 'Engineering').",
    )
    batch_size: int = Field(
        default=32,
        ge=1,
        le=128,
        description="Number of chunks to embed per Hugging Face API call.",
    )


class IngestResponse(BaseModel):
    document_id: str
    chunks_ingested: int
    message: str


class RetrieveRequest(BaseModel):
    """Payload for the /retrieve endpoint."""

    query: str = Field(..., description="The user's natural language question.", min_length=3)
    policy_category: str | None = Field(
        default=None,
        description="Optional filter: restrict results to a specific policy category.",
    )
    target_audience: str | None = Field(
        default=None,
        description="Optional filter: restrict results to a specific audience.",
    )
    effective_date_gte: str | None = Field(
        default=None,
        description="Optional filter: only return policies effective on or after this date (YYYY-MM-DD).",
    )
    candidate_k: int = Field(
        default=20, ge=5, le=100,
        description="Candidate pool size for vector search before reranking.",
    )
    final_top_k: int = Field(
        default=5, ge=1, le=20,
        description="Number of chunks to return after Cohere reranking.",
    )


class ChunkResult(BaseModel):
    document_id: str
    policy_category: str
    effective_date: str
    target_audience: str
    chunk_index: int
    section_header: str | None
    content: str
    similarity: float | None = None
    rerank_score: float | None = None


class RetrieveResponse(BaseModel):
    query: str
    results: list[ChunkResult]


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.get("/health", tags=["Infrastructure"])
async def health_check() -> dict[str, str]:
    """Liveness probe — returns 200 OK if the API is running."""
    return {"status": "ok", "service": "project-aegis"}


@app.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Ingestion"],
    summary="Ingest a policy document",
)
async def ingest(payload: IngestRequest) -> IngestResponse:
    """
    Split, embed, and persist a Markdown policy document.

    - Chunks are created using `MarkdownHeaderTextSplitter`.
    - Embeddings are generated by the Qwen 3 model (4096 dims) via Hugging Face.
    - Chunks are stored in the `policy_chunks` table in Neon (pgvector).
    """
    metadata = PolicyMetadata(
        document_id=payload.document_id,
        policy_category=payload.policy_category,
        effective_date=payload.effective_date,
        target_audience=payload.target_audience,
    )

    try:
        count = ingest_document(
            markdown_text=payload.markdown_text,
            metadata=metadata,
            batch_size=payload.batch_size,
        )
    except Exception as exc:
        logger.exception("Ingestion failed for document '%s'", payload.document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        ) from exc

    return IngestResponse(
        document_id=payload.document_id,
        chunks_ingested=count,
        message=f"Successfully ingested {count} chunks.",
    )


@app.post(
    "/retrieve",
    response_model=RetrieveResponse,
    tags=["Retrieval"],
    summary="Hybrid retrieval with reranking",
)
async def retrieve_chunks(payload: RetrieveRequest) -> RetrieveResponse:
    """
    Perform hybrid retrieval for a natural language query.

    Pipeline:
      1. Embed query with Qwen 3 (Hugging Face).
      2. Dense cosine search against `policy_chunks` (IVFFlat, pgvector).
      3. Rerank the candidate pool with Cohere ReRank.

    Returns the top-*final_top_k* chunks with metadata.
    """
    filters: dict[str, Any] = {}
    if payload.policy_category:
        filters["policy_category"] = payload.policy_category
    if payload.target_audience:
        filters["target_audience"] = payload.target_audience
    if payload.effective_date_gte:
        filters["effective_date_gte"] = payload.effective_date_gte

    try:
        chunks = retrieve_documents(
            user_query=payload.query,
            filters=filters or None,
        )
    except Exception as exc:
        logger.exception("Retrieval failed for query: '%s'", payload.query)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval failed: {exc}",
        ) from exc

    results = [
        ChunkResult(
            document_id=c["document_id"],
            policy_category=c["metadata"].get("policy_category", ""),
            effective_date=c["metadata"].get("effective_date", ""),
            target_audience=c["metadata"].get("target_audience", ""),
            chunk_index=c["metadata"].get("chunk_index", 0),
            section_header=c["metadata"].get("section_header"),
            content=c["chunk_text"],
            similarity=c.get("similarity"),
            rerank_score=c.get("rerank_score"),
        )
        for c in chunks
    ]

    return RetrieveResponse(query=payload.query, results=results)


# ──────────────────────────────────────────────
# POST /chat — Full RAG Pipeline
# ──────────────────────────────────────────────

class ChatRequestBody(BaseModel):
    """Re-export of ChatRequest for OpenAPI docs clarity."""
    message: str = Field(..., min_length=3, description="The user's question.")
    policy_category: str | None = None
    target_audience: str | None = None
    effective_date_gte: str | None = None


@app.post(
    "/chat",
    tags=["Chat"],
    summary="Ask a question — Streaming RAG pipeline",
)
async def chat(payload: ChatRequest):
    """
    Full end-to-end RAG pipeline with Server-Sent Events (SSE) streaming:

      1. **Multi-Query Expansion** — DeepSeek generates 3 alternative phrasings.
      2. **Vector Search (HNSW)** — Each variant queries policy_chunks; top-25
         unique candidates are collected.
      3. **Cohere ReRank** — 25 candidates pruned to top-5.
      4. **Streaming Synthesis** — DeepSeek yields tokens in real-time.

    Returns a `text/event-stream` response.
    """
    filters: dict[str, Any] = {}
    if payload.policy_category:
        filters["policy_category"] = payload.policy_category
    if payload.target_audience:
        filters["target_audience"] = payload.target_audience
    if payload.effective_date_gte:
        filters["effective_date_gte"] = payload.effective_date_gte

    # ── Meta-Query Interception ───────────────────────────────────────
    # If the user is just asking "what policies do you have?", don't use
    # vector search. Query the DB directly for document IDs.
    meta_intents = ["all policies", "list policies", "what policies", "list all", "list the policies", "show me all"]
    query_lower = payload.message.lower()
    
    if any(intent in query_lower for intent in meta_intents):
        async def meta_query_stream():
            import json
            yield f"data: {json.dumps({'type': 'metadata', 'citations': [], 'chunks_used': 0})}\n\n"
            
            policies = get_all_policy_ids()
            if not policies:
                yield f"data: {json.dumps({'type': 'chunk', 'text': 'I currently do not have any policies in my database. Please upload some documents first.'})}\n\n"
                return
                
            intro = "Here are the policy documents currently available in my database:\n\n"
            yield f"data: {json.dumps({'type': 'chunk', 'text': intro})}\n\n"
            
            for p in policies:
                doc_id = p.get('document_id', 'Unknown')
                cat = p.get('category', 'General')
                bullet = f"- **{doc_id}** (Category: {cat})\n"
                yield f"data: {json.dumps({'type': 'chunk', 'text': bullet})}\n\n"
                
        return StreamingResponse(
            meta_query_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    try:
        # Contextualize the search query by appending the previous user question
        # This prevents the relevance gate from rejecting short follow-up questions
        search_query = payload.message
        if payload.history:
            last_user_msgs = [h for h in payload.history if h.role == "user"]
            if last_user_msgs:
                last_msg = last_user_msgs[-1].content
                search_query = f"{last_msg} - {payload.message}"

        top_chunks = retrieve_documents(
            user_query=search_query,
            filters=filters or None,
        )
    except Exception as exc:
        logger.exception("Retrieval failed for message: '%s'", payload.message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval pipeline failed: {exc}",
        ) from exc

    return StreamingResponse(
        generate_answer_stream(
            user_query=payload.message,
            top_chunks=top_chunks,
            history=[h.model_dump() for h in payload.history],
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}


def _extract_text(filename: str, content: bytes) -> str:
    """Extract plain text from uploaded file bytes based on extension."""
    ext = os.path.splitext(filename)[1].lower()

    if ext in (".md", ".txt"):
        return content.decode("utf-8")

    if ext == ".pdf":
        import io
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
        except ImportError:
            # Fallback to PyPDF2 if pypdf not available
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(content))

        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages).strip()
        if not text:
            raise ValueError("Could not extract any text from the PDF. It may be scanned/image-based.")
        return text

    raise ValueError(f"Unsupported file type: {ext}")


@app.post("/upload", tags=["Ingestion"], summary="Upload a policy document")
async def upload_document(
    file: UploadFile = File(...),
    x_upload_passcode: str | None = Header(default=None, alias="X-Upload-Passcode"),
):
    """
    Accepts .md, .txt, or .pdf file uploads and passes extracted text
    to the ingestion pipeline. Requires a valid X-Upload-Passcode header.
    """
    # ── Passcode gate ─────────────────────────────────────────────────
    expected = os.environ.get("UPLOAD_PASSCODE", "")
    if not expected:
        logger.warning("UPLOAD_PASSCODE is not set — upload endpoint is unprotected!")
    elif x_upload_passcode != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing passcode. Access denied.",
        )

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    try:
        content = await file.read()
        text = _extract_text(file.filename, content)

        doc_id = os.path.splitext(file.filename)[0]
        metadata = PolicyMetadata(
            document_id=doc_id,
            policy_category="General",
            effective_date=date.today().isoformat(),
            target_audience="All Employees"
        )

        chunks_inserted = ingest_document(text, metadata)
        return {
            "success": True,
            "message": f"Successfully ingested '{file.filename}' → {chunks_inserted} chunks."
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to ingest uploaded document.")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")


# ──────────────────────────────────────────────
# GET /documents — List all policy documents
# ──────────────────────────────────────────────

@app.get("/documents", tags=["Management"], summary="List all ingested policy documents")
async def list_documents():
    """
    Returns a distinct list of all document_ids and their categories
    currently stored in the policy_chunks table.
    """
    policies = get_all_policy_ids()
    return {"documents": [dict(p) for p in policies]}


# ──────────────────────────────────────────────
# DELETE /documents/{document_id} — Remove a policy
# ──────────────────────────────────────────────

@app.delete(
    "/documents/{document_id}",
    tags=["Management"],
    summary="Delete all chunks for a policy document",
)
async def delete_document(
    document_id: str,
    x_upload_passcode: str | None = Header(default=None, alias="X-Upload-Passcode"),
):
    """
    Deletes ALL chunks in policy_chunks that belong to the given document_id.
    Requires the same X-Upload-Passcode header as the upload endpoint.
    """
    # ── Passcode gate (same as upload) ────────────────────────────────
    expected = os.environ.get("UPLOAD_PASSCODE", "")
    if not expected:
        logger.warning("UPLOAD_PASSCODE is not set — delete endpoint is unprotected!")
    elif x_upload_passcode != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing passcode. Access denied.",
        )

    try:
        import psycopg2
        conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM policy_chunks WHERE document_id = %s",
                    (document_id,),
                )
                deleted_rows = cur.rowcount
            conn.commit()
        finally:
            conn.close()

        if deleted_rows == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No document found with id '{document_id}'.",
            )

        logger.info("Deleted %d chunks for document '%s'.", deleted_rows, document_id)
        return {
            "success": True,
            "message": f"Deleted '{document_id}' ({deleted_rows} chunks removed).",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete document '%s'.", document_id)
        raise HTTPException(status_code=500, detail=f"Deletion failed: {exc}")
