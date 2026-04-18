#!/usr/bin/env python3
"""
Sync jobs from local SQLite (data/jobs.db) to Supabase scraped_jobs table.

Run AFTER the scraper step and BEFORE the multi-student scorer so that
student_job_scores JOIN scraped_jobs returns full job details on the dashboard.

NOTE: Supabase already has a 'jobs' table owned by ai-carrer-ops (UUID ids).
This script targets 'scraped_jobs' (TEXT SHA-256 ids) to avoid conflicts.
The student_top_jobs view joins student_job_scores.job_id -> scraped_jobs.id.

Env vars required:
    SUPABASE_URL
    SUPABASE_SERVICE_KEY

Optional:
    SQLITE_PATH   (default: data/jobs.db)
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", "data/jobs.db"))

_BATCH_SIZE = 500          # rows per upsert call (well under Supabase 1 MB limit)
_BATCH_DELAY = 0.3         # seconds between batches to avoid rate limits

_H1B_CSV = Path(__file__).parent / "data" / "h1b_employers.csv"


def _load_h1b_sponsors() -> frozenset[str]:
    """Load lowercase company names from data/h1b_employers.csv."""
    if not _H1B_CSV.exists():
        return frozenset()
    sponsors: set[str] = set()
    try:
        with _H1B_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("company_name", "").strip().lower()
                if name:
                    sponsors.add(name)
    except Exception:
        pass
    return frozenset(sponsors)


_H1B_SPONSORS: frozenset[str] = _load_h1b_sponsors()


def _resolve_h1b(company: str | None, existing: Any) -> bool | None:
    """
    Return True if company is a known H1B sponsor from the CSV.
    Falls back to the existing scraped value if company not in CSV.
    """
    if company:
        company_lower = company.strip().lower()
        if any(
            sponsor in company_lower or company_lower in sponsor
            for sponsor in _H1B_SPONSORS
        ):
            return True
    # Fall back to whatever the scraper detected
    return None if existing is None else bool(existing)


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

def load_jobs_from_sqlite() -> list[dict[str, Any]]:
    """Return all rows from the SQLite jobs table as plain dicts."""
    if not SQLITE_PATH.exists():
        raise FileNotFoundError(
            f"SQLite database not found: {SQLITE_PATH}\n"
            "Run the scraper first: python -m src.cli scrape"
        )

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE is_usa_job = 1
               OR usa_region != ''
               OR location LIKE '%USA%'
               OR location LIKE '%United States%'
               OR location LIKE '%, CA%'
               OR location LIKE '%, NY%'
               OR location LIKE '%, WA%'
               OR location LIKE '%, TX%'
               OR location LIKE '%, MA%'
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _coerce_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a raw SQLite row into a Supabase-compatible dict.

    - INTEGER booleans -> Python bool (Supabase BOOLEAN)
    - skills JSON string -> parsed list (Supabase JSONB)
    - ISO datetime strings kept as-is (Postgres accepts them)
    """
    def _opt_bool(v: Any) -> bool | None:
        return None if v is None else bool(v)

    skills_raw = row.get("skills") or "[]"
    try:
        skills = json.loads(skills_raw) if isinstance(skills_raw, str) else skills_raw
        if not isinstance(skills, list):
            skills = []
    except Exception:
        skills = []

    return {
        "id":                row["id"],
        "title":             row["title"] or "",
        "company":           row["company"] or "",
        "location":          row.get("location") or "",
        "url":               row["url"] or "",
        "work_mode":         row.get("work_mode") or "unknown",
        "usa_region":        row.get("usa_region") or "",
        "is_usa_job":        bool(row.get("is_usa_job") or 0),
        "experience_level":  row.get("experience_level") or "unknown",
        "is_entry_eligible": bool(row.get("is_entry_eligible") or 0),
        "h1b_sponsor":       _resolve_h1b(row.get("company"), row.get("h1b_sponsor")),
        "opt_friendly":      _opt_bool(row.get("opt_friendly")),
        "stem_opt_eligible": _opt_bool(row.get("stem_opt_eligible")),
        "skills":            skills,
        "job_category":      row.get("job_category") or "other",
        "date_posted":       row.get("date_posted") or None,
        "fetched_at":        datetime.now(timezone.utc).isoformat(),
        "expires_at":        row.get("expires_at") or None,
        "visa_score":        0,
        "h1b_count":         0,
    }


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------

def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.\n"
            "Add them to .env or pass them as environment variables."
        )
    try:
        from supabase import create_client  # type: ignore[import]
    except ImportError:
        raise ImportError("supabase not installed — run: pip install supabase")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upsert_batch(client, rows: list[dict[str, Any]]) -> int:
    """Upsert a batch of job rows; returns the count of rows upserted."""
    result = (
        client.table("scraped_jobs")
        .upsert(rows, on_conflict="id")
        .execute()
    )
    return len(result.data) if result.data else 0


