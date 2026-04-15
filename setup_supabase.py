#!/usr/bin/env python3
"""
Apply all pending Supabase migrations.

Usage:
    # Option A — direct Postgres connection (fastest):
    #   Get the URI from Supabase → Settings → Database → Connection string → URI
    DATABASE_URL='postgresql://postgres:[pw]@db.ubmsuuagwrozftwutdhf.supabase.co:5432/postgres' \
        python setup_supabase.py

    # Option B — add DATABASE_URL to .env then run:
    python setup_supabase.py

    # Option C — print SQL to paste manually:
    python setup_supabase.py --print-sql

Migrations are in migrations/*.sql, applied in filename order.
Safe to re-run: all statements use IF NOT EXISTS / CREATE OR REPLACE.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DATABASE_URL = os.getenv("DATABASE_URL", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
PROJECT_REF = (
    SUPABASE_URL.split("https://")[1].split(".supabase.co")[0]
    if "supabase.co" in SUPABASE_URL
    else "your-project"
)
SQL_EDITOR_URL = f"https://supabase.com/dashboard/project/{PROJECT_REF}/sql/new"


def get_migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        return []
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def apply_via_psycopg2(database_url: str) -> None:
    try:
        import psycopg2  # type: ignore[import]
    except ImportError:
        print("ERROR: psycopg2 not installed — run: pip install psycopg2-binary")
        sys.exit(1)

    print(f"Connecting to Supabase Postgres...")
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
    except Exception as exc:
        print(f"ERROR: Could not connect: {exc}")
        _print_manual_fallback()
        sys.exit(1)

    files = get_migration_files()
    if not files:
        print("No migration files found in migrations/")
        return

    for path in files:
        sql = path.read_text(encoding="utf-8")
        print(f"Applying {path.name} ...", end=" ", flush=True)
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            print("OK")
        except Exception as exc:
            print(f"ERROR: {exc}")
            conn.close()
            sys.exit(1)

    conn.close()
    print("\nAll migrations applied successfully.")


def print_sql() -> None:
    files = get_migration_files()
    if not files:
        print("No migration files found in migrations/")
        return
    print("-- " + "=" * 70)
    print("-- Paste this SQL into Supabase SQL Editor:")
    print(f"-- {SQL_EDITOR_URL}")
    print("-- " + "=" * 70)
    for path in files:
        print(f"\n-- === {path.name} ===\n")
        print(path.read_text(encoding="utf-8"))


def _print_manual_fallback() -> None:
    print()
    print("=" * 70)
    print("DATABASE_URL not set or connection failed.")
    print("Run this SQL in Supabase SQL Editor:")
    print(f"  {SQL_EDITOR_URL}")
    print("=" * 70)
    print_sql()


def main() -> None:
    if "--print-sql" in sys.argv:
        print_sql()
        return

    if not DATABASE_URL:
        print("DATABASE_URL not set.\n")
        print("To apply automatically, get the URI from:")
        print("  Supabase → Settings → Database → Connection string → URI")
        print("Then run:")
        print("  DATABASE_URL='postgresql://postgres:[pw]@db.ubmsuuagwrozftwutdhf.supabase.co:5432/postgres' python setup_supabase.py\n")
        print("Or run with --print-sql to get the SQL to paste manually:")
        print("  python setup_supabase.py --print-sql\n")
        _print_manual_fallback()
        sys.exit(1)

    apply_via_psycopg2(DATABASE_URL)


if __name__ == "__main__":
    main()
