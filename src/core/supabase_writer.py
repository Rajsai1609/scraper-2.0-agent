"""
Supabase write-through layer — upserts scraped jobs to the `scraped_jobs` table.

Called after every scrape run.  Requires SUPABASE_URL and SUPABASE_KEY in .env
(or environment).  If credentials are absent the module degrades gracefully and
logs a warning so the local SQLite pipeline is never blocked.

Table columns mirror the Job model.  Fields that the dashboard reads
(scraper_score, visa_flag) are mapped explicitly.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from dotenv import load_dotenv

from src.core.models import Job

load_dotenv()

_BATCH_SIZE = 100  # rows per upsert call


def _get_client():
    """Return a Supabase client or None if credentials are missing."""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def _job_to_row(job: Job) -> dict:
    """Serialise a Job into a dict matching the scraped_jobs table columns."""
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "ats_platform": job.ats_platform,
        "url": job.url,
        "description": job.description or "",
        "location": job.location or "",
        "country": job.country,
        "work_mode": job.work_mode.value,
        "usa_region": job.usa_region or "",
        "is_usa_job": job.is_usa_job,
        "experience_level": job.experience_level.value,
        "years_min": job.years_min,
        "years_max": job.years_max,
        "is_entry_eligible": job.is_entry_eligible,
        "h1b_sponsor": job.h1b_sponsor,
        "opt_friendly": job.opt_friendly,
        "stem_opt_eligible": job.stem_opt_eligible,
        "visa_flag": job.h1b_sponsor is False,  # flagged when explicitly NOT sponsoring
        "visa_notes": job.visa_notes or "",
        "skills": job.skills,
        "job_category": job.job_category.value,
        "scraper_score": job.fit_score,
        "date_posted": job.date_posted.isoformat() if job.date_posted else None,
        "fetched_at": job.fetched_at.isoformat(),
        "expires_at": job.expires_at.isoformat(),
    }


def upsert_jobs(jobs: list[Job]) -> tuple[int, int]:
    """
    Upsert jobs into the Supabase `scraped_jobs` table.

    Uses ON CONFLICT (id) DO UPDATE via Supabase's upsert() so re-runs
    update stale rows rather than creating duplicates.

    Returns (upserted_count, error_count).
    """
    if not jobs:
        return 0, 0

    client = _get_client()
    if client is None:
        print("[supabase_writer] SUPABASE_URL / SUPABASE_KEY not set — skipping Supabase write.")
        return 0, 0

    rows = [_job_to_row(j) for j in jobs]
    upserted = 0
    errors = 0

    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i : i + _BATCH_SIZE]
        try:
            client.table("scraped_jobs").upsert(batch, on_conflict="id").execute()
            upserted += len(batch)
        except Exception as exc:
            print(f"[supabase_writer] Batch {i // _BATCH_SIZE + 1} failed: {exc}")
            errors += len(batch)

    return upserted, errors
