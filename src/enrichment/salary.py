from __future__ import annotations

import re
from typing import Optional

from src.core.models import Job

# Matches patterns like "$120k", "$120,000", "120k - 180k", "$120,000 - $180,000"
_SALARY_RE = re.compile(
    r"\$?\s*(\d{2,3}(?:,\d{3})?(?:\.\d+)?)\s*k?\s*"
    r"(?:[-–—to]+\s*\$?\s*(\d{2,3}(?:,\d{3})?(?:\.\d+)?)\s*k?)?",
    re.IGNORECASE,
)


def _to_int(value: str, is_k: bool) -> int:
    cleaned = value.replace(",", "")
    amount = float(cleaned)
    return int(amount * 1000) if is_k else int(amount)


def extract_salary(text: str) -> tuple[Optional[int], Optional[int]]:
    """Return (min, max) salary integers extracted from text, or (None, None)."""
    for match in _SALARY_RE.finditer(text):
        raw_min = match.group(1)
        raw_max = match.group(2)
        is_k = "k" in match.group(0).lower()

        try:
            salary_min = _to_int(raw_min, is_k)
            salary_max = _to_int(raw_max, is_k) if raw_max else salary_min
            # Sanity check: reasonable salary range
            if 20_000 <= salary_min <= 1_000_000:
                return salary_min, salary_max
        except (ValueError, OverflowError):
            continue

    return None, None


def enrich_job(job: Job) -> Job:
    """Return a new Job with salary fields populated if not already set."""
    if job.salary_min is not None or not job.description:
        return job
    salary_min, salary_max = extract_salary(job.description)
    return job.model_copy(
        update={"salary_min": salary_min, "salary_max": salary_max}
    )
