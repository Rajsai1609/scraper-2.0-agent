-- H1B Employers table + scraped_jobs visa columns
-- Run once via Supabase SQL editor or psql

CREATE TABLE IF NOT EXISTS h1b_employers (
    id            UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    employer_name TEXT        UNIQUE NOT NULL,
    h1b_count     INTEGER     DEFAULT 0,
    avg_salary    FLOAT       DEFAULT 0,
    approval_rate FLOAT       DEFAULT 0,
    visa_score    INTEGER     DEFAULT 0,
    job_titles    TEXT        DEFAULT '[]',
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_h1b_employer_name ON h1b_employers (employer_name);
CREATE INDEX IF NOT EXISTS idx_h1b_visa_score    ON h1b_employers (visa_score DESC);

ALTER TABLE h1b_employers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_read_h1b_employers"
    ON h1b_employers FOR SELECT
    TO anon, authenticated
    USING (true);

-- Add visa columns to scraped_jobs (idempotent)
ALTER TABLE scraped_jobs ADD COLUMN IF NOT EXISTS visa_score INTEGER DEFAULT 0;
ALTER TABLE scraped_jobs ADD COLUMN IF NOT EXISTS h1b_count  INTEGER DEFAULT 0;
