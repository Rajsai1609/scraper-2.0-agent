"""
Bridge Layer: scraper-2.0-agent → ai-carrer-ops
Reads qualified jobs from data/jobs.db and writes pipeline.md
to the sibling ai-carrer-ops repo.
"""

import sqlite3
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

DB_PATH = Path(__file__).parent.parent / "data" / "jobs.db"
TARGET_REPO = Path(__file__).parent.parent.parent / "ai-carrer-ops"
TARGET_DIR = TARGET_REPO / "data"
TARGET_FILE = TARGET_DIR / "pipeline.md"
SUMMARY_FILE = Path(__file__).parent / "last_run.json"

SCORE_THRESHOLD = 0.4


def get_columns(cursor, table: str) -> list[str]:
    cursor.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def build_query(columns: list[str]) -> tuple[str, bool]:
    """Build the SELECT query, optionally filtering on visa_sponsorship_flag."""
    has_visa_flag = "visa_sponsorship_flag" in columns

    base = """
        SELECT url, company, fit_score
        FROM jobs
        WHERE fit_score >= ?
    """

    if has_visa_flag:
        base += "  AND visa_sponsorship_flag = 0\n"

    base += "ORDER BY fit_score DESC"
    return base, has_visa_flag


def main() -> None:
    # Guard: sibling repo must exist
    if not TARGET_REPO.exists():
        print(f"ERROR: Target repo not found: {TARGET_REPO}", file=sys.stderr)
        print("Make sure ai-carrer-ops is checked out as a sibling directory.", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Total jobs in DB
    cur.execute("SELECT COUNT(*) FROM jobs")
    total_in_db: int = cur.fetchone()[0]

    columns = get_columns(cur, "jobs")
    query, has_visa_flag = build_query(columns)

    # Jobs passing score filter (before visa rejection)
    cur.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score >= ?",
        (SCORE_THRESHOLD,),
    )
    passed_score: int = cur.fetchone()[0]

    # Final filtered result set
    cur.execute(query, (SCORE_THRESHOLD,))
    rows = cur.fetchall()  # (url, company, fit_score)
    conn.close()

    urls_written = len(rows)
    visa_rejected = passed_score - urls_written if has_visa_flag else 0

    # Top 5 companies by job count in filtered results
    company_counts = Counter(row[1] for row in rows if row[1])
    top_companies = [name for name, _ in company_counts.most_common(5)]

    # Write pipeline.md
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    with open(TARGET_FILE, "w", encoding="utf-8") as f:
        for url, _company, _score in rows:
            f.write(url + "\n")

    # Write last_run.json
    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_jobs_in_db": total_in_db,
        "passed_score_filter": passed_score,
        "visa_rejected": visa_rejected,
        "urls_written": urls_written,
        "top_companies": top_companies,
    }
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Stdout summary
    companies_str = ", ".join(top_companies) if top_companies else "N/A"
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\u2705 Bridge complete")
    print(f"Total jobs in DB:             {total_in_db}")
    print(f"Passed score filter (>={SCORE_THRESHOLD}):  {passed_score}")
    print(f"Visa rejected:                {visa_rejected}")
    print(f"Written to pipeline.md:       {urls_written}")
    print(f"Top companies:                {companies_str}")


if __name__ == "__main__":
    main()
