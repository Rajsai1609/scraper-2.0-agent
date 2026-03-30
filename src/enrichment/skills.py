from __future__ import annotations

import re

from src.core.models import Job

# Canonical skill taxonomy — extend as needed
SKILL_PATTERNS: dict[str, list[str]] = {
    "python": [r"\bpython\b", r"\bdjango\b", r"\bfastapi\b", r"\bflask\b"],
    "javascript": [r"\bjavascript\b", r"\btypescript\b", r"\bnode\.?js\b", r"\breact\b", r"\bvue\b", r"\bangular\b"],
    "go": [r"\bgolang\b", r"\b(?:go\s+lang)\b", r"\bgo\s+(?:developer|engineer|programming)\b"],
    "rust": [r"\brust\b"],
    "java": [r"\bjava\b(?!script)", r"\bspring\b", r"\bjvm\b"],
    "sql": [r"\bsql\b", r"\bpostgres\b", r"\bmysql\b", r"\bsqlite\b"],
    "kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "docker": [r"\bdocker\b", r"\bcontainer\b"],
    "aws": [r"\baws\b", r"\bamazon web services\b"],
    "gcp": [r"\bgcp\b", r"\bgoogle cloud\b"],
    "azure": [r"\bazure\b", r"\bmicrosoft cloud\b"],
    "machine_learning": [r"\bmachine learning\b", r"\bml\b", r"\bdeep learning\b", r"\bneural network\b", r"\bllm\b"],
    "data_engineering": [r"\bspark\b", r"\bairflow\b", r"\bkafka\b", r"\bdata pipeline\b", r"\betl\b"],
    "devops": [r"\bdevops\b", r"\bci/cd\b", r"\bterraform\b", r"\bansible\b"],
    "system_design": [r"\bdistributed systems\b", r"\bmicroservice\b", r"\bscalability\b"],
}


def extract_skills(text: str) -> list[str]:
    """Return a deduplicated list of matched skill keys from free text."""
    lowered = text.lower()
    found: list[str] = []
    for skill, patterns in SKILL_PATTERNS.items():
        if any(re.search(p, lowered) for p in patterns):
            found.append(skill)
    return found


def enrich_job(job: Job) -> Job:
    """Return a new Job with skills populated from its description."""
    if not job.description:
        return job
    skills = extract_skills(job.description)
    return job.model_copy(update={"skills": skills})


def enrich_resume_skills(text: str) -> list[str]:
    return extract_skills(text)
