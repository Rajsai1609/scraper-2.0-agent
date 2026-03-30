from __future__ import annotations

from typing import Any

import requests

from src.core.models import Job

# Workday does not have a unified public API; this module uses their
# internal search endpoint that most Workday career sites expose.
SEARCH_PATH = "/wday/cxs/{tenant}/jobs/search"


def fetch_jobs(company: dict[str, Any]) -> list[Job]:
    """
    Fetches jobs from a Workday-powered career site.
    The `tenant` and `url` fields in the company config drive the request.
    """
    tenant = company.get("tenant", company["slug"])
    base = company["url"].rstrip("/")

    # Workday career sites vary widely; fall back gracefully.
    try:
        response = requests.post(
            f"{base}/fs/searchRequest",
            json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""},
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    job_postings = data.get("jobPostings") or []
    return [_parse(p, company["name"]) for p in job_postings]


def _parse(raw: dict[str, Any], company_name: str) -> Job:
    job_id = f"workday-{raw.get('bulletFields', [raw.get('title', 'unknown')])[0]}"
    external_path = raw.get("externalPath", "")

    return Job(
        id=job_id,
        company=company_name,
        ats_platform="workday",
        title=raw.get("title", ""),
        location=raw.get("locationsText"),
        url=external_path if external_path.startswith("http") else f"https://careers.{company_name.lower()}.com{external_path}",
    )
