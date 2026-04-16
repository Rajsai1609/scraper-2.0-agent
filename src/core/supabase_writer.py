"""
Job-model → dict converter + Supabase write-through.

Converts Job objects to scraped_jobs table rows, then delegates
to supabase_db.upsert_jobs_to_supabase() for the actual write.
"""
from __future__ import annotations

from src.core.models import Job
from src.core import supabase_db


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
        "visa_flag": job.h1b_sponsor is False,
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
    Convert Jobs to dicts and upsert to Supabase scraped_jobs.
    Returns (upserted_count, error_count).
    """
    if not jobs:
        return 0, 0

    rows = [_job_to_row(j) for j in jobs]
    try:
        supabase_db.upsert_jobs_to_supabase(rows)
        return len(rows), 0
    except Exception as exc:
        print(f"[supabase_writer] Upsert failed: {exc}")
        return 0, len(rows)
