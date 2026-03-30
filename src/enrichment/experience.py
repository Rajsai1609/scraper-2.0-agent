from __future__ import annotations

import re

from src.core.models import ExperienceLevel, Job

_LEVEL_SIGNALS: dict[ExperienceLevel, list[str]] = {
    ExperienceLevel.NEW_GRAD: [
        r"\bnew\s+grad\b",
        r"\bentry[\s-]level\b",
        r"\brecent\s+graduate\b",
        r"\bgraduate\s+student\b",
        r"\bintern(?:ship)?\b",
        r"\bco[\s-]?op\b",
        r"\b0[\s-]*[-–]\s*1\s+year\b",
    ],
    ExperienceLevel.JUNIOR: [
        r"\bjunior\b",
        r"\bassociate\s+(?:software|data|engineer)\b",
        r"\bsoftware\s+engineer\s+i\b",
        r"\b1[\s-]*[-–]\s*3\s+years?\b",
    ],
    ExperienceLevel.SENIOR: [
        r"\bsenior\b",
        r"\bstaff\s+(?:software|data|engineer)\b",
        r"\bprincipal\b",
        r"\blead\s+(?:software|data|engineer)\b",
        r"\barchitect\b",
        r"\b(?:5|6|7|8|9|10)\+\s+years?\b",
    ],
    ExperienceLevel.MID: [
        r"\bmid[\s-]?level\b",
        r"\bsoftware\s+engineer\s+ii\b",
        r"\b3[\s-]*[-–]\s*5\s+years?\b",
        r"\b[34]\s+years?\s+(?:of\s+)?experience\b",
    ],
}

_YEARS_RE = re.compile(
    r"(\d+)\s*[-–to]+\s*(\d+)\s+years?"
    r"|(\d+)\+\s+years?"
    r"|\bminimum\s+of?\s+(\d+)\s+years?\b"
    r"|\bat\s+least\s+(\d+)\s+years?\b",
    re.IGNORECASE,
)


def extract_years(text: str) -> tuple[int | None, int | None]:
    """Return (years_min, years_max) extracted from free text."""
    for m in _YEARS_RE.finditer(text):
        g = m.groups()
        if g[0] and g[1]:   # "X–Y years"
            return int(g[0]), int(g[1])
        if g[2]:             # "X+ years"
            return int(g[2]), None
        if g[3]:             # "minimum X years"
            return int(g[3]), None
        if g[4]:             # "at least X years"
            return int(g[4]), None
    return None, None


def detect_experience_level(title: str, description: str) -> ExperienceLevel:
    """Infer ExperienceLevel from title then full text."""
    title_lower = title.lower()
    # Title is the strongest signal — check it alone first
    for level in (
        ExperienceLevel.NEW_GRAD,
        ExperienceLevel.JUNIOR,
        ExperienceLevel.SENIOR,
        ExperienceLevel.MID,
    ):
        for pattern in _LEVEL_SIGNALS[level]:
            if re.search(pattern, title_lower):
                return level

    combined = f"{title} {description}".lower()
    for level in (
        ExperienceLevel.NEW_GRAD,
        ExperienceLevel.JUNIOR,
        ExperienceLevel.SENIOR,
        ExperienceLevel.MID,
    ):
        for pattern in _LEVEL_SIGNALS[level]:
            if re.search(pattern, combined):
                return level

    return ExperienceLevel.UNKNOWN


def enrich_job(job: Job) -> Job:
    """Return a new Job with experience fields populated."""
    combined = f"{job.title} {job.description}"
    years_min, years_max = extract_years(combined)
    level = detect_experience_level(job.title, job.description)

    is_entry_eligible = (
        level in (ExperienceLevel.NEW_GRAD, ExperienceLevel.JUNIOR)
        or (years_min is not None and years_min <= 2)
        or (level is ExperienceLevel.UNKNOWN and years_min is None)
    )

    return job.model_copy(update={
        "experience_level": level,
        "years_min": years_min,
        "years_max": years_max,
        "is_entry_eligible": is_entry_eligible,
    })
