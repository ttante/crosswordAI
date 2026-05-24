CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    failure_reason TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id),
    media_type TEXT NOT NULL,
    object_uri TEXT NOT NULL,
    content_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS source_packs (
    id TEXT PRIMARY KEY,
    theme TEXT NOT NULL,
    normalized_theme TEXT NOT NULL,
    taxonomy TEXT NOT NULL,
    taxonomy_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    taxonomy_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_score DOUBLE PRECISION NOT NULL,
    version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    artifact_id TEXT REFERENCES artifacts(id)
);

CREATE TABLE IF NOT EXISTS source_documents (
    id TEXT PRIMARY KEY,
    source_pack_id TEXT NOT NULL REFERENCES source_packs(id),
    source_type TEXT NOT NULL,
    url_or_path TEXT NOT NULL,
    title TEXT NOT NULL,
    author_or_provider TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    license_or_rights_status TEXT NOT NULL,
    trust_score DOUBLE PRECISION NOT NULL,
    content_hash TEXT NOT NULL,
    object_storage_uri TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_snippets (
    id TEXT PRIMARY KEY,
    source_document_id TEXT NOT NULL REFERENCES source_documents(id),
    snippet_text TEXT NOT NULL,
    start_locator INTEGER NOT NULL,
    end_locator INTEGER NOT NULL,
    snippet_hash TEXT NOT NULL,
    rights_risk TEXT NOT NULL,
    allowed_use TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_chunk_embeddings (
    id TEXT PRIMARY KEY,
    source_document_id TEXT REFERENCES source_documents(id),
    chunk_text TEXT NOT NULL,
    taxonomy TEXT,
    trust_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    rights_risk TEXT NOT NULL DEFAULT 'unknown',
    embedding_model_id TEXT NOT NULL DEFAULT 'unknown',
    embedding_model_version TEXT NOT NULL DEFAULT 'unknown',
    embedding_dimensions INTEGER NOT NULL DEFAULT 768,
    embedding vector(768),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_source_chunk_embeddings_hnsw
ON source_chunk_embeddings
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_source_chunk_embeddings_fts
ON source_chunk_embeddings
USING gin (to_tsvector('english', chunk_text));

CREATE TABLE IF NOT EXISTS retrieval_traces (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    embedding_model_id TEXT NOT NULL,
    embedding_model_version TEXT NOT NULL,
    embedding_dimensions INTEGER NOT NULL,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    results JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_entities (
    id TEXT PRIMARY KEY,
    source_pack_id TEXT NOT NULL REFERENCES source_packs(id),
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_evidence_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS graph_relationships (
    id TEXT PRIMARY KEY,
    source_pack_id TEXT NOT NULL REFERENCES source_packs(id),
    subject_id TEXT NOT NULL REFERENCES graph_entities(id),
    predicate TEXT NOT NULL,
    object_id TEXT NOT NULL REFERENCES graph_entities(id),
    source_evidence_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_graph_entities_source_pack
ON graph_entities (source_pack_id);

CREATE INDEX IF NOT EXISTS idx_graph_relationships_source_pack
ON graph_relationships (source_pack_id);

CREATE TABLE IF NOT EXISTS model_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id),
    task_type TEXT NOT NULL,
    model_id TEXT NOT NULL,
    route_id TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    latency_ms DOUBLE PRECISION NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    estimated_cost DOUBLE PRECISION NOT NULL,
    cache_hit BOOLEAN NOT NULL,
    retry_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_model_calls_run
ON model_calls (run_id);
