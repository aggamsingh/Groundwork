-- Chunk store and retrieval indexes — Phase 2 machinery (C-006).
--
-- Applied by scripts/init_db.py after the base schema.
--
-- Chunks are DERIVED data: they are rebuilt whenever chunking configuration
-- changes, which Phase 3 does eight times. Papers, sections and paragraphs are
-- the durable record; nothing here is a source of truth, and everything here can
-- be dropped and recomputed.

-- ---------------------------------------------------------------------------
-- One row per chunk, per chunking configuration.
--
-- `config_fingerprint` is what makes several chunkings coexist. Phase 3 compares
-- techniques, and comparing requires having both present at once — replacing
-- chunks in place would mean re-running the previous configuration to see its
-- numbers again, and the old rows are cheap to keep.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunks (
    id            bigserial PRIMARY KEY,
    paper_id      bigint NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    section_id    bigint REFERENCES sections(id) ON DELETE SET NULL,
    config_fingerprint text NOT NULL,
    strategy      text NOT NULL,
    ordinal       int NOT NULL,
    text          text NOT NULL,
    -- Prepended paper/section context (Phase 3 item 2) is stored separately so
    -- the augmentation can be measured without re-chunking, and so a citation
    -- never quotes text the paper does not contain.
    context_prefix text,
    char_count    int NOT NULL,
    UNIQUE (config_fingerprint, paper_id, ordinal)
);
CREATE INDEX IF NOT EXISTS chunks_paper_idx ON chunks (paper_id);
CREATE INDEX IF NOT EXISTS chunks_config_idx ON chunks (config_fingerprint);

-- ---------------------------------------------------------------------------
-- Where each chunk's text came from. A chunk may span several paragraphs, so
-- this is one row per contributing span rather than a column on `chunks`.
--
-- This table is what makes a retrieved chunk citable (D-003). Without it a
-- citation could only point at a chunk, and chunks move every time chunking
-- changes.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunk_spans (
    id           bigserial PRIMARY KEY,
    chunk_id     bigint NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    paragraph_id bigint NOT NULL REFERENCES paragraphs(id) ON DELETE CASCADE,
    char_start   int NOT NULL,
    char_end     int NOT NULL,
    CHECK (char_end >= char_start)
);
CREATE INDEX IF NOT EXISTS chunk_spans_chunk_idx ON chunk_spans (chunk_id);
CREATE INDEX IF NOT EXISTS chunk_spans_paragraph_idx ON chunk_spans (paragraph_id);

-- ---------------------------------------------------------------------------
-- Embeddings, one row per (chunk, embedding model).
--
-- The model is part of the key because spec section 4 requires benchmarking two
-- alternatives in Phase 3, and comparing them means holding both at once.
-- Dimensions vary by model, so the vector column is unconstrained here and the
-- index is created per model by scripts/build_index.py — pgvector requires a
-- fixed dimension on an indexed column.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id     bigint NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    model_name   text NOT NULL,
    dimensions   int NOT NULL,
    embedding    vector NOT NULL,
    PRIMARY KEY (chunk_id, model_name)
);

-- ---------------------------------------------------------------------------
-- Full-text search, for the BM25 side of hybrid retrieval.
--
-- Postgres FTS rather than a separate BM25 index, per spec section 4: it keeps
-- lexical and dense retrieval in one joinable store, and whether it is adequate
-- is a Phase 2 measurement rather than an assumption. `ts_rank_cd` is not BM25 —
-- it is a different lexical scoring function — so any report must say which was
-- used rather than calling it BM25 by habit.
--
-- The tsvector is generated, so it cannot drift from the text it indexes.
-- ---------------------------------------------------------------------------
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS text_search tsvector
    GENERATED ALWAYS AS (to_tsvector('english', text)) STORED;

CREATE INDEX IF NOT EXISTS chunks_fts_idx ON chunks USING GIN (text_search);

-- ---------------------------------------------------------------------------
-- Dev-set-only view over chunks, mirroring v_dev_papers (D-004).
--
-- Retrieval selects from here, never from `chunks` directly, so a holdout
-- paper's text cannot enter a result set through a forgotten join. The guard has
-- to exist at the chunk level too: by Phase 3 retrieval reads chunks, not
-- papers, and a view that only protects papers would protect nothing.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_dev_chunks AS
SELECT c.*
FROM chunks c
JOIN corpus_split s ON s.paper_id = c.paper_id
WHERE s.split = 'dev';

COMMENT ON VIEW v_dev_chunks IS
    'The only chunk set any pre-Phase-6 retrieval may read. See CLAUDE.md CHECKPOINT 1.';
