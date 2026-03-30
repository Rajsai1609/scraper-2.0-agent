"""
Scraper 2.0 — Job Intelligence Dashboard
Live Google Sheets view with sidebar filters, metric summary, and paginated job cards.

Run:
    cd scraper-2.0
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from components.job_card import render_job_card
from components.sidebar import render_sidebar
from components.stats_bar import render_stats
from sheets_reader import load_jobs

st.set_page_config(
    page_title="Scraper 2.0 — Job Intelligence",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🔍 Job Intelligence Dashboard")
st.caption("Live data from Google Sheets · auto-refreshes every 5 minutes")

# ── Load data ─────────────────────────────────────────────────────────────────
try:
    df = load_jobs()
except Exception as exc:
    st.error(f"**Could not connect to Google Sheets:** {exc}")
    st.info(
        "Set `GOOGLE_CREDENTIALS_PATH` (path to service-account JSON) or "
        "`GOOGLE_CREDENTIALS_JSON` (raw JSON string) in your environment, "
        "then restart the app."
    )
    st.stop()

if df.empty:
    st.warning("No jobs in the sheet yet. Run the scraper to populate it.")
    st.stop()

# ── Sidebar filters ───────────────────────────────────────────────────────────
filters = render_sidebar(df)

# ── Apply filters ─────────────────────────────────────────────────────────────
filtered = df.copy()

if "search" in filters:
    q = filters["search"].lower()
    mask = (
        filtered["title"].str.lower().str.contains(q, na=False)
        | filtered["company"].str.lower().str.contains(q, na=False)
    )
    filtered = filtered[mask]

if "work_mode" in filters:
    filtered = filtered[filtered["work_mode"].isin(filters["work_mode"])]

if "experience_level" in filters:
    filtered = filtered[filtered["experience_level"].isin(filters["experience_level"])]

if "job_category" in filters:
    filtered = filtered[filtered["job_category"].isin(filters["job_category"])]

if "usa_region" in filters:
    filtered = filtered[filtered["usa_region"].isin(filters["usa_region"])]

if filters.get("h1b_sponsor"):
    filtered = filtered[filtered["h1b_sponsor"] == True]

if filters.get("opt_friendly"):
    filtered = filtered[filtered["opt_friendly"] == True]

if filters.get("stem_opt_eligible"):
    filtered = filtered[filtered["stem_opt_eligible"] == True]

if filters.get("is_entry_eligible"):
    filtered = filtered[filtered["is_entry_eligible"] == True]

if "max_years" in filters:
    mx = filters["max_years"]
    filtered = filtered[filtered["years_min"].isna() | (filtered["years_min"] <= mx)]

if "min_score" in filters:
    filtered = filtered[
        filtered["fit_score"].notna() & (filtered["fit_score"] >= filters["min_score"])
    ]

# Newest first
filtered = filtered.sort_values(
    ["date_posted", "fetched_at"], ascending=False, na_position="last"
)
filtered = filtered.reset_index(drop=True)

# ── Stats row ─────────────────────────────────────────────────────────────────
render_stats(filtered)
st.divider()

# ── Result count ──────────────────────────────────────────────────────────────
total_all      = len(df)
total_filtered = len(filtered)

if total_filtered == total_all:
    st.markdown(f"Showing **{total_filtered}** jobs")
else:
    st.markdown(f"Showing **{total_filtered}** of {total_all} jobs")

# ── Paginated job cards ───────────────────────────────────────────────────────
if filtered.empty:
    st.info("No jobs match the current filters. Try broadening your search.")
else:
    PAGE_SIZE = 25
    total_pages = max(1, (total_filtered + PAGE_SIZE - 1) // PAGE_SIZE)

    if total_pages > 1:
        col_left, col_mid, col_right = st.columns([1, 2, 1])
        with col_mid:
            page_num = st.number_input(
                f"Page (1–{total_pages})",
                min_value=1,
                max_value=total_pages,
                value=1,
                step=1,
            )
        page_idx = page_num - 1
    else:
        page_idx = 0

    start   = page_idx * PAGE_SIZE
    page_df = filtered.iloc[start : start + PAGE_SIZE]

    for _, row in page_df.iterrows():
        render_job_card(row)

    if total_pages > 1:
        st.caption(f"Page {page_idx + 1} of {total_pages} · {total_filtered} results")
