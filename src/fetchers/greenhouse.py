from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import requests

from src.core.models import Job

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def fetch_jobs(company: dict[str, Any]) -> list[Job]:
    slug = company["slug"]
    response = requests.get(
        BASE_URL.format(slug=slug),
        params={"content": "true"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    return [_parse(job, company["name"]) for job in data.get("jobs", [])]


def _parse(raw: dict[str, Any], company_name: str) -> Job:
    job_id = f"greenhouse-{raw['id']}"
    location = (raw.get("location") or {}).get("name")
    date_posted = None
    if raw.get("updated_at"):
        try:
            date_posted = datetime.fromisoformat(raw["updated_at"].replace("Z", "+00:00"))
        except ValueError:
            pass

    return Job(
        id=job_id,
        company=company_name,
        ats_platform="greenhouse",
        title=raw.get("title", ""),
        location=location,
        url=raw.get("absolute_url", ""),
        description=raw.get("content"),
        date_posted=date_posted,
    )
