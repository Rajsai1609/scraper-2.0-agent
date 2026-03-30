from __future__ import annotations

import re

from src.core.models import Job, JobCategory

# Each rule is (category, title_patterns, full_text_patterns).
# Title patterns fire first since titles are the cleanest signal.
_RULES: list[tuple[JobCategory, list[str], list[str]]] = [
    (
        JobCategory.ML_AI_ENGINEER,
        [
            r"\bml\s+engineer\b", r"\bai\s+engineer\b", r"\bmachine\s+learning\s+engineer\b",
            r"\bdata\s+scientist\b", r"\bmlops\b", r"\bapplied\s+scientist\b",
            r"\bresearch\s+(?:engineer|scientist)\b",
        ],
        [
            r"\bdeep\s+learning\b", r"\bllm\b", r"\bnlp\b",
            r"\bcomputer\s+vision\b", r"\bneural\s+network\b",
        ],
    ),
    (
        JobCategory.DATA_ENGINEER,
        [
            r"\bdata\s+engineer\b", r"\bdata\s+platform\s+engineer\b",
            r"\banalytics\s+engineer\b",
        ],
        [
            r"\betl\b", r"\bdata\s+pipeline\b", r"\bdbt\b",
            r"\bairflow\b", r"\bspark\b.*\bengineer\b", r"\bkafka\b.*\bengineer\b",
        ],
    ),
    (
        JobCategory.DATA_ANALYST,
        [
            r"\bdata\s+analyst\b", r"\bbusiness\s+analyst\b",
            r"\banalytics\s+analyst\b", r"\bsql\s+analyst\b",
        ],
        [
            r"\btableau\b.*\banalys\b", r"\bpower\s+bi\b.*\banalys\b",
            r"\blookupsql\b", r"\bdata\s+visualization\b.*\banalys\b",
        ],
    ),
    (
        JobCategory.DEVOPS_CLOUD,
        [
            r"\bdevops\b", r"\bsre\b", r"\bsite\s+reliability\b",
            r"\bcloud\s+engineer\b", r"\binfrastructure\s+engineer\b",
            r"\bplatform\s+engineer\b",
        ],
        [
            r"\bkubernetes\b.*\bengineer\b", r"\bterraform\b.*\bengineer\b",
        ],
    ),
    (
        JobCategory.FULLSTACK_ENGINEER,
        [r"\bfull[\s-]?stack\b", r"\bfullstack\b"],
        [r"\bfull[\s-]?stack\b"],
    ),
    (
        JobCategory.FRONTEND_ENGINEER,
        [
            r"\bfrontend\b", r"\bfront[\s-]end\b",
            r"\bui\s+engineer\b", r"\bweb\s+(?:ui\s+)?engineer\b",
        ],
        [],
    ),
    (
        JobCategory.BACKEND_ENGINEER,
        [
            r"\bbackend\b", r"\bback[\s-]end\b",
            r"\bapi\s+engineer\b", r"\bserver[\s-]?side\b",
        ],
        [],
    ),
    (
        JobCategory.PRODUCT_MANAGER,
        [
            r"\bproduct\s+manager\b", r"\bprogram\s+manager\b",
            r"\bproduct\s+owner\b",
        ],
        [],
    ),
    (
        JobCategory.SOFTWARE_ENGINEER,
        [
            r"\bsoftware\s+engineer\b", r"\bsoftware\s+developer\b",
            r"\b\bswe\b", r"\bapplication\s+developer\b",
        ],
        [],
    ),
]


def detect_category(title: str, description: str) -> JobCategory:
    """Return the most specific JobCategory for a job posting."""
    title_lower = title.lower()
    desc_lower = description.lower()
    combined = f"{title_lower} {desc_lower}"

    for category, title_patterns, text_patterns in _RULES:
        for p in title_patterns:
            if re.search(p, title_lower):
                return category

    for category, title_patterns, text_patterns in _RULES:
        for p in text_patterns:
            if re.search(p, combined):
                return category
        # fall-through title check for full combined text too
        for p in title_patterns:
            if re.search(p, combined):
                return category

    return JobCategory.OTHER


def enrich_job(job: Job) -> Job:
    """Return a new Job with job_category populated."""
    category = detect_category(job.title, job.description)
    return job.model_copy(update={"job_category": category})
