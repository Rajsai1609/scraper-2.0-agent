from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import requests

from src.core.models import Job

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def fetch_jobs(company: dict[str, Any]) -> list[Job]:
    slug = company["slug"]
    response = requests.get(BASE_URL.format(slug=slug), timeout=15)
    response.raise_for_status()
    data = response.json()
    postings = data.get("jobs") or []
    return [_parse(p, company["name"]) for p in postings]


def _parse_salary(compensation: Optional[dict]) -> tuple[Optional[int], Optional[int]]:
    if not compensation:
        return None, None
    for tier in compensation.get("compensationTiers") or []:
        for component in tier.get("components") or []:
            if component.get("compensationType") == "Salary":
                return component.get("minValue"), component.get("maxValue")
    return None, None


def _parse(raw: dict[str, Any], company_name: str) -> Job:
    job_id = f"ashby-{raw['id']}"

    date_posted = None
    if raw.get("publishedAt"):
        try:
            date_posted = datetime.fromisoformat(
                raw["publishedAt"].replace("Z", "+00:00")
            )
        except ValueError:
            pass

    salary_min, salary_max = _parse_salary(raw.get("compensation"))

    return Job(
        id=job_id,
        company=company_name,
        ats_platform="ashby",
        title=raw.get("title", ""),
        location=raw.get("location") or "",
        url=raw.get("jobUrl") or f"https://jobs.ashbyhq.com/{company_name.lower()}/{raw['id']}",
        description=raw.get("descriptionPlain") or "",
        date_posted=date_posted,
    )
