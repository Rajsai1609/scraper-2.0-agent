#!/usr/bin/env python3
"""
Apply step2_supabase_schema.sql to MCT-Alesia.

Usage:
    # Option A — direct Postgres (fastest)
    # Get the connection string from:
    # Supabase Dashboard → Project Settings → Database → Connection string → URI
    DATABASE_URL=postgresql://postgres:[password]@db.ubmsuuagwrozftwutdhf.supabase.co:5432/postgres \
        python apply_schema.py

    # Option B — add DATABASE_URL to .env then run
    python apply_schema.py

    # Option C — paste the SQL manually
    # Copy step2_supabase_schema.sql → Supabase Dashboard → SQL Editor → Run

Requires:
    pip install psycopg2-binary python-dotenv
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SQL_FILE = Path(__file__).parent / "step2_supabase_schema.sql"
DATABASE_URL = os.getenv("DATABASE_URL", "")


def apply(database_url: str) -> None:
    try:
        import psycopg2  # type: ignore[import]
    except ImportError:
        print("ERROR: psycopg2-binary not installed — run: pip install psycopg2-binary")
        sys.exit(1)

    sql = SQL_FILE.read_text(encoding="utf-8")

    print(f"Connecting to Supabase Postgres...")
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
    except Exception as exc:
        print(f"ERROR: Could not connect: {exc}")
        _print_manual_instructions()
        sys.exit(1)

    print(f"Applying {SQL_FILE.name} ...")
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        print("Schema applied successfully.")
    except Exception as exc:
        print(f"ERROR applying schema: {exc}")
        _print_manual_instructions()
        sys.exit(1)
    finally:
        conn.close()


def _print_manual_instructions() -> None:
    print()
    print("=" * 60)
    print("MANUAL OPTION: Paste the SQL below into Supabase SQL Editor")
    print("  https://app.supabase.com/project/ubmsuuagwrozftwutdhf/sql/new")
    print("=" * 60)
    print(SQL_FILE.read_text(encoding="utf-8"))


def main() -> None:
    if not DATABASE_URL:
        print("DATABASE_URL not set.\n")
        print("Get it from: Supabase Dashboard → Settings → Database → URI")
        print("Then run:")
        print("  DATABASE_URL='postgresql://postgres:[pw]@db.ubmsuuagwrozftwutdhf.supabase.co:5432/postgres'")
        print("  python apply_schema.py\n")
        _print_manual_instructions()
        sys.exit(1)

    apply(DATABASE_URL)


if __name__ == "__main__":
    main()
