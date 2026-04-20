-- Migration: multi-track support
-- Run in Supabase SQL Editor

ALTER TABLE students ADD COLUMN IF NOT EXISTS role_tracks TEXT[] DEFAULT '{}';

-- Seed from existing single role_track (skip 'general' — it's the fallback, not a real track)
UPDATE students
SET role_tracks = ARRAY[role_track]
WHERE role_track IS NOT NULL
  AND role_track != 'general'
  AND (role_tracks IS NULL OR role_tracks = '{}');

ALTER TABLE waitlist ADD COLUMN IF NOT EXISTS role_tracks TEXT[];
