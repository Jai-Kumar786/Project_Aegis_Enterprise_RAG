-- =============================================================
-- Project Aegis — Neon PostgreSQL Schema
-- =============================================================
-- Run this once against your Neon database to create the
-- required extension, tables, and indexes.
--
-- Embedding dimensions: 1536 (compatible with pgvector HNSW,
-- which supports up to 2000 dimensions).
-- =============================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Drop existing table to fix dimension mismatch
DROP TABLE IF EXISTS policy_chunks;

-- 3. Policy chunks table
CREATE TABLE policy_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id VARCHAR(255)      NOT NULL,
    chunk_text  TEXT              NOT NULL,
    embedding   VECTOR(1024),                -- 1024-dim, HNSW-compatible
    metadata    JSONB             NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. HNSW vector index (works because 1024 < 2000-dim limit)
CREATE INDEX ON policy_chunks
    USING hnsw (embedding vector_cosine_ops);

-- 4. GIN index for fast JSONB metadata filtering
CREATE INDEX idx_policy_chunks_metadata
    ON policy_chunks USING GIN (metadata);

-- 5. B-Tree indexes for common scalar lookups
CREATE INDEX idx_policy_chunks_document_id
    ON policy_chunks (document_id);

CREATE INDEX idx_policy_chunks_created_at
    ON policy_chunks (created_at DESC);