# ---------------------------------------------------------------------------
# H1B enrichment
# ---------------------------------------------------------------------------

# Manual overrides for companies whose short names don't substring-match DOL records.
_H1B_KNOWN_MAPPINGS: dict[str, str] = {
    "CHARLES SCHWAB":  "CHARLES SCHWAB",
    "FIDELITY":        "FIDELITY INVESTMENTS",
    "GEICO":           "GOVERNMENT EMPLOYEES INS CO",
    "BOOZ ALLEN":      "BOOZ ALLEN HAMILTON",
    "EQUIFAX":         "EQUIFAX INC",
    "INTERMOUNTAIN":   "INTERMOUNTAIN HEALTH",
}


def _lookup_h1b(client, company_upper: str, cache: dict[str, dict | None]) -> dict | None:
    """
    Return the best-matching h1b_employers row for *company_upper*, or None.

    Strategy (stops at first hit):
      1. Known-mapping override → ilike on the mapped name
      2. Exact ilike on the full normalised name
      3. ilike on first two words only (handles "Charles Schwab" → "CHARLES SCHWAB & CO INC")

    Results are cached by company_upper to avoid duplicate DB calls in the same run.
    """
    if company_upper in cache:
        return cache[company_upper]

    def _query(pattern: str) -> dict | None:
        try:
            result = (
                client.table("h1b_employers")
                .select("visa_score, h1b_count")
                .ilike("employer_name", pattern)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception:
            return None

    row: dict | None = None

    # 1. Known mapping
    for prefix, mapped in _H1B_KNOWN_MAPPINGS.items():
        if company_upper.startswith(prefix):
            row = _query(f"%{mapped}%")
            if row:
                break

    # 2. Full name substring
    if not row:
        row = _query(f"%{company_upper}%")

    # 3. First two words
    if not row:
        words = company_upper.split()
        if len(words) >= 2:
            prefix_two = " ".join(words[:2])
            row = _query(f"%{prefix_two}%")

    cache[company_upper] = row
    return row


def _enrich_jobs_with_h1b(client, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Look up each job's company in h1b_employers and set visa_score/h1b_count."""
    print("Enriching jobs with H1B sponsor data...")
    cache: dict[str, dict | None] = {}
    enriched = 0

    for job in jobs:
        company = (job.get("company") or "").strip().upper()
        if not company:
            continue
        row = _lookup_h1b(client, company, cache)
        if row:
            job["visa_score"] = row["visa_score"]
            job["h1b_count"]  = row["h1b_count"]
            if row["visa_score"] >= 50:
                job["h1b_sponsor"] = True
            enriched += 1

    unique_looked_up = len(cache)
    print(f"  H1B enriched {enriched}/{len(jobs)} jobs ({unique_looked_up} unique company lookups)")
    return jobs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    print("=" * 60)
    print("MCT PathAI - Sync jobs: SQLite -> Supabase (scraped_jobs)")
    print("=" * 60)

    # 1. Load from SQLite
    print(f"\n[1/4] Loading jobs from {SQLITE_PATH} ...")
    try:
        raw_jobs = load_jobs_from_sqlite()
    except FileNotFoundError as exc:
        print(f"  ERROR: {exc}")
        sys.exit(1)

    if not raw_jobs:
        print("  No jobs found in SQLite. Run the scraper first.")
        sys.exit(0)

    print(f"  {len(raw_jobs)} jobs loaded from SQLite")

    # 2. Coerce rows
    print("\n[2/4] Preparing rows for Supabase ...")
    coerced = [_coerce_row(r) for r in raw_jobs]
    print(f"  {len(coerced)} rows ready")

    # 3. Connect to Supabase (reused for enrichment + upsert)
    print("\n[3/4] Connecting to Supabase ...")
    client = _get_supabase()

    # 2b. Enrich with H1B data
    coerced = _enrich_jobs_with_h1b(client, coerced)

    # 4. Upsert in batches
    print("\n[4/4] Upserting to Supabase jobs table ...")
    total_upserted = 0

    for i in range(0, len(coerced), _BATCH_SIZE):
        batch = coerced[i : i + _BATCH_SIZE]
        batch_num = i // _BATCH_SIZE + 1
        total_batches = (len(coerced) + _BATCH_SIZE - 1) // _BATCH_SIZE

        try:
            upserted = upsert_batch(client, batch)
            total_upserted += upserted
            print(f"  Batch {batch_num}/{total_batches}: {upserted} rows upserted")
        except Exception as exc:
            print(f"  Batch {batch_num}/{total_batches}: ERROR — {exc}")
            # Continue with remaining batches rather than aborting
            continue

        if i + _BATCH_SIZE < len(coerced):
            time.sleep(_BATCH_DELAY)

    print(f"\n{'=' * 60}")
    print(f"Done. {total_upserted} / {len(coerced)} rows upserted to Supabase scraped_jobs table.")


if __name__ == "__main__":
    run()
