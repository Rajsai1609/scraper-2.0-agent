-- Job Application Tracker
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS job_applications (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id  UUID NOT NULL REFERENCES students(id)     ON DELETE CASCADE,
  job_id      UUID NOT NULL REFERENCES scraped_jobs(id) ON DELETE CASCADE,
  status      TEXT NOT NULL DEFAULT 'saved'
              CHECK (status IN ('saved','applied','interview','offer','rejected')),
  notes       TEXT,
  applied_at  TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (student_id, job_id)
);

ALTER TABLE job_applications ENABLE ROW LEVEL SECURITY;

-- Dashboard uses the anon key — allow full access
CREATE POLICY "anon_all" ON job_applications
  FOR ALL USING (true) WITH CHECK (true);

-- Index for fast per-student lookups
CREATE INDEX IF NOT EXISTS idx_job_apps_student ON job_applications (student_id);
