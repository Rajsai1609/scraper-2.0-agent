#!/usr/bin/env python3
"""Delete scraped_jobs rows with fetched_at older than 30 days."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def run() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
    try:
        from supabase import create_client
    except ImportError:
        raise ImportError("supabase not installed — run: pip install supabase")

    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    print(f"Deleting scraped_jobs with fetched_at < {cutoff} ...")
    result = (
        client.table("scraped_jobs")
        .delete()
        .lt("fetched_at", cutoff)
        .execute()
    )
    deleted = len(result.data) if result.data else 0
    print(f"Deleted {deleted} old job(s).")


if __name__ == "__main__":
    run()
