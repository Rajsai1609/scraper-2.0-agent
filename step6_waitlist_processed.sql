-- =============================================================================
-- MCT PathAI — waitlist processing tracking columns
-- Run in: Supabase Dashboard → SQL Editor
-- Idempotent — safe to re-run.
-- =============================================================================

ALTER TABLE waitlist
    ADD COLUMN IF NOT EXISTS processed    BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;

-- Index so the auto-ingest script can quickly find pending rows
CREATE INDEX IF NOT EXISTS idx_waitlist_pending
    ON waitlist(processed)
    WHERE processed = FALSE;
