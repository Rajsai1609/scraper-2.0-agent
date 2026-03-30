from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from src.core.models import Job

# BambooHR public job board API
BASE_URL = "https://api.bamboohr.com/api/gateway.php/{subdomain}/v1/applicant_tracking/jobs"


def fetch_jobs(company: dict[str, Any]) -> list[Job]:
    subdomain = company.get("subdomain", company["slug"])

    try:
        response = requests.get(
            BASE_URL.format(subdomain=subdomain),
            headers={"Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    return [_parse(item, company["name"]) for item in data]


def _parse(raw: dict[str, Any], company_name: str) -> Job:
    job_id = f"bamboohr-{raw.get('id', 'unknown')}"

    date_posted = None
    if raw.get("datePosted"):
        try:
            date_posted = datetime.fromisoformat(raw["datePosted"])
        except ValueError:
            pass

    location_parts = filter(None, [
        raw.get("location", {}).get("city"),
        raw.get("location", {}).get("state"),
        raw.get("location", {}).get("country"),
    ])
    location = ", ".join(location_parts) or None

    return Job(
        id=job_id,
        company=company_name,
        ats_platform="bamboohr",
        title=raw.get("jobOpeningName", raw.get("title", "")),
        location=location,
        url=raw.get("jobUrl", ""),
        date_posted=date_posted,
    )
