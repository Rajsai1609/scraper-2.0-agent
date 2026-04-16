"""JobSpy fetcher — scrapes LinkedIn, Indeed, Glassdoor, and ZipRecruiter."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.core.models import Job, WorkMode

logger = logging.getLogger(__name__)

SEARCH_TERMS = [
    "software engineer",
    "data engineer",
    "data analyst",
    "machine learning engineer",
    "cloud engineer",
    "backend engineer",
    "full stack engineer",
]

SOURCES = ["linkedin", "indeed", "glassdoor", "zip_recruiter"]
LOCATION = "United States"
RESULTS_PER_TERM = 100
# 7 days in hours — JobSpy's hours_old parameter
HOURS_OLD = 168


def fetch_all_jobs() -> tuple[list[Job], dict[str, int]]:
    """
    Scrape jobs from LinkedIn, Indeed, Glassdoor, and ZipRecruiter via JobSpy.

    Returns:
        (jobs, source_counts) where source_counts maps site name → job count.
    """
    try:
        from jobspy import scrape_jobs  # type: ignore[import]
    except ImportError:
        logger.error("jobspy not installed — run: pip install jobspy")
        return [], {}

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
    raw_jobs: list[Job] = []
    source_counts: dict[str, int] = {}
    seen_urls: set[str] = set()

    for term in SEARCH_TERMS:
        try:
            df = scrape_jobs(
                site_name=SOURCES,
                search_term=term,
                location=LOCATION,
                results_wanted=RESULTS_PER_TERM,
                hours_old=HOURS_OLD,
                country_indeed="usa",   # prevents invalid-country errors (cyprus, lesotho, etc.)
            )
        except Exception as exc:
            logger.warning("JobSpy error for '%s': %s", term, exc)
            continue

        if df is None or df.empty:
            continue

        for _, row in df.iterrows():
            url = _str(row.get("job_url")) or _str(row.get("job_url_direct"))
            if not url or url in seen_urls:
                continue

            # Date filter — keep only last-7-days jobs
            date_posted = _parse_date(row.get("date_posted"))
            if date_posted and date_posted < cutoff:
                continue

            site = _str(row.get("site", "jobspy"))
            job = _row_to_job(row, site, date_posted)
            if job is None:
                continue

            seen_urls.add(url)
            raw_jobs.append(job)
            source_counts[site] = source_counts.get(site, 0) + 1

    return raw_jobs, source_counts


def _row_to_job(row: object, site: str, date_posted: Optional[datetime]) -> Optional[Job]:
    """Convert a DataFrame row to a Job model."""
    url = _str(row.get("job_url")) or _str(row.get("job_url_direct"))  # type: ignore[union-attr]
    title = _str(row.get("title"))  # type: ignore[union-attr]
    company = _str(row.get("company"))  # type: ignore[union-attr]

    if not url or not title or not company:
        return None

    location = _str(row.get("location", ""))  # type: ignore[union-attr]
    description = _str(row.get("description", ""))  # type: ignore[union-attr]

    # Build a platform-native ID (e.g. linkedin-12345678, indeed-abc123).
    # This matches the ashby-xxx / greenhouse-xxx format used by ATS fetchers
    # and ensures the JOIN with student_job_scores works in the dashboard.
    raw_id = _str(row.get("id"))  # type: ignore[union-attr]
    platform_id = f"{site}-{raw_id}" if raw_id else ""

    # Work mode detection from JobSpy's is_remote flag
    is_remote = row.get("is_remote")  # type: ignore[union-attr]
    if is_remote is True:
        work_mode = WorkMode.REMOTE
    elif location and "remote" in location.lower():
        work_mode = WorkMode.REMOTE
    else:
        work_mode = WorkMode.UNKNOWN

    return Job(
        id=platform_id,          # "" → model validator derives SHA-256 as fallback
        title=title,
        company=company,
        ats_platform=site,
        url=url,
        location=location,
        description=description,
        work_mode=work_mode,
        date_posted=date_posted,
    )


def _str(value: object) -> str:
    """Safely coerce a value to a stripped string, returning '' for null/NaN."""
    if value is None:
        return ""
    try:
        import math
        if isinstance(value, float) and math.isnan(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _parse_date(value: object) -> Optional[datetime]:
    """Parse a date value from JobSpy output into a timezone-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    # pandas Timestamp
    try:
        ts = value.to_pydatetime()  # type: ignore[union-attr]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except AttributeError:
        pass
    # ISO string fallback
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None
