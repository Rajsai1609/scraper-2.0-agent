from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WorkMode(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class ExperienceLevel(str, Enum):
    NEW_GRAD = "new_grad"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    UNKNOWN = "unknown"


class JobCategory(str, Enum):
    SOFTWARE_ENGINEER = "software_engineer"
    DATA_ANALYST = "data_analyst"
    DATA_ENGINEER = "data_engineer"
    ML_AI_ENGINEER = "ml_ai_engineer"
    DEVOPS_CLOUD = "devops_cloud"
    FRONTEND_ENGINEER = "frontend_engineer"
    BACKEND_ENGINEER = "backend_engineer"
    FULLSTACK_ENGINEER = "fullstack_engineer"
    PRODUCT_MANAGER = "product_manager"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Region detection data
# ---------------------------------------------------------------------------

# Maps state abbreviations and city keywords → region name.
# Ordered so more-specific matches (cities) shadow state abbreviations.
_REGION_RULES: list[tuple[str, list[str]]] = [
    (
        "Pacific Northwest",
        ["WA", "OR", "ID", "Seattle", "Portland", "Bothell",
         "Kirkland", "Bellevue", "Redmond", "Everett"],
    ),
    (
        "West Coast",
        ["CA", "NV", "AZ", "San Francisco", "SF", "Los Angeles", "LA",
         "San Diego"],
    ),
    (
        "Mountain",
        ["CO", "UT", "MT", "WY", "NM", "Denver", "Salt Lake City"],
    ),
    (
        "Midwest",
        ["IL", "OH", "MI", "IN", "WI", "MN", "MO",
         "Chicago", "Detroit"],
    ),
    (
        "South",
        ["TX", "FL", "GA", "NC", "TN", "VA",
         "Atlanta", "Miami", "Austin"],
    ),
    (
        "Northeast",
        ["NY", "MA", "PA", "NJ", "CT",
         "New York", "NYC", "Boston", "Philadelphia"],
    ),
]

# USA state abbreviations used for is_usa_job detection
_USA_STATES: frozenset[str] = frozenset([
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
])

_USA_KEYWORDS: frozenset[str] = frozenset([
    "united states", "usa", "u.s.", "u.s.a", "us ",
    "new york", "san francisco", "los angeles", "seattle", "chicago",
    "boston", "austin", "denver", "atlanta", "miami",
])

_CANADIAN_PROVINCES: frozenset[str] = frozenset([
    "british columbia", "ontario", "alberta", "quebec", "manitoba",
    "saskatchewan", "nova scotia", "new brunswick", "newfoundland",
    "prince edward island", "yukon", "nunavut", "northwest territories",
])


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def generate_job_id(company: str, url: str) -> str:
    """SHA-256 hex digest of ``company.lower() + url.lower()``."""
    payload = f"{company.lower()}|{url.lower()}".encode()
    return hashlib.sha256(payload).hexdigest()


def detect_work_mode(title: str, location: str) -> WorkMode:
    """
    Infer work mode from title and location strings.

    Priority: REMOTE > HYBRID > ONSITE > UNKNOWN
    ONSITE is returned only when a recognisable US city/state is present
    and no remote/hybrid signal exists.
    """
    combined = f"{title} {location}".lower()

    if "hybrid" in combined:
        return WorkMode.HYBRID
    if "remote" in combined:
        return WorkMode.REMOTE

    # ONSITE: location contains a known US state abbreviation or city keyword
    loc_upper = location.upper()
    has_us_place = any(
        f" {state} " in f" {loc_upper} " or loc_upper.endswith(f", {state}")
        for state in _USA_STATES
    ) or any(kw in location.lower() for kw in _USA_KEYWORDS)

    if has_us_place:
        return WorkMode.ONSITE

    return WorkMode.UNKNOWN


def detect_usa_region(location: str, work_mode: WorkMode) -> str:
    """
    Map a raw location string to a named US region.

    Returns one of:
      "Pacific Northwest", "West Coast", "Mountain", "Midwest",
      "South", "Northeast", "Remote", "Other USA", or "" (non-USA / unknown).
    """
    if not location and work_mode is WorkMode.REMOTE:
        return "Remote"

    loc_upper = location.upper()
    loc_lower = location.lower()

    for region, keywords in _REGION_RULES:
        for kw in keywords:
            kw_upper = kw.upper()
            # State abbreviation: match as a whole word/token
            if len(kw) == 2 and kw.isupper():
                if (
                    f" {kw_upper}," in f" {loc_upper},"
                    or f" {kw_upper} " in f" {loc_upper} "
                    or loc_upper.endswith(f", {kw_upper}")
                    or loc_upper == kw_upper
                ):
                    return region
            else:
                # City/phrase: case-insensitive substring
                if kw.lower() in loc_lower:
                    return region

    if work_mode is WorkMode.REMOTE:
        return "Remote"

    # Last resort: any US state abbreviation present → Other USA
    tokens = re.split(r"[\s,]+", loc_upper)
    if any(tok in _USA_STATES for tok in tokens):
        return "Other USA"

    return ""


def _is_usa_job(location: str, work_mode: WorkMode) -> bool:
    """Return True when the job is clearly US-based.

    Delegates to the strict geography gate in src.enrichment.geography.
    """
    from src.enrichment.geography import is_usa_job  # local import avoids circular dep
    return is_usa_job(location, work_mode.value)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Job(BaseModel):
    # IDENTITY
    id: str = Field(default="")
    title: str
    company: str
    ats_platform: str
    url: str
    description: str = ""

    # LOCATION
    location: str = ""
    country: Optional[str] = None
    work_mode: WorkMode = WorkMode.UNKNOWN
    usa_region: str = ""
    is_usa_job: bool = False

    # EXPERIENCE
    experience_level: ExperienceLevel = ExperienceLevel.UNKNOWN
    years_min: Optional[int] = None
    years_max: Optional[int] = None
    is_entry_eligible: bool = False

    # VISA
    h1b_sponsor: Optional[bool] = None
    opt_friendly: Optional[bool] = None
    stem_opt_eligible: Optional[bool] = None
    visa_notes: str = ""

    # ENRICHMENT
    skills: list[str] = Field(default_factory=list)
    job_category: JobCategory = JobCategory.OTHER

    # SCORING
    fit_score: Optional[float] = None

    # METADATA
    date_posted: Optional[datetime] = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    expires_at: datetime = Field(default=None)  # type: ignore[assignment]

    @model_validator(mode="after")
    def _derive_computed_fields(self) -> "Job":
        # id: derive from company + url when not supplied
        if not self.id:
            object.__setattr__(self, "id", generate_job_id(self.company, self.url))

        # expires_at: default to fetched_at + 30 days
        if self.expires_at is None:
            object.__setattr__(
                self, "expires_at", self.fetched_at + timedelta(days=30)
            )

        # work_mode: auto-detect when still UNKNOWN
        if self.work_mode is WorkMode.UNKNOWN:
            object.__setattr__(
                self,
                "work_mode",
                detect_work_mode(self.title, self.location),
            )

        # is_usa_job + usa_region derive from (possibly just-set) work_mode
        if not self.is_usa_job:
            object.__setattr__(
                self, "is_usa_job", _is_usa_job(self.location, self.work_mode)
            )

        if not self.usa_region:
            object.__setattr__(
                self,
                "usa_region",
                detect_usa_region(self.location, self.work_mode),
            )

        # country: normalise to "USA" for detected US jobs
        if self.country is None and self.is_usa_job:
            object.__setattr__(self, "country", "USA")

        return self

    model_config = {"frozen": True}


class Resume(BaseModel):
    raw_text: str
    skills: list[str] = Field(default_factory=list)
    experience_years: Optional[float] = None
