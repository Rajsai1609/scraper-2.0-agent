#!/usr/bin/env python3
"""
Download DOL LCA H1B disclosure data to data/h1b_lca_2024.xlsx.

Fiscal year and quarter are configurable via env vars so the URL never
needs a code change at the start of each quarter:

    DOL_FY=2026 DOL_QUARTER=1 python scripts/download_h1b_data.py

Defaults to the latest confirmed-live quarter (FY2026 Q1).

Flags:
    --dry-run   Print the resolved URL and skip the actual download.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

import requests

_FY      = os.getenv("DOL_FY", "2026")
_QUARTER = os.getenv("DOL_QUARTER", "1")

_FILENAME = f"LCA_Disclosure_Data_FY{_FY}_Q{_QUARTER}.xlsx"
DOL_URL   = f"https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/{_FILENAME}"

OUTPUT_PATH = Path("data/h1b_lca_2024.xlsx")
DRY_RUN     = "--dry-run" in sys.argv


def _verify_url(url: str) -> None:
    """HEAD-check the URL and abort with a clear message if it is not 200."""
    try:
        resp = requests.head(url, timeout=30, allow_redirects=True)
    except requests.exceptions.RequestException as exc:
        print(f"ERROR: HEAD request failed for {url}: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    if resp.status_code != 200:
        print(
            f"ERROR: DOL server returned HTTP {resp.status_code} for:\n  {url}\n"
            f"Check DOL_FY={_FY} and DOL_QUARTER={_QUARTER} env vars.",
            file=sys.stderr,
        )
        sys.exit(1)


def download_h1b_data() -> Path:
    print(f"DOL source : {DOL_URL}")
    print(f"Output path: {OUTPUT_PATH}")

    _verify_url(DOL_URL)

    if DRY_RUN:
        print("[dry-run] URL verified (HTTP 200). Skipping download.")
        return OUTPUT_PATH

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("Downloading...")
    try:
        response = requests.get(DOL_URL, stream=True, timeout=120)
    except requests.exceptions.RequestException as exc:
        print(f"ERROR: Download failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

    if not response.ok:
        print(
            f"ERROR: DOL server returned HTTP {response.status_code} during download.",
            file=sys.stderr,
        )
        sys.exit(1)

    downloaded = 0
    with OUTPUT_PATH.open("wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)

    size_mb = downloaded / (1024 * 1024)
    print(f"Downloaded {size_mb:.1f} MB -> {OUTPUT_PATH}")
    return OUTPUT_PATH


if __name__ == "__main__":
    download_h1b_data()
