#!/usr/bin/env python3
"""
Download DOL LCA H1B disclosure data (FY2024 Q4) to data/h1b_lca_2024.xlsx.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

DOL_URL = (
    "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/"
    "LCA_Disclosure_Data_FY2024_Q4.xlsx"
)
OUTPUT_PATH = Path("data/h1b_lca_2024.xlsx")


def download_h1b_data() -> Path:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading DOL H1B LCA data from DOL...")
    response = requests.get(DOL_URL, stream=True, timeout=120)
    response.raise_for_status()

    total = int(response.headers.get("content-length", 0))
    downloaded = 0
    with OUTPUT_PATH.open("wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)

    size_mb = downloaded / (1024 * 1024)
    print(f"Downloaded {size_mb:.1f} MB → {OUTPUT_PATH}")
    return OUTPUT_PATH


if __name__ == "__main__":
    download_h1b_data()
