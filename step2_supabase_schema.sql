-- =============================================================================
-- MCT PathAI — Multi-Student Schema
-- Project: MCT-Alesia (Supabase)
-- Run via: Supabase Dashboard → SQL Editor, or `supabase db push`
-- =============================================================================

-- ---------------------------------------------------------------------------
-- students — one row per student whose resume has been ingested
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS students (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT        NOT NULL,
    email            TEXT,
    filename         TEXT        NOT NULL UNIQUE,   -- original filename, dedup key
    resume_text      TEXT        NOT NULL,
    skills           JSONB       NOT NULL DEFAULT '[]',
    experience_years FLOAT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  students              IS 'Student profiles ingested from resume files';
COMMENT ON COLUMN students.filename     IS 'Source filename used as upsert key';
COMMENT ON COLUMN students.skills       IS 'Array of skill strings extracted from resume';

-- Auto-bump updated_at on every row update
CREATE OR REPLACE FUNCTION _set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS students_updated_at ON students;
CREATE TRIGGER students_updated_at
    BEFORE UPDATE ON students
    FOR EACH ROW EXECUTE FUNCTION _set_updated_at();

-- ---------------------------------------------------------------------------
-- student_job_scores — per-student per-job match scores
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS student_job_scores (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id     UUID        NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    job_id         TEXT        NOT NULL,    -- SHA-256 id from jobs.db
    fit_score      FLOAT       NOT NULL,    -- composite [0, 1]
    skill_score    FLOAT,                   -- Jaccard skill overlap [0, 1]
    semantic_score FLOAT,                   -- cosine similarity [0, 1]
    scored_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_student_job UNIQUE (student_id, job_id)
);

COMMENT ON TABLE  student_job_scores            IS 'Per-student job match scores from multi-scorer';
COMMENT ON COLUMN student_job_scores.fit_score  IS 'Final score: 0.4*skill + 0.6*semantic, range [0,1]';
COMMENT ON COLUMN student_job_scores.job_id     IS 'SHA-256 job id matching jobs.db primary key';

CREATE INDEX IF NOT EXISTS idx_sjs_student_id
    ON student_job_scores(student_id);

CREATE INDEX IF NOT EXISTS idx_sjs_job_id
    ON student_job_scores(job_id);

-- Composite index used by dashboard query: "top N jobs for student X"
CREATE INDEX IF NOT EXISTS idx_sjs_student_score
    ON student_job_scores(student_id, fit_score DESC);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE students           ENABLE ROW LEVEL SECURITY;
ALTER TABLE student_job_scores ENABLE ROW LEVEL SECURITY;

-- Service role (backend: step1, step3) — full access
CREATE POLICY IF NOT EXISTS "service_full_students"
    ON students FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY IF NOT EXISTS "service_full_scores"
    ON student_job_scores FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Anon / authenticated (dashboard) — read only
CREATE POLICY IF NOT EXISTS "anon_read_students"
    ON students FOR SELECT
    TO anon, authenticated
    USING (true);

CREATE POLICY IF NOT EXISTS "anon_read_scores"
    ON student_job_scores FOR SELECT
    TO anon, authenticated
    USING (true);

-- ---------------------------------------------------------------------------
-- Convenience view: top 200 scored jobs per student (used by dashboard)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW student_top_jobs AS
SELECT
    s.id             AS student_id,
    s.name           AS student_name,
    sjs.job_id,
    sjs.fit_score,
    sjs.skill_score,
    sjs.semantic_score,
    sjs.scored_at
FROM students s
JOIN student_job_scores sjs ON sjs.student_id = s.id
ORDER BY s.name, sjs.fit_score DESC;

COMMENT ON VIEW student_top_jobs IS 'Denormalised student+score view for dashboard queries';
