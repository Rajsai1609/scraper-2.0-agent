#!/usr/bin/env python3
"""
Sync jobs from local SQLite (data/jobs.db) to Supabase scraped_jobs table.

Run AFTER the scraper step and BEFORE the multi-student scorer so that
student_job_scores JOIN scraped_jobs returns full job details on the dashboard.

NOTE: Supabase already has a 'jobs' table owned by ai-carrer-ops (UUID ids).
This script targets 'scraped_jobs' (TEXT SHA-256 ids) to avoid conflicts.
The student_top_jobs view joins student_job_scores.job_id -> scraped_jobs.id.

Env vars required:
    SUPABASE_URL
    SUPABASE_SERVICE_KEY

Optional:
    SQLITE_PATH   (default: data/jobs.db)
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", "data/jobs.db"))

_BATCH_SIZE = 500          # rows per upsert call (well under Supabase 1 MB limit)
_BATCH_DELAY = 0.3         # seconds between batches to avoid rate limits


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

def load_jobs_from_sqlite() -> list[dict[str, Any]]:
    """Return all rows from the SQLite jobs table as plain dicts."""
    if not SQLITE_PATH.exists():
        raise FileNotFoundError(
            f"SQLite database not found: {SQLITE_PATH}\n"
            "Run the scraper first: python -m src.cli scrape"
        )

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE is_usa_job = 1
               OR usa_region != ''
               OR location LIKE '%USA%'
               OR location LIKE '%United States%'
               OR location LIKE '%, CA%'
               OR location LIKE '%, NY%'
               OR location LIKE '%, WA%'
               OR location LIKE '%, TX%'
               OR location LIKE '%, MA%'
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _coerce_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a raw SQLite row into a Supabase-compatible dict.

    - INTEGER booleans -> Python bool (Supabase BOOLEAN)
    - skills JSON string -> parsed list (Supabase JSONB)
    - ISO datetime strings kept as-is (Postgres accepts them)
    """
    def _opt_bool(v: Any) -> bool | None:
        return None if v is None else bool(v)

    skills_raw = row.get("skills") or "[]"
    try:
        skills = json.loads(skills_raw) if isinstance(skills_raw, str) else skills_raw
        if not isinstance(skills, list):
            skills = []
    except Exception:
        skills = []

    return {
        "id":                row["id"],
        "title":             row["title"] or "",
        "company":           row["company"] or "",
        "location":          row.get("location") or "",
        "url":               row["url"] or "",
        "work_mode":         row.get("work_mode") or "unknown",
        "usa_region":        row.get("usa_region") or "",
        "is_usa_job":        bool(row.get("is_usa_job") or 0),
        "experience_level":  row.get("experience_level") or "unknown",
        "is_entry_eligible": bool(row.get("is_entry_eligible") or 0),
        "h1b_sponsor":       _opt_bool(row.get("h1b_sponsor")),
        "opt_friendly":      _opt_bool(row.get("opt_friendly")),
        "stem_opt_eligible": _opt_bool(row.get("stem_opt_eligible")),
        "skills":            skills,
        "job_category":      row.get("job_category") or "other",
        "date_posted":       row.get("date_posted") or None,
        "fetched_at":        row.get("fetched_at") or None,
        "expires_at":        row.get("expires_at") or None,
    }


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------

def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.\n"
            "Add them to .env or pass them as environment variables."
        )
    try:
        from supabase import create_client  # type: ignore[import]
    except ImportError:
        raise ImportError("supabase not installed — run: pip install supabase")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upsert_batch(client, rows: list[dict[str, Any]]) -> int:
    """Upsert a batch of job rows; returns the count of rows upserted."""
    result = (
        client.table("scraped_jobs")
        .upsert(rows, on_conflict="id")
        .execute()
    )
    return len(result.data) if result.data else 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    print("=" * 60)
    print("MCT PathAI - Sync jobs: SQLite -> Supabase (scraped_jobs)")
    print("=" * 60)

    # 1. Load from SQLite
    print(f"\n[1/3] Loading jobs from {SQLITE_PATH} ...")
    try:
        raw_jobs = load_jobs_from_sqlite()
    except FileNotFoundError as exc:
        print(f"  ERROR: {exc}")
        sys.exit(1)

    if not raw_jobs:
        print("  No jobs found in SQLite. Run the scraper first.")
        sys.exit(0)

    print(f"  {len(raw_jobs)} jobs loaded from SQLite")

    # 2. Coerce rows
    print("\n[2/3] Preparing rows for Supabase ...")
    coerced = [_coerce_row(r) for r in raw_jobs]
    print(f"  {len(coerced)} rows ready")

    # 3. Upsert in batches
    print("\n[3/3] Upserting to Supabase jobs table ...")
    client = _get_supabase()
    total_upserted = 0

    for i in range(0, len(coerced), _BATCH_SIZE):
        batch = coerced[i : i + _BATCH_SIZE]
        batch_num = i // _BATCH_SIZE + 1
        total_batches = (len(coerced) + _BATCH_SIZE - 1) // _BATCH_SIZE

        try:
            upserted = upsert_batch(client, batch)
            total_upserted += upserted
            print(f"  Batch {batch_num}/{total_batches}: {upserted} rows upserted")
        except Exception as exc:
            print(f"  Batch {batch_num}/{total_batches}: ERROR — {exc}")
            # Continue with remaining batches rather than aborting
            continue

        if i + _BATCH_SIZE < len(coerced):
            time.sleep(_BATCH_DELAY)

    print(f"\n{'=' * 60}")
    print(f"Done. {total_upserted} / {len(coerced)} rows upserted to Supabase scraped_jobs table.")


if __name__ == "__main__":
    run()
