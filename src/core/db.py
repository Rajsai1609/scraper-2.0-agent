"""
Google Sheets database layer — "Scraper 2.0 - Job Intelligence"

Sheet layout:
  Jobs  — one row per job, headers in row 1
  Stats — aggregate counts, rewritten on every get_stats() call
  Logs  — append-only run log with level column
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from src.core.models import (
    ExperienceLevel,
    Job,
    JobCategory,
    WorkMode,
)

# ---------------------------------------------------------------------------
# Configuration  (values come from .env, fall back to hard-coded defaults)
# ---------------------------------------------------------------------------

load_dotenv()

CREDS_PATH: Path = Path(
    os.getenv("GOOGLE_CREDENTIALS_PATH", "config/google_credentials.json")
)
SPREADSHEET_NAME: str = os.getenv(
    "SPREADSHEET_NAME", "Scraper 2.0 - Job Intelligence"
)

SCOPES: list[str] = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ---------------------------------------------------------------------------
# Column definitions — order is the ground truth for serialisation
# ---------------------------------------------------------------------------

JOBS_HEADERS: list[str] = [
    # identity
    "id", "title", "company", "ats_platform", "url", "description",
    # location
    "location", "country", "work_mode", "usa_region", "is_usa_job",
    # experience
    "experience_level", "years_min", "years_max", "is_entry_eligible",
    # visa
    "h1b_sponsor", "opt_friendly", "stem_opt_eligible", "visa_notes",
    # enrichment
    "skills", "job_category",
    # scoring
    "fit_score",
    # metadata
    "date_posted", "fetched_at", "expires_at",
]

STATS_HEADERS: list[str] = ["metric", "value"]
LOGS_HEADERS: list[str] = ["timestamp", "level", "message"]

# column A holds job ids (1-based in gspread)
_ID_COL: int = 1

# ---------------------------------------------------------------------------
# Module-level connection state
# ---------------------------------------------------------------------------

_spreadsheet: Optional[gspread.Spreadsheet] = None
_client: Optional[gspread.Client] = None


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _build_client() -> gspread.Client:
    creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=SCOPES)
    return gspread.authorize(creds)


def init_sheets() -> None:
    """
    Authenticate with the service account, open (or create) the spreadsheet,
    and ensure all three worksheets exist with correct headers.

    Safe to call multiple times — idempotent.
    """
    global _spreadsheet, _client

    _client = _build_client()

    try:
        _spreadsheet = _client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        _spreadsheet = _client.create(SPREADSHEET_NAME)

    _ensure_worksheet("Jobs", JOBS_HEADERS)
    _ensure_worksheet("Stats", STATS_HEADERS)
    _ensure_worksheet("Logs", LOGS_HEADERS)


def _get_spreadsheet() -> gspread.Spreadsheet:
    if _spreadsheet is None:
        raise RuntimeError("Sheets not initialised — call init_sheets() first.")
    return _spreadsheet


def _get_worksheet(name: str) -> gspread.Worksheet:
    """
    Return the named worksheet, transparently reconnecting if the OAuth
    session has expired (HTTP 401 from the Sheets API).
    """
    global _spreadsheet, _client

    try:
        return _get_spreadsheet().worksheet(name)
    except gspread.exceptions.APIError as exc:
        # 401 Unauthorized — token expired; rebuild client and re-open
        if exc.response.status_code == 401:
            _client = _build_client()
            _spreadsheet = _client.open(SPREADSHEET_NAME)
            return _spreadsheet.worksheet(name)
        raise


def _ensure_worksheet(name: str, headers: list[str]) -> None:
    """Create the worksheet if absent; write headers only when row 1 is empty."""
    sheet = _get_spreadsheet()
    try:
        ws = sheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=name, rows=1000, cols=max(len(headers), 3))

    if not ws.row_values(1):
        ws.append_row(headers, value_input_option="RAW")


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _bool_cell(v: bool) -> str:
    return "TRUE" if v else "FALSE"


def _opt_bool_cell(v: Optional[bool]) -> str:
    if v is None:
        return ""
    return "TRUE" if v else "FALSE"


def _job_to_row(job: Job) -> list[Any]:
    """Serialise a Job into a flat list aligned with JOBS_HEADERS."""
    return [
        # identity
        job.id,
        job.title,
        job.company,
        job.ats_platform,
        job.url,
        job.description,
        # location
        job.location,
        job.country or "",
        job.work_mode.value,
        job.usa_region,
        _bool_cell(job.is_usa_job),
        # experience
        job.experience_level.value,
        job.years_min   if job.years_min   is not None else "",
        job.years_max   if job.years_max   is not None else "",
        _bool_cell(job.is_entry_eligible),
        # visa
        _opt_bool_cell(job.h1b_sponsor),
        _opt_bool_cell(job.opt_friendly),
        _opt_bool_cell(job.stem_opt_eligible),
        job.visa_notes,
        # enrichment
        json.dumps(job.skills),
        job.job_category.value,
        # scoring
        job.fit_score if job.fit_score is not None else "",
        # metadata
        job.date_posted.isoformat() if job.date_posted else "",
        job.fetched_at.isoformat(),
        job.expires_at.isoformat(),
    ]


def _row_to_job(row: list[str]) -> Job:
    """Deserialise a flat Sheet row (aligned with JOBS_HEADERS) into a Job."""

    def _bool(v: str) -> bool:
        return v.strip().upper() == "TRUE"

    def _opt_bool(v: str) -> Optional[bool]:
        s = v.strip()
        return None if s == "" else (s.upper() == "TRUE")

    def _opt_int(v: str) -> Optional[int]:
        s = v.strip()
        return int(s) if s else None

    def _opt_float(v: str) -> Optional[float]:
        s = v.strip()
        return float(s) if s else None

    def _opt_dt(v: str) -> Optional[datetime]:
        s = v.strip()
        return datetime.fromisoformat(s) if s else None

    def _enum(cls, v: str, default):
        s = v.strip()
        try:
            return cls(s) if s else default
        except ValueError:
            return default

    # Pad short rows (trailing empty cells are sometimes dropped by gspread)
    padded = row + [""] * (len(JOBS_HEADERS) - len(row))
    col = dict(zip(JOBS_HEADERS, padded))

    return Job(
        # identity
        id=col["id"],
        title=col["title"],
        company=col["company"],
        ats_platform=col["ats_platform"],
        url=col["url"],
        description=col["description"],
        # location — all derived fields passed explicitly to suppress re-detection
        location=col["location"],
        country=col["country"] or None,
        work_mode=_enum(WorkMode, col["work_mode"], WorkMode.UNKNOWN),
        usa_region=col["usa_region"],
        is_usa_job=_bool(col["is_usa_job"]),
        # experience
        experience_level=_enum(ExperienceLevel, col["experience_level"], ExperienceLevel.UNKNOWN),
        years_min=_opt_int(col["years_min"]),
        years_max=_opt_int(col["years_max"]),
        is_entry_eligible=_bool(col["is_entry_eligible"]),
        # visa
        h1b_sponsor=_opt_bool(col["h1b_sponsor"]),
        opt_friendly=_opt_bool(col["opt_friendly"]),
        stem_opt_eligible=_opt_bool(col["stem_opt_eligible"]),
        visa_notes=col["visa_notes"],
        # enrichment
        skills=json.loads(col["skills"] or "[]"),
        job_category=_enum(JobCategory, col["job_category"], JobCategory.OTHER),
        # scoring
        fit_score=_opt_float(col["fit_score"]),
        # metadata
        date_posted=_opt_dt(col["date_posted"]),
        fetched_at=datetime.fromisoformat(col["fetched_at"]),
        expires_at=datetime.fromisoformat(col["expires_at"]),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def job_exists(job_id: str) -> bool:
    """
    Return True if job_id already exists in column A of the Jobs sheet.
    Uses a single col_values() call — no cell-by-cell scan.
    """
    ids = _get_worksheet("Jobs").col_values(_ID_COL)
    return job_id in ids[1:]  # ids[0] is the "id" header


def insert_job(job: Job) -> bool:
    """
    Append job as a new row.  Returns True if inserted, False if skipped
    because the id was already present.
    """
    if job_exists(job.id):
        return False
    _get_worksheet("Jobs").append_row(_job_to_row(job), value_input_option="RAW")
    return True


def batch_insert_jobs(jobs: list[Job]) -> tuple[int, int]:
    """
    Insert all jobs that are not already in the sheet.
    Reads existing IDs once, then appends all new rows in a single API call.
    Returns (inserted_count, skipped_count).
    """
    ws = _get_worksheet("Jobs")
    existing_ids = set(ws.col_values(_ID_COL)[1:])  # skip header

    new_rows = [_job_to_row(j) for j in jobs if j.id not in existing_ids]
    skipped = len(jobs) - len(new_rows)

    if new_rows:
        ws.append_rows(new_rows, value_input_option="RAW")

    return len(new_rows), skipped


def update_job(job_id: str, updates: dict[str, Any]) -> bool:
    """
    Update specific columns of an existing job row by id.
    Returns True if the row was found and updated, False otherwise.
    """
    ws = _get_worksheet("Jobs")
    ids = ws.col_values(_ID_COL)
    data_ids = ids[1:]  # skip header at ids[0]
    try:
        list_idx = data_ids.index(job_id)
    except ValueError:
        return False

    row_idx = list_idx + 2  # +1 skip header, +1 for 1-based

    cells = []
    for field, value in updates.items():
        if field not in JOBS_HEADERS:
            continue
        col_idx = JOBS_HEADERS.index(field) + 1
        cells.append(gspread.Cell(row_idx, col_idx, value))

    if cells:
        ws.update_cells(cells, value_input_option="RAW")
    return True


def replace_all_jobs(jobs: list[Job]) -> None:
    """Overwrite every data row in the Jobs sheet with the supplied jobs list."""
    ws = _get_worksheet("Jobs")
    ws.clear()
    rows: list[list[Any]] = [JOBS_HEADERS] + [_job_to_row(j) for j in jobs]
    ws.append_rows(rows, value_input_option="RAW")


def get_jobs(filters: Optional[dict] = None) -> list[Job]:
    """
    Read every data row from the Jobs sheet, deserialise to Job objects,
    then apply in-memory filters.

    Supported filter keys:
      work_mode        (str)   — exact WorkMode value  e.g. "remote"
      usa_region       (str)   — exact usa_region value e.g. "Northeast"
      experience_level (str)   — exact ExperienceLevel value
      is_entry_eligible (bool) — True = entry-eligible only
      h1b_sponsor      (bool)  — True = h1b_sponsor is True
      opt_friendly     (bool)  — True = opt_friendly is True
      stem_opt_eligible (bool) — True = stem_opt_eligible is True
      job_category     (str)   — exact JobCategory value e.g. "ml_ai_engineer"
      min_score        (float) — minimum fit_score; rows with no score excluded
      max_years        (int)   — years_min <= max_years (or years_min is None)
      is_usa_job       (bool)  — True = USA jobs only
    """
    rows = _get_worksheet("Jobs").get_all_values()
    if len(rows) <= 1:
        return []

    jobs: list[Job] = []
    for row in rows[1:]:
        try:
            jobs.append(_row_to_job(row))
        except Exception:
            continue  # skip malformed rows silently

    return _apply_filters(jobs, filters or {})


def _apply_filters(jobs: list[Job], filters: dict) -> list[Job]:
    result = jobs

    if (wm := filters.get("work_mode")) is not None:
        result = [j for j in result if j.work_mode.value == wm]

    if (region := filters.get("usa_region")) is not None:
        result = [j for j in result if j.usa_region == region]

    if (exp := filters.get("experience_level")) is not None:
        result = [j for j in result if j.experience_level.value == exp]

    if filters.get("is_entry_eligible") is True:
        result = [j for j in result if j.is_entry_eligible]

    if filters.get("h1b_sponsor") is True:
        result = [j for j in result if j.h1b_sponsor is True]

    if filters.get("opt_friendly") is True:
        result = [j for j in result if j.opt_friendly is True]

    if filters.get("stem_opt_eligible") is True:
        result = [j for j in result if j.stem_opt_eligible is True]

    if (cat := filters.get("job_category")) is not None:
        result = [j for j in result if j.job_category.value == cat]

    if (min_score := filters.get("min_score")) is not None:
        result = [j for j in result if j.fit_score is not None and j.fit_score >= min_score]

    if (max_years := filters.get("max_years")) is not None:
        result = [j for j in result if j.years_min is None or j.years_min <= max_years]

    if filters.get("is_usa_job") is True:
        result = [j for j in result if j.is_usa_job]

    return result


def delete_expired() -> int:
    """
    Delete rows in Jobs where expires_at < now (UTC).
    Deletes bottom-to-top so sheet row indices stay valid throughout.
    Returns the number of rows deleted.
    """
    ws = _get_worksheet("Jobs")
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return 0

    now = datetime.now(tz=timezone.utc)
    exp_idx = JOBS_HEADERS.index("expires_at")
    expired: list[int] = []

    for sheet_row, row in enumerate(rows[1:], start=2):  # row 1 is header
        padded = row + [""] * (len(JOBS_HEADERS) - len(row))
        raw = padded[exp_idx].strip()
        if not raw:
            continue
        try:
            exp_dt = datetime.fromisoformat(raw)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < now:
                expired.append(sheet_row)
        except ValueError:
            continue

    for row_num in reversed(expired):
        ws.delete_rows(row_num)

    return len(expired)


def get_stats() -> dict[str, Any]:
    """
    Aggregate counts from all jobs in the Jobs sheet.
    Writes the full breakdown to the Stats sheet and returns the dict.

    Scalar counts:
      total_jobs, remote_count, hybrid_count, onsite_count,
      new_grad_count, junior_count, h1b_sponsor_count,
      opt_friendly_count, stem_opt_count, entry_eligible_count

    Distribution counts (dicts):
      by_company (top 20 by count), by_ats_platform,
      by_usa_region, by_job_category
    """
    jobs = get_jobs()

    company_counter: Counter[str] = Counter()
    ats_counter:     Counter[str] = Counter()
    region_counter:  Counter[str] = Counter()
    category_counter: Counter[str] = Counter()

    remote_count = hybrid_count = onsite_count = 0
    new_grad_count = junior_count = 0
    h1b_count = opt_count = stem_count = entry_count = 0

    for job in jobs:
        company_counter[job.company] += 1
        ats_counter[job.ats_platform] += 1
        category_counter[job.job_category.value] += 1
        if job.usa_region:
            region_counter[job.usa_region] += 1

        match job.work_mode:
            case WorkMode.REMOTE:  remote_count += 1
            case WorkMode.HYBRID:  hybrid_count += 1
            case WorkMode.ONSITE:  onsite_count += 1

        match job.experience_level:
            case ExperienceLevel.NEW_GRAD: new_grad_count += 1
            case ExperienceLevel.JUNIOR:   junior_count   += 1

        if job.h1b_sponsor      is True: h1b_count   += 1
        if job.opt_friendly     is True: opt_count    += 1
        if job.stem_opt_eligible is True: stem_count  += 1
        if job.is_entry_eligible:         entry_count += 1

    stats: dict[str, Any] = {
        # scalars
        "total_jobs":          len(jobs),
        "remote_count":        remote_count,
        "hybrid_count":        hybrid_count,
        "onsite_count":        onsite_count,
        "new_grad_count":      new_grad_count,
        "junior_count":        junior_count,
        "h1b_sponsor_count":   h1b_count,
        "opt_friendly_count":  opt_count,
        "stem_opt_count":      stem_count,
        "entry_eligible_count": entry_count,
        # distributions
        "by_company":      dict(company_counter.most_common(20)),
        "by_ats_platform": dict(ats_counter.most_common()),
        "by_usa_region":   dict(region_counter.most_common()),
        "by_job_category": dict(category_counter.most_common()),
        "last_updated":    datetime.now(tz=timezone.utc).isoformat(),
    }

    _write_stats(stats)
    return stats


def _write_stats(stats: dict[str, Any]) -> None:
    """Overwrite the Stats sheet with the current aggregate data."""
    ws = _get_worksheet("Stats")
    ws.clear()

    def section(label: str, data: dict[str, Any]) -> list[list[str]]:
        return [
            ["", ""],
            [f"--- {label} ---", ""],
            *[[k, str(v)] for k, v in data.items()],
        ]

    rows: list[list[str]] = [
        STATS_HEADERS,
        # summary scalars
        ["total_jobs",           str(stats["total_jobs"])],
        ["remote_count",         str(stats["remote_count"])],
        ["hybrid_count",         str(stats["hybrid_count"])],
        ["onsite_count",         str(stats["onsite_count"])],
        ["new_grad_count",       str(stats["new_grad_count"])],
        ["junior_count",         str(stats["junior_count"])],
        ["h1b_sponsor_count",    str(stats["h1b_sponsor_count"])],
        ["opt_friendly_count",   str(stats["opt_friendly_count"])],
        ["stem_opt_count",       str(stats["stem_opt_count"])],
        ["entry_eligible_count", str(stats["entry_eligible_count"])],
        ["last_updated",         stats["last_updated"]],
        *section("BY COMPANY (TOP 20)",  stats["by_company"]),
        *section("BY ATS PLATFORM",      stats["by_ats_platform"]),
        *section("BY USA REGION",        stats["by_usa_region"]),
        *section("BY JOB CATEGORY",      stats["by_job_category"]),
    ]

    ws.append_rows(rows, value_input_option="RAW")


def log_run(message: str, level: str = "INFO") -> None:
    """Append a timestamped entry to the Logs sheet.

    Args:
        message: Human-readable description of the event.
        level:   Severity label — INFO, WARNING, ERROR, DEBUG.  Defaults to INFO.
    """
    _get_worksheet("Logs").append_row(
        [datetime.now(tz=timezone.utc).isoformat(), level.upper(), message],
        value_input_option="RAW",
    )
