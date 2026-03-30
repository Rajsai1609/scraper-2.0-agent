from __future__ import annotations

import re

from src.core.models import Job

KNOWN_H1B_SPONSORS: frozenset[str] = frozenset([
    # Big Tech
    "google", "microsoft", "amazon", "apple", "meta", "netflix",
    "ibm", "oracle", "salesforce", "adobe", "intel", "qualcomm",
    "nvidia", "amd", "broadcom", "cisco",
    # Mid-size / well-known sponsors
    "stripe", "dropbox", "figma", "notion", "canva", "asana",
    "zendesk", "hubspot", "intercom", "amplitude", "gitlab",
    "datadog", "mongodb", "elastic", "confluent", "hashicorp", "okta",
    "twilio", "sendgrid", "cloudflare", "fastly", "snowflake",
    "databricks", "palantir", "splunk", "new relic", "pagerduty",
    "atlassian", "zenefits", "workday", "servicenow", "veeva",
    "zoom", "slack", "box", "docusign", "ringcentral",
    "linkedin", "twitter", "pinterest", "lyft", "uber", "airbnb",
    "doordash", "instacart", "robinhood", "coinbase", "plaid",
    "brex", "rippling", "gusto", "chime", "affirm", "klarna",
    "square", "block", "paypal", "intuit",
])

_H1B_YES: list[str] = [
    r"\bwill\s+(?:provide\s+)?(?:visa\s+)?sponsorship\b",
    r"\bvisa\s+sponsorship\s+(?:is\s+)?(?:provided|available|offered)\b",
    r"\bh[\s-]?1[\s-]?b\s+(?:visa\s+)?sponsor\b",
    r"\bopen\s+to\s+sponsoring\b",
    r"\bwork\s+visa\s+sponsor\b",
]
_H1B_NO: list[str] = [
    r"\bno\s+(?:visa\s+)?sponsorship\b",
    r"\bsponsorship\s+(?:is\s+)?not\s+(?:available|provided|offered)\b",
    r"\bmust\s+(?:be\s+(?:a\s+)?)?(?:us\s+)?citizen\b",
    r"\bus\s+citizen(?:ship)?\s+(?:is\s+)?required\b",
    r"\bsecurity\s+clearance\s+required\b",
    r"\bauthorized\s+to\s+work\s+in\s+the\s+(?:us|united\s+states)\b",
    r"\bcurrent(?:ly)?\s+(?:reside|located|live)\s+in\s+the\s+(?:us|united\s+states)\b",
]

_OPT: list[str] = [
    r"\bopt\b",
    r"\bcpt\b",
    r"\bf[\s-]?1\s+(?:visa\s+)?(?:holder|student|worker)\b",
    r"\bstem\s+opt\b",
]
_STEM_OPT: list[str] = [
    r"\bstem\s+opt\b",
    r"\bstem\s+(?:visa\s+)?extension\b",
]


def enrich_job(job: Job) -> Job:
    """Return a new Job with visa fields populated from description."""
    desc = job.description.lower() if job.description else ""
    company_lower = job.company.lower() if job.company else ""

    # Company name lookup takes priority over description parsing
    # Bidirectional partial match: "Stripe, Inc." → matches "stripe"; "stripe" → matches "Stripe"
    h1b_sponsor: bool | None = None
    if any(
        sponsor in company_lower or company_lower in sponsor
        for sponsor in KNOWN_H1B_SPONSORS
    ):
        h1b_sponsor = True
    else:
        for p in _H1B_YES:
            if re.search(p, desc):
                h1b_sponsor = True
                break
        if h1b_sponsor is None:
            for p in _H1B_NO:
                if re.search(p, desc):
                    h1b_sponsor = False
                    break

    opt_friendly: bool | None = None
    if any(re.search(p, desc) for p in _OPT):
        opt_friendly = True

    stem_opt_eligible: bool | None = None
    if any(re.search(p, desc) for p in _STEM_OPT):
        stem_opt_eligible = True

    return job.model_copy(update={
        "h1b_sponsor": h1b_sponsor,
        "opt_friendly": opt_friendly,
        "stem_opt_eligible": stem_opt_eligible,
    })
