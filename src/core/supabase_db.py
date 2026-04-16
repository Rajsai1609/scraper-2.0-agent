"""
Low-level Supabase writer for scraped jobs.

Accepts plain dicts that match the scraped_jobs table schema.
Uses SUPABASE_SERVICE_KEY (service role — bypasses RLS for writes).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

_BATCH_SIZE = 500  # rows per upsert call


def get_supabase():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    from supabase import create_client
    return create_client(url, key)


def upsert_jobs_to_supabase(jobs: list[dict]) -> None:
    """Upsert job dicts into the scraped_jobs table in batches of 500."""
    if not jobs:
        return

    client = get_supabase()
    if client is None:
        print("[supabase_db] SUPABASE_URL / SUPABASE_SERVICE_KEY not set — skipping.")
        return

    for i in range(0, len(jobs), _BATCH_SIZE):
        batch = jobs[i : i + _BATCH_SIZE]
        client.table("scraped_jobs").upsert(batch, on_conflict="id").execute()

    print(f"[supabase_db] Upserted {len(jobs)} jobs to Supabase")
