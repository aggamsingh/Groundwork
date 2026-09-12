-- Survey Assistant — corpus store schema (Phase 0)
--
-- Structure only. No chunking decisions are baked in here: paragraphs are stored
-- as the parser found them, and chunking is a Phase 3 concern that reads from
-- these tables rather than reshaping them (spec §5, Phase 1).
--
-- Spans are (paragraph_id, char_start, char_end) into paragraphs.text. See D-003.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Corpora — each corpus is isolated: own papers, schema, adapter, eval set.
-- ---------------------------------------------------------------------------
CREATE TABLE corpora (
    id          text PRIMARY KEY,              -- 'semcom'
    created_at  timestamptz NOT NULL DEFAULT now(),
    notes       text
);

-- ---------------------------------------------------------------------------
-- Papers
-- ---------------------------------------------------------------------------
CREATE TABLE papers (
    id            bigserial PRIMARY KEY,
    corpus_id     text NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
    -- Stable external identifier chosen by the user (arXiv id / DOI / slug).
    -- This is the key eval/holdout_papers.txt refers to.
    external_id   text NOT NULL,
    title         text,
    abstract      text,
    year          int,
    venue         text,
    page_count    int,
    -- Resolved identifiers live in their own columns; external_id stays the
    -- slug, because eval labels key off it and re-keying after CHECKPOINT 4
    -- would invalidate them (D-005).
    doi           text,
    arxiv_id      text,
    source_path   text,                        -- path under corpus/, not committed
    sha256        text,                        -- content hash; idempotent re-ingest
    parser        text,                        -- which parser produced this (Phase 1 bake-off)
    parsed_at     timestamptz,
    ingest_status text NOT NULL DEFAULT 'pending'
        CHECK (ingest_status IN ('pending','ok','quarantined')),
    failure_reason text,
    UNIQUE (corpus_id, external_id)
);

-- ---------------------------------------------------------------------------
-- Holdout enforcement (CHECKPOINT 1 / D-002).
--
-- The split is authored by the user in eval/holdout_papers.txt and loaded here.
-- It is NOT generated. 'holdout' rows must not be read, ingested into the dev
-- index, or tuned against before Phase 6.
--
-- The mechanical guard has two halves:
--   1. v_dev_papers below — every retrieval and eval path selects from this view,
--      never from papers directly, so holdout rows cannot leak in by omission.
--   2. The CI check in task 0.6b, which fails any eval run whose retrieved paper
--      ids intersect the holdout list.
-- ---------------------------------------------------------------------------
CREATE TABLE corpus_split (
    paper_id    bigint PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
    split       text NOT NULL CHECK (split IN ('dev','holdout')),
    frozen_at   timestamptz NOT NULL DEFAULT now(),
    source_file text NOT NULL                  -- provenance: 'eval/holdout_papers.txt'
);

CREATE VIEW v_dev_papers AS
SELECT p.*
FROM papers p
JOIN corpus_split s ON s.paper_id = p.id
WHERE s.split = 'dev';

COMMENT ON VIEW v_dev_papers IS
    'The only paper set any pre-Phase-6 retrieval or eval path may read. See CLAUDE.md CHECKPOINT 1.';

-- ---------------------------------------------------------------------------
-- Document structure: sections form a tree; paragraphs hang off sections.
-- ---------------------------------------------------------------------------
CREATE TABLE sections (
    id         bigserial PRIMARY KEY,
    paper_id   bigint NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    parent_id  bigint REFERENCES sections(id) ON DELETE CASCADE,
    ordinal    int NOT NULL,                   -- order among siblings
    depth      int NOT NULL,
    heading    text,
    kind       text                            -- 'abstract','body','references',...
);
CREATE INDEX ON sections (paper_id);
CREATE INDEX ON sections (parent_id);

CREATE TABLE paragraphs (
    id         bigserial PRIMARY KEY,
    paper_id   bigint NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    section_id bigint REFERENCES sections(id) ON DELETE CASCADE,
    ordinal    int NOT NULL,
    text       text NOT NULL,
    -- Where this text sits in the source PDF, for the Phase 7 clickable citation.
    page_from  int,
    page_to    int
);
CREATE INDEX ON paragraphs (paper_id);
CREATE INDEX ON paragraphs (section_id);

-- ---------------------------------------------------------------------------
-- Tables preserved as tables (Phase 1 exit criterion), not flattened to prose.
-- Header hierarchy is kept in `grid` so column-to-condition mapping survives.
-- The NL description is indexed separately from the serialized table (Phase 3.6).
-- ---------------------------------------------------------------------------
CREATE TABLE paper_tables (
    id          bigserial PRIMARY KEY,
    paper_id    bigint NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    section_id  bigint REFERENCES sections(id) ON DELETE SET NULL,
    ordinal     int NOT NULL,
    label       text,                          -- 'Table 2'
    caption     text,
    grid        jsonb NOT NULL,                -- rows/cells + multi-row header structure
    page        int
);
CREATE INDEX ON paper_tables (paper_id);

-- ---------------------------------------------------------------------------
-- Citation graph. Targets may be unresolved (cited work outside the corpus).
-- ---------------------------------------------------------------------------
CREATE TABLE citation_edges (
    id             bigserial PRIMARY KEY,
    src_paper_id   bigint NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    dst_paper_id   bigint REFERENCES papers(id) ON DELETE CASCADE,  -- NULL = outside corpus
    raw_reference  text,                       -- the reference string as parsed
    dst_external_id text,                      -- resolved id when known
    context_paragraph_id bigint REFERENCES paragraphs(id) ON DELETE SET NULL
);
CREATE INDEX ON citation_edges (src_paper_id);
CREATE INDEX ON citation_edges (dst_paper_id);
