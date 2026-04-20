-- Step 9: Role Track Intelligence
-- Run in Supabase SQL Editor

ALTER TABLE students
ADD COLUMN IF NOT EXISTS role_track TEXT DEFAULT 'general';

ALTER TABLE waitlist
ADD COLUMN IF NOT EXISTS role_track TEXT;
