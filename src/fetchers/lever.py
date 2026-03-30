from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from src.core.models import Job

BASE_URL = "https://api.lever.co/v0/postings/{slug}"


def fetch_jobs(company: dict[str, Any]) -> list[Job]:
    slug = company["slug"]
    response = requests.get(
        BASE_URL.format(slug=slug),
        params={"mode": "json"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    return [_parse(job, company["name"]) for job in data]


def _parse(raw: dict[str, Any], company_name: str) -> Job:
    job_id = f"lever-{raw['id']}"
    location = raw.get("categories", {}).get("location")
    commitment = raw.get("categories", {}).get("commitment", "")

    date_posted = None
    if raw.get("createdAt"):
        try:
            date_posted = datetime.fromtimestamp(raw["createdAt"] / 1000, tz=timezone.utc)
        except (ValueError, OSError):
            pass

    description = raw.get("descriptionPlain") or raw.get("descriptionBodyPlain") or ""

    return Job(
        id=job_id,
        company=company_name,
        ats_platform="lever",
        title=raw.get("text", ""),
        location=location,
        url=raw.get("hostedUrl", ""),
        description=description,
        date_posted=date_posted,
    )
