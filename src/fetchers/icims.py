from __future__ import annotations

from typing import Any

import requests

from src.core.models import Job

# iCIMS exposes a REST API under the customer's portal subdomain.
# config shape: { name, slug, portal_id, url }
BASE_URL = "https://api.icims.com/customers/{portal_id}/search/jobs"


def fetch_jobs(company: dict[str, Any]) -> list[Job]:
    portal_id = company.get("portal_id", "")
    if not portal_id:
        return []

    headers = {"Content-Type": "application/json"}
    payload = {
        "filters": [],
        "sortBy": "date",
        "sortDirection": "desc",
        "offset": 0,
        "pageSize": 50,
    }

    try:
        response = requests.post(
            BASE_URL.format(portal_id=portal_id),
            json=payload,
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    return [_parse(item, company["name"]) for item in data.get("searchResults", [])]


def _parse(raw: dict[str, Any], company_name: str) -> Job:
    job_id = f"icims-{raw.get('id', raw.get('requisitionId', 'unknown'))}"

    return Job(
        id=job_id,
        company=company_name,
        ats_platform="icims",
        title=raw.get("jobtitle", raw.get("title", "")),
        location=raw.get("joblocation", {}).get("value"),
        url=raw.get("canonicalUrl", ""),
    )
