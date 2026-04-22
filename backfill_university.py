#!/usr/bin/env python3
"""
One-time backfill: extract university from existing students' resume_text
and UPDATE students.university for rows where it is currently NULL.

Run once after deploying the pipeline fix:
    python backfill_university.py

Required env vars:
    SUPABASE_URL
    SUPABASE_SERVICE_KEY
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def _get_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
    try:
        from supabase import create_client
    except ImportError:
        raise ImportError("supabase not installed — run: pip install supabase")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def run() -> None:
    from step1_ingest_resumes import extract_university

    client = _get_client()

    print("Fetching students with NULL university…")
    result = (
        client.table("students")
        .select("id, name, resume_text")
        .is_("university", "null")
        .execute()
    )
    students = result.data or []
    print(f"Found {len(students)} student(s) with NULL university.\n")

    if not students:
        print("Nothing to backfill. ✓")
        return

    updated = 0
    skipped = 0

    for row in students:
        sid   = row["id"]
        name  = row.get("name", "?")
        text  = row.get("resume_text") or ""

        university = extract_university(text)

        if university:
            client.table("students").update({"university": university}).eq("id", sid).execute()
            print(f"  ✅  {name:30s}  →  {university}")
            updated += 1
        else:
            print(f"  —   {name:30s}  (no match)")
            skipped += 1

    print(f"\n{'='*60}")
    print(f"Backfill complete: {updated} updated, {skipped} could not be extracted.")
    if skipped:
        print(
            f"\nNOTE: {skipped} student(s) still have NULL university.\n"
            "Their alumni tab will show empty until university is populated manually\n"
            "or their resume is re-ingested with better text quality."
        )
    pct = round(100 * updated / len(students)) if students else 0
    print(f"Fill rate: {updated}/{len(students)} ({pct}%)")
    if pct < 80:
        print("⚠  Fill rate <80% — regex may need wider patterns. Review skipped names above.")


if __name__ == "__main__":
    run()
