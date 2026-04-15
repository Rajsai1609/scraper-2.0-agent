"""
Database layer — SQLite (primary) + Google Sheets (optional).

SQLite is always available. Google Sheets is used only when
config/google_credentials.json exists and gspread is installed.

Sheet layout (when Sheets is enabled):
  Jobs  — one row per job, headers in row 1
  Stats — aggregate counts, rewritten on every get_stats() call
  Logs  — append-only run log with level column
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generator, Optional

# ---------------------------------------------------------------------------
# Optional gspread — imported only if available and credentials exist
# ---------------------------------------------------------------------------

try:
    import gspread
    from google.oauth2.service_account import Credentials as _GCredentials
    _GSPREAD_AVAILABLE = True
except ImportError:
    _GSPREAD_AVAILABLE = False

from dotenv import load_dotenv

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
SQLITE_PATH: Path = Path(os.getenv("SQLITE_PATH", "data/jobs.db"))

SCOPES: list[str] = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ---------------------------------------------------------------------------
# Column definitions — order is the ground truth for Sheets serialisation
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
# Rate-limit / quota constants
# ---------------------------------------------------------------------------

_BATCH_SIZE: int = 50          # rows per append_rows call
_BATCH_DELAY_S: float = 1.0    # seconds between consecutive batch writes
_MAX_RETRIES: int = 5
_BACKOFF_BASE_S: float = 2.0   # exponential-backoff base (seconds)

# ---------------------------------------------------------------------------
# Module-level Sheets connection state
# ---------------------------------------------------------------------------

_spreadsheet: Optional[Any] = None
_client: Optional[Any] = None
_sheets_ready: bool = False

# In-memory ID cache — loaded once per process, updated on every insert
_existing_ids: set[str] = set()
_ids_loaded: bool = False

# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    id                TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    company           TEXT NOT NULL,
    ats_platform      TEXT NOT NULL,
    url               TEXT NOT NULL,
    description       TEXT DEFAULT '',
    location          TEXT DEFAULT '',
    country           TEXT,
    work_mode         TEXT DEFAULT 'unknown',
    usa_region        TEXT DEFAULT '',
    is_usa_job        INTEGER DEFAULT 0,
    experience_level  TEXT DEFAULT 'unknown',
    years_min         INTEGER,
    years_max         INTEGER,
    is_entry_eligible INTEGER DEFAULT 0,
    h1b_sponsor       INTEGER,
    opt_friendly      INTEGER,
    stem_opt_eligible INTEGER,
    visa_notes        TEXT DEFAULT '',
    skills            TEXT DEFAULT '[]',
    job_category      TEXT DEFAULT 'other',
    fit_score         REAL,
    date_posted       TEXT,
    fetched_at        TEXT NOT NULL,
    expires_at        TEXT NOT NULL
)
"""


def init_db() -> None:
    """Create the SQLite database and jobs table if they don't exist.

    Safe to call multiple times — idempotent.
    The data/ directory is created automatically if absent.
    """
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SQLITE_PATH) as conn:
        conn.execute(_SQLITE_DDL)
        conn.commit()


@contextmanager
def _db_conn() -> Generator[sqlite3.Connection, None, None]:
    """Yield a SQLite connection with row_factory set."""
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def save_job(job: Job) -> bool:
    """Insert job into SQLite.  Returns True if inserted, False if duplicate."""
    row = (
        job.id,
        job.title,
        job.company,
        job.ats_platform,
        job.url,
        job.description,
        job.location,
        job.country,
        job.work_mode.value,
        job.usa_region,
        int(job.is_usa_job),
        job.experience_level.value,
        job.years_min,
        job.years_max,
        int(job.is_entry_eligible),
        None if job.h1b_sponsor is None else int(job.h1b_sponsor),
        None if job.opt_friendly is None else int(job.opt_friendly),
        None if job.stem_opt_eligible is None else int(job.stem_opt_eligible),
        job.visa_notes,
        json.dumps(job.skills),
        job.job_category.value,
        job.fit_score,
        job.date_posted.isoformat() if job.date_posted else None,
        job.fetched_at.isoformat(),
        job.expires_at.isoformat(),
    )
    with _db_conn() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO jobs (
                id, title, company, ats_platform, url, description,
                location, country, work_mode, usa_region, is_usa_job,
                experience_level, years_min, years_max, is_entry_eligible,
                h1b_sponsor, opt_friendly, stem_opt_eligible, visa_notes,
                skills, job_category, fit_score,
                date_posted, fetched_at, expires_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            row,
        )
        conn.commit()
        return cursor.rowcount > 0


