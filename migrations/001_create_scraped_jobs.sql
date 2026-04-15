-- =============================================================================
-- Migration 001: scraped_jobs table
-- Run via: python setup_supabase.py
--       OR: Supabase Dashboard -> SQL Editor -> paste and run
--
-- Purpose: stores job listings synced from the daily scraper's SQLite db.
--          id is TEXT (e.g. "greenhouse-12345", "ashby-uuid", "lever-uuid")
--          matching student_job_scores.job_id so the JOIN works.
-- =============================================================================

CREATE TABLE IF NOT EXISTS scraped_jobs (
    id                TEXT        PRIMARY KEY,   -- e.g. greenhouse-12345, ashby-uuid
    title             TEXT        NOT NULL DEFAULT '',
    company           TEXT        NOT NULL DEFAULT '',
    location          TEXT        NOT NULL DEFAULT '',
    url               TEXT        NOT NULL DEFAULT '',
    description       TEXT        NOT NULL DEFAULT '',
    work_mode         TEXT        NOT NULL DEFAULT 'unknown',
    usa_region        TEXT        NOT NULL DEFAULT '',
    is_usa_job        BOOLEAN     NOT NULL DEFAULT FALSE,
    experience_level  TEXT        NOT NULL DEFAULT 'unknown',
    is_entry_eligible BOOLEAN     NOT NULL DEFAULT FALSE,
    h1b_sponsor       BOOLEAN,
    opt_friendly      BOOLEAN,
    stem_opt_eligible BOOLEAN,
    skills            JSONB       NOT NULL DEFAULT '[]'::jsonb,
    job_category      TEXT        NOT NULL DEFAULT 'other',
    date_posted       TIMESTAMPTZ,
    fetched_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at        TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 days')
);

-- Indexes for common dashboard filters
CREATE INDEX IF NOT EXISTS idx_scraped_jobs_company
    ON scraped_jobs(company);
CREATE INDEX IF NOT EXISTS idx_scraped_jobs_work_mode
    ON scraped_jobs(work_mode);
CREATE INDEX IF NOT EXISTS idx_scraped_jobs_job_category
    ON scraped_jobs(job_category);
CREATE INDEX IF NOT EXISTS idx_scraped_jobs_expires_at
    ON scraped_jobs(expires_at);

-- Row Level Security: service role writes, anon/auth reads
ALTER TABLE scraped_jobs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'scraped_jobs' AND policyname = 'service_full_scraped_jobs'
    ) THEN
        CREATE POLICY service_full_scraped_jobs
            ON scraped_jobs FOR ALL TO service_role
            USING (true) WITH CHECK (true);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'scraped_jobs' AND policyname = 'anon_read_scraped_jobs'
    ) THEN
        CREATE POLICY anon_read_scraped_jobs
            ON scraped_jobs FOR SELECT TO anon, authenticated
            USING (true);
    END IF;
END $$;

-- =============================================================================
-- Rebuild student_top_jobs view to JOIN with scraped_jobs
-- =============================================================================

CREATE OR REPLACE VIEW student_top_jobs AS
SELECT
    s.id               AS student_id,
    s.name             AS student_name,
    sjs.job_id,
    sjs.fit_score,
    sjs.skill_score,
    sjs.semantic_score,
    sjs.scored_at,
    j.title,
    j.company,
    j.location,
    j.url,
    j.work_mode,
    j.usa_region,
    j.is_usa_job,
    j.experience_level,
    j.is_entry_eligible,
    j.h1b_sponsor,
    j.opt_friendly,
    j.stem_opt_eligible,
    j.skills,
    j.job_category,
    j.date_posted
FROM students s
JOIN  student_job_scores sjs ON sjs.student_id = s.id
LEFT JOIN scraped_jobs   j   ON j.id = sjs.job_id
ORDER BY s.name, sjs.fit_score DESC;

COMMENT ON VIEW student_top_jobs
    IS 'Student scores joined with scraped job details for the dashboard';
