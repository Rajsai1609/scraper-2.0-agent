from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Step 1 — IMMEDIATE REJECT
# All checked with word boundaries to avoid false matches
# (e.g. "india" must not reject "Indianapolis")
# ---------------------------------------------------------------------------

_REJECT_COUNTRIES: tuple[str, ...] = (
    "mexico", "canada", "denmark", "poland", "germany",
    "france", "united kingdom", "england", "scotland",
    "wales", "ireland", "australia", "india", "singapore",
    "netherlands", "sweden", "norway", "finland", "switzerland",
    "austria", "belgium", "spain", "italy", "portugal",
    "brazil", "argentina", "colombia", "chile", "peru",
    "japan", "china", "korea", "taiwan", "philippines",
    "vietnam", "thailand", "indonesia", "malaysia",
    "pakistan", "bangladesh", "sri lanka", "nepal",
    "nigeria", "kenya", "ghana", "south africa", "egypt",
    "uae", "saudi arabia", "qatar", "israel", "turkey",
    "new zealand", "czech republic", "hungary", "romania",
    "bulgaria", "ukraine", "russia", "greece", "croatia",
    "uk",
)

_REJECT_CANADIAN_PROVINCES: tuple[str, ...] = (
    "british columbia", "ontario", "alberta", "quebec",
    "manitoba", "saskatchewan", "nova scotia",
    "new brunswick", "newfoundland", "prince edward",
    "northwest territories", "yukon", "nunavut",
)

_REJECT_REGIONAL_TERMS: tuple[str, ...] = (
    "emea", "apac", "latam", "europe", "asia", "africa",
    "oceania", "worldwide", "global", "globally", "anywhere",
    "open to all", "all countries", "international",
)

# Compile one regex for all Step-1 terms, longest first (avoids short-match shadowing)
_ALL_REJECT_TERMS: tuple[str, ...] = (
    _REJECT_COUNTRIES + _REJECT_CANADIAN_PROVINCES + _REJECT_REGIONAL_TERMS
)

