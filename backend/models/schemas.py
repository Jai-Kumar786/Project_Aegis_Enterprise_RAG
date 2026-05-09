from __future__ import annotations

from datetime import date
from typing import Optional
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field


class PolicyMetadata(BaseModel):
    """
    Pydantic model representing metadata extracted from an enterprise policy document.
    Used as a data contract between the ingestion pipeline and the database layer.
    """

    document_id: str = Field(
        ...,
        description="Unique identifier for the source policy document.",
        examples=["POL-2024-HR-001"],
    )
    policy_category: str = Field(
        ...,
        description="High-level category the policy belongs to (e.g. 'HR', 'Security', 'Finance').",
        examples=["HR", "Security", "Finance"],
    )
    effective_date: date = Field(
        ...,
        description="The date from which this policy version is in effect (ISO 8601: YYYY-MM-DD).",
        examples=["2024-01-01"],
    )
    target_audience: str = Field(
        ...,
        description="The intended audience for this policy (e.g. 'All Employees', 'Engineering', 'Contractors').",
        examples=["All Employees", "Engineering"],
    )


class ChunkMetadata(PolicyMetadata):
    """
    Extends PolicyMetadata with chunk-level fields populated during ingestion.
    Each chunk stored in the vector database will carry this full metadata payload.
    """

    chunk_index: int = Field(
        ...,
        description="Zero-based index of this chunk within its source document.",
    )
    section_header: Optional[str] = Field(
        default=None,
        description="The Markdown header(s) that scope this chunk, joined with ' > '.",
        examples=["HR Policies > Leave Policy > Sick Leave"],
    )
    token_count: Optional[int] = Field(
        default=None,
        description="Approximate token count of the chunk content.",
    )


class HistoryMessage(BaseModel):
    """A single turn in the conversation history."""
    role: str = Field(..., description="Either 'user' or 'assistant'.")
    content: str = Field(..., description="The message content.")


class ChatRequest(BaseModel):
    """
    Payload for the POST /chat endpoint.
    The data contract between the Next.js frontend and the RAG API.
    """

    message: str = Field(
        ...,
        min_length=3,
        description="The user's natural language question.",
        examples=["What is the remote work policy?"],
    )
    history: list[HistoryMessage] = Field(
        default_factory=list,
        description="Previous turns in the conversation (oldest first). Used to give DeepSeek memory of the current session.",
    )
    policy_category: Optional[str] = Field(
        default=None,
        description="Optional filter: restrict retrieval to a specific policy category.",
    )
    target_audience: Optional[str] = Field(
        default=None,
        description="Optional filter: restrict retrieval to a specific audience.",
    )
    effective_date_gte: Optional[str] = Field(
        default=None,
        description="Optional filter: only consider policies effective on or after this date (YYYY-MM-DD).",
    )


class ChatResponse(BaseModel):
    """
    Response shape for POST /chat.
    Contains the LLM-generated answer and the list of source document IDs cited.
    """

    answer: str = Field(
        ...,
        description="The grounded LLM answer with inline citations like [1], [2].",
    )
    cited_document_ids: list[str] = Field(
        ...,
        description="Ordered list of document_ids that were used as context. Index 0 = [1].",
    )
    chunks_used: int = Field(
        ...,
        description="Number of chunks passed to the LLM for synthesis.",
    )
