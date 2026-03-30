"""
Read live data from Google Sheets and return a clean pandas DataFrame.

Credential resolution (first match wins):
  1. GOOGLE_CREDENTIALS_JSON env var — raw JSON string (ideal for Streamlit Cloud secrets)
  2. GOOGLE_CREDENTIALS_PATH env var — file path
  3. ../config/google_credentials.json  — project-root default
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import gspread
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "Scraper 2.0 - Job Intelligence")

_HERE = Path(__file__).parent
_PROJECT_ROOT = _HERE.parent
_DEFAULT_CREDS = _PROJECT_ROOT / "config" / "google_credentials.json"
CREDS_PATH = Path(os.getenv("GOOGLE_CREDENTIALS_PATH", str(_DEFAULT_CREDS)))

# Typed column sets — mirrors db.py JOBS_HEADERS
_BOOL_COLS = ["is_usa_job", "is_entry_eligible"]
_OPT_BOOL_COLS = ["h1b_sponsor", "opt_friendly", "stem_opt_eligible"]
_INT_COLS = ["years_min", "years_max"]
_FLOAT_COLS = ["fit_score"]
_DATE_COLS = ["date_posted", "fetched_at", "expires_at"]


def _build_client() -> gspread.Client:
    raw_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if raw_json:
        info = json.loads(raw_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_data(ttl=300, show_spinner="Loading jobs from Google Sheets…")
def load_jobs() -> pd.DataFrame:
    """
    Fetch all rows from the Jobs worksheet and return a typed DataFrame.
    Cached for 5 minutes. Click 'Refresh data' in the sidebar to force reload.
    """
    client = _build_client()
    ws = client.open(SPREADSHEET_NAME).worksheet("Jobs")
    rows = ws.get_all_records(default_blank="")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    for col in _BOOL_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.upper() == "TRUE"

    def _to_opt_bool(v) -> "bool | None":
        s = str(v).strip()
        if s in ("", "None", "none", "nan"):
            return None
        return s.upper() == "TRUE"

    for col in _OPT_BOOL_COLS:
        if col in df.columns:
            df[col] = df[col].apply(_to_opt_bool)

    for col in _INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in _FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in _DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    # Normalise work_mode so stats_bar comparisons ("remote", "hybrid") always match
    if "work_mode" in df.columns:
        df["work_mode"] = df["work_mode"].str.strip().str.lower()

    # Remove senior / high-experience jobs — dashboard targets 0–5 yrs entry roles
    if "experience_level" in df.columns:
        df = df[df["experience_level"].str.strip().str.lower() != "senior"]
    if "years_min" in df.columns:
        df = df[df["years_min"].isna() | (df["years_min"] <= 5)]

    if "skills" in df.columns:
        df["skills"] = df["skills"].apply(
            lambda v: json.loads(v) if isinstance(v, str) and v.startswith("[") else []
        )

    return df