_STEP1_RE = re.compile(
    r"\b(" +
    "|".join(re.escape(t) for t in sorted(_ALL_REJECT_TERMS, key=len, reverse=True)) +
    r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Step 2 — IMMEDIATE ACCEPT
# ---------------------------------------------------------------------------

# Sorted longest-first so "united states only" matches before "united states"
_ACCEPT_PHRASES: tuple[str, ...] = (
    "united states only", "united states", "usa",
    "u.s.a", "u.s.",
    "us-remote", "remote - us", "remote us", "us remote",
    "us only",
)

_ZIP_RE = re.compile(r"\b\d{5}\b")

# ---------------------------------------------------------------------------
# Step 3 — Full US state names
# ---------------------------------------------------------------------------

_US_STATE_NAMES: tuple[str, ...] = (
    "alabama", "alaska", "arizona", "arkansas", "california",
    "colorado", "connecticut", "delaware", "florida", "georgia",
    "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland",
    "massachusetts", "michigan", "minnesota", "mississippi", "missouri",
    "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia",
)

# ---------------------------------------------------------------------------
# Step 4 — Major US cities and regional terms
# ---------------------------------------------------------------------------

_US_CITIES: tuple[str, ...] = (
    "new york", "los angeles", "chicago", "houston",
    "phoenix", "philadelphia", "san antonio", "san diego",
    "dallas", "san jose", "austin", "jacksonville",
    "san francisco", "seattle", "denver", "nashville",
    "boston", "las vegas", "portland", "atlanta", "miami",
    "minneapolis", "tampa", "raleigh", "charlotte",
    "bothell", "kirkland", "bellevue", "redmond", "everett",
    "omaha", "sacramento", "colorado springs",
    "indianapolis", "columbus", "fort worth", "memphis",
    "louisville", "baltimore", "milwaukee", "washington dc",
    "pacific northwest", "midwest", "northeast", "south",
)

# ---------------------------------------------------------------------------
# Step 5 — State abbreviations in address context
# ---------------------------------------------------------------------------

# Safe abbreviations: no collision risk with non-US meanings
_SAFE_ABBRS: frozenset[str] = frozenset([
    "AK", "AZ", "AR", "CA", "CO", "CT", "FL", "HI", "ID", "IL",
    "IA", "KS", "KY", "MD", "MA", "MI", "MN", "MO", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "RI", "SC", "SD",
    "TN", "TX", "UT", "VT", "WA", "WV", "WI", "WY", "DC",
])

# Collision abbreviations: only accepted when a known US city is also present
_COLLISION_ABBRS: frozenset[str] = frozenset([
    "AL", "DE", "GA", "IN", "LA", "ME", "MS", "MT", "OK", "OR", "PA", "VA",
])


def _make_abbr_pattern(abbrs: frozenset[str]) -> re.Pattern[str]:
    """Match a state abbreviation preceded by comma/space and followed by
    a digit, another comma, or end-of-string (address context)."""
    alts = "|".join(sorted(abbrs))
    return re.compile(
        rf"(?:,\s*|\s+)({alts})(?:\s+\d|\s*,|\s*$)",
        re.IGNORECASE,
    )


_SAFE_ABBR_RE = _make_abbr_pattern(_SAFE_ABBRS)
_COLLISION_ABBR_RE = _make_abbr_pattern(_COLLISION_ABBRS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_usa_job(location: str, work_mode: str = "") -> bool:
    """
    Strict USA-only geography gate.

    Follows 7 ordered steps; returns False when in doubt.

    Args:
        location:  Raw location string from the job listing.
        work_mode: Optional work-mode hint ("remote", "hybrid", "onsite", …).
    """
    loc = location.strip()
    loc_lower = loc.lower()

    # Remote signal: detected from work_mode arg OR "remote" keyword in string
    is_remote = work_mode.lower() == "remote" or "remote" in loc_lower

    # ------------------------------------------------------------------
    # STEP 1 — IMMEDIATE REJECT
    # Any non-USA country, Canadian province, or global/regional term.
    # Uses word boundaries to avoid false matches (e.g. "india" ≠ "Indianapolis").
    # ------------------------------------------------------------------
    if _STEP1_RE.search(loc_lower):
        return False

    # ------------------------------------------------------------------
    # STEP 2 — IMMEDIATE ACCEPT
    # Explicit "United States", "USA", US-Remote variants, ZIP codes.
    # ------------------------------------------------------------------
    for phrase in _ACCEPT_PHRASES:
        if phrase in loc_lower:
            return True
    if _ZIP_RE.search(loc):
        return True

    # ------------------------------------------------------------------
    # STEP 3 — Full US state name present
    # ------------------------------------------------------------------
    for state_name in _US_STATE_NAMES:
        if state_name in loc_lower:
            return True

    # ------------------------------------------------------------------
    # STEP 4 — Major US city or US region present
    # ------------------------------------------------------------------
    for city in _US_CITIES:
        if city in loc_lower:
            return True

    # ------------------------------------------------------------------
    # STEP 5 — State abbreviation in address context
    # Safe abbreviations are accepted directly.
    # Collision abbreviations (IN, OR, PA, …) require a known US city.
    # ------------------------------------------------------------------
    if _SAFE_ABBR_RE.search(loc):
        return True
    if _COLLISION_ABBR_RE.search(loc):
        for city in _US_CITIES:
            if city in loc_lower:
                return True

    # ------------------------------------------------------------------
    # STEP 6 — Remote special rule
    # Remote with no non-USA country (already cleared Step 1) → True.
    # Blank location (no signal at all) → True.
    # ------------------------------------------------------------------
    if is_remote or not loc:
        return True

    # ------------------------------------------------------------------
    # STEP 7 — Everything else → False
    # ------------------------------------------------------------------
    return False
