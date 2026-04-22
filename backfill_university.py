#!/usr/bin/env python3
"""
Backfill: extract university from existing students' resume_text
and UPDATE students.university for rows where it is currently NULL.

Usage:
    python backfill_university.py              # process only-NULL rows (default)
    python backfill_university.py --all        # re-run on every student row
    python backfill_university.py --only-null  # explicit alias for default

Required env vars:
    SUPABASE_URL
    SUPABASE_SERVICE_KEY
"""
from __future__ import annotations

import argparse
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


def run(*, only_null: bool = True) -> None:
    from step1_ingest_resumes import extract_university

    client = _get_client()

    if only_null:
        print("Fetching students with NULL university...")
        result = (
            client.table("students")
            .select("id, name, resume_text")
            .is_("university", "null")
            .execute()
        )
    else:
        print("Fetching ALL students (--all mode)...")
        result = (
            client.table("students")
            .select("id, name, resume_text")
            .execute()
        )

    students = result.data or []
    label = "NULL" if only_null else "total"
    print(f"Found {len(students)} student(s) ({label}).\n")

    if not students:
        print("Nothing to backfill. Done.")
        return

    updated = 0
    skipped = 0
    misses: list[tuple[str, int]] = []  # (name, text_len)

    for row in students:
        sid   = row["id"]
        name  = row.get("name", "?")
        text  = row.get("resume_text") or ""

        university = extract_university(text)

        if university:
            client.table("students").update({"university": university}).eq("id", sid).execute()
            print(f"  [OK] {name:30s}  ->  {university}")
            updated += 1
        else:
            text_len = len(text)
            print(f"  [--] {name:30s}  [resume_text length={text_len}]  (no match)")
            skipped += 1
            misses.append((name, text_len))

    print(f"\n{'='*60}")
    print(f"Backfill complete: {updated} updated, {skipped} could not be extracted.")

    if misses:
        print(f"\nMiss summary ({len(misses)} rows):")
        empty = [(n, l) for n, l in misses if l < 50]
        sparse = [(n, l) for n, l in misses if 50 <= l < 500]
        normal = [(n, l) for n, l in misses if l >= 500]
        if empty:
            print(f"  * {len(empty)} likely empty/corrupt (text_len < 50) - manual entry needed:")
            for n, l in empty:
                print(f"      {n}  [len={l}]")
        if sparse:
            print(f"  * {len(sparse)} sparse text (50-499 chars) - may need Claude API extraction:")
            for n, l in sparse:
                print(f"      {n}  [len={l}]")
        if normal:
            print(f"  * {len(normal)} normal-length text - regex may still be too narrow:")
            for n, l in normal:
                print(f"      {n}  [len={l}]")
        print(
            "\nNOTE: students above still have NULL university.\n"
            "Their alumni tab will show empty until university is populated manually\n"
            "or their resume is re-ingested with better text quality."
        )

    pct = round(100 * updated / len(students)) if students else 0
    print(f"\nFill rate: {updated}/{len(students)} ({pct}%)")
    if pct >= 90:
        print("[OK] >=90% fill rate achieved - ready to ship.")
    elif pct >= 80:
        print("[!!] 80-89% fill rate - consider Claude API extraction for stubborn cases.")
    else:
        print("[!!] Fill rate <80% - regex may need wider patterns. Review misses above.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill university for students with NULL.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--only-null",
        action="store_true",
        default=True,
        help="Process only students with NULL university (default).",
    )
    group.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Re-run extraction on ALL students regardless of current university value.",
    )
    args = parser.parse_args()
    run(only_null=not args.all)
