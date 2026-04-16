-- =============================================================================
-- MCT PathAI — scraped_jobs table
-- Run in: Supabase Dashboard → SQL Editor
-- Idempotent — safe to re-run.
-- =============================================================================

CREATE TABLE IF NOT EXISTS scraped_jobs (
    id                TEXT        PRIMARY KEY,          -- SHA-256(company+url)
    title             TEXT        NOT NULL,
    company           TEXT        NOT NULL,
    ats_platform      TEXT        NOT NULL,
    url               TEXT        NOT NULL,
    description       TEXT        DEFAULT '',
    location          TEXT        DEFAULT '',
    country           TEXT,
    work_mode         TEXT        DEFAULT 'unknown',
    usa_region        TEXT        DEFAULT '',
    is_usa_job        BOOLEAN     DEFAULT FALSE,
    experience_level  TEXT        DEFAULT 'unknown',
    years_min         INTEGER,
    years_max         INTEGER,
    is_entry_eligible BOOLEAN     DEFAULT FALSE,
    h1b_sponsor       BOOLEAN,
    opt_friendly      BOOLEAN,
    stem_opt_eligible BOOLEAN,
    visa_flag         BOOLEAN     DEFAULT FALSE,        -- TRUE when h1b_sponsor is explicitly FALSE
    visa_notes        TEXT        DEFAULT '',
    skills            JSONB       DEFAULT '[]',
    job_category      TEXT        DEFAULT 'other',
    scraper_score     FLOAT,                            -- fit_score from local scorer [0,1]
    date_posted       TIMESTAMPTZ,
    fetched_at        TIMESTAMPTZ NOT NULL,
    expires_at        TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE  scraped_jobs                IS 'Raw jobs written by scraper-2.0 after every run';
COMMENT ON COLUMN scraped_jobs.id             IS 'SHA-256(company|url) — stable dedup key';
COMMENT ON COLUMN scraped_jobs.visa_flag      IS 'TRUE when company is known NOT to sponsor visas';
COMMENT ON COLUMN scraped_jobs.scraper_score  IS 'Local resume fit score from scraper, range [0,1]';

-- Indexes used by the dashboard and student_top_jobs join
CREATE INDEX IF NOT EXISTS idx_sj_company      ON scraped_jobs(company);
CREATE INDEX IF NOT EXISTS idx_sj_job_category ON scraped_jobs(job_category);
CREATE INDEX IF NOT EXISTS idx_sj_work_mode    ON scraped_jobs(work_mode);
CREATE INDEX IF NOT EXISTS idx_sj_visa_flag    ON scraped_jobs(visa_flag);
CREATE INDEX IF NOT EXISTS idx_sj_fetched_at   ON scraped_jobs(fetched_at DESC);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE scraped_jobs ENABLE ROW LEVEL SECURITY;

-- Service role (scraper backend) — full access
CREATE POLICY IF NOT EXISTS "service_full_scraped_jobs"
    ON scraped_jobs FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Anon / authenticated (dashboard) — read only
CREATE POLICY IF NOT EXISTS "anon_read_scraped_jobs"
    ON scraped_jobs FOR SELECT
    TO anon, authenticated
    USING (true);
