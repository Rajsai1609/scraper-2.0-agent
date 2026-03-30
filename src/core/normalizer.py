from __future__ import annotations

import re
from typing import Optional

from src.core.models import Job, WorkMode, _is_usa_job, detect_usa_region, detect_work_mode


def normalize_title(title: str) -> str:
    """Lowercase and strip excess whitespace from a job title."""
    return re.sub(r"\s+", " ", title.strip().lower())


def normalize_location(raw: Optional[str]) -> str:
    """Strip and return a clean location string (empty string when absent)."""
    return raw.strip() if raw else ""


def normalize_job(job: Job) -> Job:
    """
    Return a new Job with a cleaned title and location.

    model_copy does NOT re-run Pydantic validators, so work_mode,
    is_usa_job, usa_region, and country are re-derived explicitly here
    from the cleaned strings.
    """
    clean_title = normalize_title(job.title)
    clean_location = normalize_location(job.location)
    new_work_mode = detect_work_mode(clean_title, clean_location)
    new_is_usa = _is_usa_job(clean_location, new_work_mode)
    new_usa_region = detect_usa_region(clean_location, new_work_mode)
    new_country = "USA" if new_is_usa else job.country

    return job.model_copy(
        update={
            "title": clean_title,
            "location": clean_location,
            "work_mode": new_work_mode,
            "is_usa_job": new_is_usa,
            "usa_region": new_usa_region,
            "country": new_country,
        }
    )
