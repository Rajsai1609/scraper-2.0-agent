#!/usr/bin/env python3
"""
Process DOL LCA xlsx -> aggregate employer stats -> upsert to h1b_employers.

Env vars required (both must be set):
    SUPABASE_URL
    SUPABASE_SERVICE_KEY

Flags:
    --dry-run   Load and aggregate the xlsx, print row count, skip Supabase write.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

XLSX_PATH   = Path("data/h1b_lca_2024.xlsx")
BATCH_SIZE  = 500
BATCH_DELAY = 0.3
DRY_RUN     = "--dry-run" in sys.argv

_REQUIRED_OUTPUT_COLS = {
    "employer_name", "h1b_count", "approval_rate",
    "avg_salary", "job_titles", "visa_score",
}

_EMPLOYER_HINTS = ["employer_name", "employer", "company"]
_STATUS_HINTS   = ["case_status", "status"]
_WAGE_HINTS     = ["wage_rate_of_pay_from", "wage_from", "prevailing_wage", "wage"]
_TITLE_HINTS    = ["job_title", "soc_title", "title"]


def _find_col(cols: list[str], hints: list[str]) -> str | None:
    lower = [c.lower() for c in cols]
    for hint in hints:
        for i, c in enumerate(lower):
            if hint in c:
                return cols[i]
    return None


def _compute_visa_score(h1b_count: int, approval_rate: float) -> int:
    count_score    = min(h1b_count, 500) / 500 * 40
    approval_score = (approval_rate / 100) * 40
    presence_score = min(h1b_count, 50) / 50 * 20
    return int(round(count_score + approval_score + presence_score))


def _check_credentials() -> None:
    """Fail loudly naming whichever credential is missing."""
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_SERVICE_KEY")
    if missing:
        print(
            f"ERROR: Missing required env var(s): {', '.join(missing)}\n"
            "Both SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.",
            file=sys.stderr,
        )
        sys.exit(1)


def load_and_aggregate(xlsx_path: Path) -> pd.DataFrame:
    print(f"Reading {xlsx_path} ...")
    df = pd.read_excel(xlsx_path, sheet_name=0, engine="openpyxl")
    cols = list(df.columns)
    print(f"  {len(df):,} rows, columns: {cols[:8]}...")

    emp_col    = _find_col(cols, _EMPLOYER_HINTS)
    status_col = _find_col(cols, _STATUS_HINTS)
    wage_col   = _find_col(cols, _WAGE_HINTS)
    title_col  = _find_col(cols, _TITLE_HINTS)

    if not emp_col:
        raise ValueError(f"Could not detect employer column. Available: {cols}")

    print(f"  Detected: employer={emp_col}, status={status_col}, "
          f"wage={wage_col}, title={title_col}")

    df[emp_col] = df[emp_col].astype(str).str.strip().str.upper()
    df = df[df[emp_col].notna() & (df[emp_col] != "") & (df[emp_col] != "NAN")]

    h1b_count = df.groupby(emp_col).size().rename("h1b_count")

    if status_col:
        df["_certified"] = df[status_col].astype(str).str.upper().str.startswith("CERTIFIED")
        approval_rate = (
            df.groupby(emp_col)["_certified"].mean() * 100
        ).rename("approval_rate").round(1)
    else:
        approval_rate = pd.Series(dtype=float, name="approval_rate")

    if wage_col:
        df[wage_col] = pd.to_numeric(df[wage_col], errors="coerce")
        avg_salary = df.groupby(emp_col)[wage_col].mean().round(0).rename("avg_salary")
    else:
        avg_salary = pd.Series(dtype=float, name="avg_salary")

    if title_col:
        job_titles = (
            df.groupby(emp_col)[title_col]
            .apply(lambda x: str(list(x.dropna().unique()[:5])))
            .rename("job_titles")
        )
    else:
        job_titles = pd.Series(dtype=str, name="job_titles")

    agg = pd.DataFrame({"h1b_count": h1b_count})
    for s in [approval_rate, avg_salary, job_titles]:
        if not s.empty:
            agg = agg.join(s, how="left")

    if "approval_rate" not in agg.columns:
        agg["approval_rate"] = 100.0
    if "avg_salary" not in agg.columns:
        agg["avg_salary"] = 0.0
    if "job_titles" not in agg.columns:
        agg["job_titles"] = "[]"

    agg = agg.fillna({"approval_rate": 100.0, "avg_salary": 0.0, "job_titles": "[]"})
    agg = agg.reset_index().rename(columns={emp_col: "employer_name"})

    agg["visa_score"] = agg.apply(
        lambda r: _compute_visa_score(int(r["h1b_count"]), float(r["approval_rate"])),
        axis=1,
    )

    agg["h1b_count"]  = agg["h1b_count"].astype(int)
    agg["avg_salary"] = agg["avg_salary"].fillna(0).astype(float)
    agg["visa_score"] = agg["visa_score"].astype(int)
    agg["job_titles"] = agg["job_titles"].astype(str)

    print(f"  Aggregated {len(agg):,} unique employers")
    return agg


def _validate_schema(agg: pd.DataFrame) -> None:
    missing = _REQUIRED_OUTPUT_COLS - set(agg.columns)
    if missing:
        raise ValueError(
            f"Schema validation failed before Supabase write. "
            f"Missing columns: {sorted(missing)}"
        )


def upsert_to_supabase(agg: pd.DataFrame) -> None:
    _validate_schema(agg)

    if DRY_RUN:
        print(f"[dry-run] Would upsert {len(agg):,} rows to h1b_employers (skipping).")
        return

    _check_credentials()

    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase not installed — run: pip install supabase", file=sys.stderr)
        sys.exit(1)

    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    records = agg.to_dict("records")
    total   = len(records)
    upserted = 0

    for i in range(0, total, BATCH_SIZE):
        batch       = records[i : i + BATCH_SIZE]
        batch_num   = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        try:
            result = (
                client.table("h1b_employers")
                .upsert(batch, on_conflict="employer_name")
                .execute()
            )
            upserted += len(result.data) if result.data else len(batch)
            print(f"  Batch {batch_num}/{total_batches}: {len(batch)} rows upserted")
        except Exception as exc:
            print(f"  Batch {batch_num}/{total_batches}: ERROR — {exc}", file=sys.stderr)
            traceback.print_exc()
            sys.exit(1)

        if i + BATCH_SIZE < total:
            time.sleep(BATCH_DELAY)

    print(f"\nDone. {upserted}/{total} employer rows upserted.")


def run() -> None:
    print("=" * 60)
    print("Process H1B LCA Data -> Supabase")
    print("=" * 60)

    if not XLSX_PATH.exists():
        print(
            f"ERROR: {XLSX_PATH} not found. Run download_h1b_data.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        agg = load_and_aggregate(XLSX_PATH)
        upsert_to_supabase(agg)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run()