def save_jobs_batch(jobs: list[Job]) -> tuple[int, int]:
    """Insert all jobs not already in SQLite.  Returns (inserted, skipped)."""
    inserted = skipped = 0
    for job in jobs:
        if save_job(job):
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


def job_exists_sqlite(job_id: str) -> bool:
    """Return True if the job_id is already in the SQLite database."""
    with _db_conn() as conn:
        row = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return row is not None


def get_jobs(filters: Optional[dict] = None) -> list[Job]:
    """
    Read jobs from SQLite, deserialise to Job objects, apply in-memory filters.

    Supported filter keys match the Sheets version:
      work_mode, usa_region, experience_level, is_entry_eligible,
      h1b_sponsor, opt_friendly, stem_opt_eligible, job_category,
      min_score, max_years, is_usa_job
    """
    with _db_conn() as conn:
        rows = conn.execute("SELECT * FROM jobs").fetchall()

    jobs: list[Job] = []
    for row in rows:
        try:
            jobs.append(_sqlite_row_to_job(row))
        except Exception:
            continue

    return _apply_filters(jobs, filters or {})


def _sqlite_row_to_job(row: sqlite3.Row) -> Job:
    def _opt_bool(v: Optional[int]) -> Optional[bool]:
        return None if v is None else bool(v)

    def _opt_dt(v: Optional[str]) -> Optional[datetime]:
        return datetime.fromisoformat(v) if v else None

    def _enum(cls, v: str, default):
        try:
            return cls(v) if v else default
        except ValueError:
            return default

    return Job(
        id=row["id"],
        title=row["title"],
        company=row["company"],
        ats_platform=row["ats_platform"],
        url=row["url"],
        description=row["description"] or "",
        location=row["location"] or "",
        country=row["country"],
        work_mode=_enum(WorkMode, row["work_mode"], WorkMode.UNKNOWN),
        usa_region=row["usa_region"] or "",
        is_usa_job=bool(row["is_usa_job"]),
        experience_level=_enum(ExperienceLevel, row["experience_level"], ExperienceLevel.UNKNOWN),
        years_min=row["years_min"],
        years_max=row["years_max"],
        is_entry_eligible=bool(row["is_entry_eligible"]),
        h1b_sponsor=_opt_bool(row["h1b_sponsor"]),
        opt_friendly=_opt_bool(row["opt_friendly"]),
        stem_opt_eligible=_opt_bool(row["stem_opt_eligible"]),
        visa_notes=row["visa_notes"] or "",
        skills=json.loads(row["skills"] or "[]"),
        job_category=_enum(JobCategory, row["job_category"], JobCategory.OTHER),
        fit_score=row["fit_score"],
        date_posted=_opt_dt(row["date_posted"]),
        fetched_at=datetime.fromisoformat(row["fetched_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
    )


# ---------------------------------------------------------------------------
# Google Sheets connection helpers
# ---------------------------------------------------------------------------

def _sheets_configured() -> bool:
    """Return True if gspread is installed and credentials file exists."""
    return _GSPREAD_AVAILABLE and CREDS_PATH.exists()


def _build_client() -> Any:
    creds = _GCredentials.from_service_account_file(str(CREDS_PATH), scopes=SCOPES)
    return gspread.authorize(creds)


def init_sheets() -> None:
    """
    Authenticate with the service account, open (or create) the spreadsheet,
    and ensure all three worksheets exist with correct headers.

    If gspread is not installed or credentials file is missing, prints a
    notice and returns silently — does NOT raise.

    Safe to call multiple times — idempotent.
    """
    global _spreadsheet, _client, _sheets_ready

    if not _sheets_configured():
        print("Google Sheets not configured, using SQLite only")
        return

    _client = _build_client()

    try:
        _spreadsheet = _client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        _spreadsheet = _client.create(SPREADSHEET_NAME)

    _ensure_worksheet("Jobs", JOBS_HEADERS)
    _ensure_worksheet("Stats", STATS_HEADERS)
    _ensure_worksheet("Logs", LOGS_HEADERS)
    _sheets_ready = True


def _get_spreadsheet() -> Any:
    if _spreadsheet is None:
        raise RuntimeError("Sheets not initialised — call init_sheets() first.")
    return _spreadsheet


def _get_worksheet(name: str) -> Any:
    """
    Return the named worksheet, transparently reconnecting if the OAuth
    session has expired (HTTP 401 from the Sheets API).
    """
    global _spreadsheet, _client

    try:
        return _get_spreadsheet().worksheet(name)
    except gspread.exceptions.APIError as exc:
        if exc.response.status_code == 401:
            _client = _build_client()
            _spreadsheet = _client.open(SPREADSHEET_NAME)
            return _spreadsheet.worksheet(name)
        raise


def _sheets_write(fn: Callable[[], Any]) -> Any:
    """
    Execute a Sheets write callable with exponential backoff on quota errors.

    Retries up to _MAX_RETRIES times when a 429 / Quota-Exceeded / RESOURCE_EXHAUSTED
    error is returned by the API.  Delays double on each attempt, starting at
    _BACKOFF_BASE_S seconds.  All other errors are re-raised immediately.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            return fn()
        except Exception as exc:
            err = str(exc)
            is_quota = "429" in err or "Quota" in err or "RESOURCE_EXHAUSTED" in err
            if is_quota and attempt < _MAX_RETRIES - 1:
                delay = _BACKOFF_BASE_S ** (attempt + 1)
                time.sleep(delay)
            else:
                raise


def _ensure_worksheet(name: str, headers: list[str]) -> None:
    """Create the worksheet if absent; write headers only when row 1 is empty."""
    sheet = _get_spreadsheet()
    try:
        ws = sheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=name, rows=1000, cols=max(len(headers), 3))

    if not ws.row_values(1):
        _sheets_write(lambda: ws.append_row(headers, value_input_option="RAW"))


def _load_existing_ids() -> set[str]:
    """Load all job IDs from the sheet into memory exactly once per process."""
    global _existing_ids, _ids_loaded
    if _ids_loaded:
        return _existing_ids
    all_ids = _get_worksheet("Jobs").col_values(_ID_COL)
    _existing_ids = set(all_ids[1:])  # skip header row
    _ids_loaded = True
    return _existing_ids


# ---------------------------------------------------------------------------
# Sheets serialisation helpers
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
# Sheets public API (unchanged — guarded by _sheets_ready where needed)
# ---------------------------------------------------------------------------

def job_exists(job_id: str) -> bool:
    """Return True if job_id is in the Jobs sheet (uses in-memory cache)."""
    return job_id in _load_existing_ids()


def insert_job(job: Job) -> bool:
    """
    Append job as a new row in Sheets.  Returns True if inserted, False if
    skipped because the id was already present.  Uses exponential backoff on 429.
    """
    if job_exists(job.id):
        return False
    ws = _get_worksheet("Jobs")
    row = _job_to_row(job)
    _sheets_write(lambda: ws.append_row(row, value_input_option="RAW"))
    _existing_ids.add(job.id)
    return True


def batch_insert_jobs(jobs: list[Job]) -> tuple[int, int]:
    """
    Insert all jobs that are not already in the sheet.
    Uses the in-memory ID cache — no extra col_values() call.
    Writes in batches of _BATCH_SIZE with _BATCH_DELAY_S between batches.
    Returns (inserted_count, skipped_count).
    """
    existing = _load_existing_ids()
    new_jobs = [j for j in jobs if j.id not in existing]
    skipped = len(jobs) - len(new_jobs)

    if not new_jobs:
        return 0, skipped

    ws = _get_worksheet("Jobs")
    rows = [_job_to_row(j) for j in new_jobs]

    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i:i + _BATCH_SIZE]
        _sheets_write(lambda b=batch: ws.append_rows(b, value_input_option="RAW"))
        for j in new_jobs[i:i + _BATCH_SIZE]:
            _existing_ids.add(j.id)
        if i + _BATCH_SIZE < len(rows):
            time.sleep(_BATCH_DELAY_S)

    return len(new_jobs), skipped


def insert_jobs_batch(jobs: list[Job]) -> int:
    """
    Insert new jobs in batches of _BATCH_SIZE rows with _BATCH_DELAY_S pause
    between batches to stay under the Sheets write-quota.  Uses exponential
    backoff on 429 errors.  Uses the in-memory ID cache — no col_values()
    call is made.  Returns the number of rows inserted.
    """
    existing = _load_existing_ids()
    new_jobs = [j for j in jobs if j.id not in existing]
    if not new_jobs:
        return 0

    ws = _get_worksheet("Jobs")
    rows = [_job_to_row(j) for j in new_jobs]

    inserted = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i:i + _BATCH_SIZE]
        _sheets_write(lambda b=batch: ws.append_rows(b, value_input_option="RAW"))
        for j in new_jobs[i:i + _BATCH_SIZE]:
            _existing_ids.add(j.id)
        inserted += len(batch)
        if i + _BATCH_SIZE < len(rows):
            time.sleep(_BATCH_DELAY_S)

    return inserted


def update_job(job_id: str, updates: dict[str, Any]) -> bool:
    """
    Update specific columns of an existing job row in Sheets by id.
    Returns True if the row was found and updated, False otherwise.
    """
    ws = _get_worksheet("Jobs")
    ids = ws.col_values(_ID_COL)
    data_ids = ids[1:]
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
        _sheets_write(lambda: ws.update_cells(cells, value_input_option="RAW"))
    return True


def replace_all_jobs(jobs: list[Job]) -> None:
    """Overwrite every data row in the Jobs sheet with the supplied jobs list."""
    ws = _get_worksheet("Jobs")
    _sheets_write(lambda: ws.clear())
    time.sleep(_BATCH_DELAY_S)
    all_rows: list[list[Any]] = [JOBS_HEADERS] + [_job_to_row(j) for j in jobs]
    for i in range(0, len(all_rows), _BATCH_SIZE):
        batch = all_rows[i:i + _BATCH_SIZE]
        _sheets_write(lambda b=batch: ws.append_rows(b, value_input_option="RAW"))
        if i + _BATCH_SIZE < len(all_rows):
            time.sleep(_BATCH_DELAY_S)


def get_jobs_from_sheets(filters: Optional[dict] = None) -> list[Job]:
    """Read every data row from the Jobs sheet and apply in-memory filters."""
    rows = _get_worksheet("Jobs").get_all_values()
    if len(rows) <= 1:
        return []

    jobs: list[Job] = []
    for row in rows[1:]:
        try:
            jobs.append(_row_to_job(row))
        except Exception:
            continue

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
    Delete rows in Jobs sheet where expires_at < now (UTC).
    Returns the number of rows deleted.
    """
    ws = _get_worksheet("Jobs")
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return 0

    now = datetime.now(tz=timezone.utc)
    exp_idx = JOBS_HEADERS.index("expires_at")
    expired: list[int] = []

    for sheet_row, row in enumerate(rows[1:], start=2):
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
    Aggregate counts from all jobs in SQLite (or Sheets if active).
    When Sheets is active, also writes the breakdown to the Stats sheet.
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
        "by_company":      dict(company_counter.most_common(20)),
        "by_ats_platform": dict(ats_counter.most_common()),
        "by_usa_region":   dict(region_counter.most_common()),
        "by_job_category": dict(category_counter.most_common()),
        "last_updated":    datetime.now(tz=timezone.utc).isoformat(),
    }

    if _sheets_ready:
        _write_stats(stats)
    return stats


def _write_stats(stats: dict[str, Any]) -> None:
    """Overwrite the Stats sheet with the current aggregate data."""
    ws = _get_worksheet("Stats")
    _sheets_write(lambda: ws.clear())
    time.sleep(_BATCH_DELAY_S)

    def section(label: str, data: dict[str, Any]) -> list[list[str]]:
        return [
            ["", ""],
            [f"--- {label} ---", ""],
            *[[k, str(v)] for k, v in data.items()],
        ]

    rows: list[list[str]] = [
        STATS_HEADERS,
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

    _sheets_write(lambda: ws.append_rows(rows, value_input_option="RAW"))


def update_fit_scores(jobs: list[Job]) -> int:
    """Update the fit_score column in SQLite for each job by id.

    Returns the number of rows updated.
    """
    updated = 0
    with _db_conn() as conn:
        for job in jobs:
            cursor = conn.execute(
                "UPDATE jobs SET fit_score = ? WHERE id = ?",
                (job.fit_score, job.id),
            )
            updated += cursor.rowcount
        conn.commit()
    return updated


def log_run(message: str, level: str = "INFO") -> None:
    """Log a timestamped run event to stdout (and Sheets when active).

    Args:
        message: Human-readable description of the event.
        level:   Severity label — INFO, WARNING, ERROR, DEBUG.
    """
    ts = datetime.now(tz=timezone.utc).isoformat()
    print(f"[{ts}] {level.upper()} {message}")

    if _sheets_ready:
        row = [ts, level.upper(), message]
        ws = _get_worksheet("Logs")
        _sheets_write(lambda: ws.append_row(row, value_input_option="RAW"))
