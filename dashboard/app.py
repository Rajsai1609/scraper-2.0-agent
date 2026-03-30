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

st.markdown("""
<style>
/* Main background */
.stApp { background-color: #0D1117; }

/* Sidebar */
section[data-testid="stSidebar"] {
  background-color: #161B22;
  border-right: 1px solid #30363D;
}

/* Metric cards */
div[data-testid="metric-container"] {
  background-color: #161B22;
  border: 0.5px solid #30363D;
  border-radius: 8px;
  padding: 12px 16px;
}

/* All text inputs and selects */
.stSelectbox > div > div {
  background-color: #0D1117;
  border: 0.5px solid #30363D;
  color: #8B949E;
}

/* Buttons */
.stButton > button {
  background-color: #238636;
  color: #ffffff;
  border: none;
  border-radius: 6px;
}
.stButton > button:hover {
  background-color: #2EA043;
  border: none;
}

/* Divider */
hr { border-color: #30363D; }

/* Scrollbar */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #0D1117; }
::-webkit-scrollbar-thumb {
  background: #30363D;
  border-radius: 4px;
}

/* Text inputs */
.stTextInput > div > div > input {
  background-color: #0D1117;
  border: 0.5px solid #30363D;
  color: #C9D1D9;
}

/* Number input */
.stNumberInput > div > div > input {
  background-color: #0D1117;
  border: 0.5px solid #30363D;
  color: #C9D1D9;
}

/* Multiselect */
.stMultiSelect > div > div {
  background-color: #0D1117;
  border: 0.5px solid #30363D;
}
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<h1 style="color:#E6EDF3;margin-bottom:2px;">🔍 Scraper <span style="color:#58A6FF;">2.0</span> — Job Intelligence</h1>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="color:#484F58;font-size:13px;margin-top:0;">Live data from Google Sheets · auto-refreshes every 5 minutes</p>',
    unsafe_allow_html=True,
)

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
st.markdown('<hr style="border-color:#30363D;margin:16px 0;">', unsafe_allow_html=True)

# ── Result count ──────────────────────────────────────────────────────────────
total_all      = len(df)
total_filtered = len(filtered)

if total_filtered == total_all:
    st.markdown(
        f'<p style="color:#8B949E;font-size:13px;">Showing <strong style="color:#E6EDF3;">{total_filtered}</strong> jobs</p>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<p style="color:#8B949E;font-size:13px;">Showing <strong style="color:#E6EDF3;">{total_filtered}</strong> of {total_all} jobs</p>',
        unsafe_allow_html=True,
    )

# ── Paginated job cards ───────────────────────────────────────────────────────
if filtered.empty:
    st.info("No jobs match the current filters. Try broadening your search.")
else:
    PAGE_SIZE = 25
    total_pages = max(1, (total_filtered + PAGE_SIZE - 1) // PAGE_SIZE)

    if "page_idx" not in st.session_state:
        st.session_state.page_idx = 0

    # Reset to page 0 if filters changed and current page is out of range
    if st.session_state.page_idx >= total_pages:
        st.session_state.page_idx = 0

    if total_pages > 1:
        col_prev, col_info, col_next = st.columns([1, 3, 1])
        with col_prev:
            if st.button("← Previous", disabled=st.session_state.page_idx == 0):
                st.session_state.page_idx -= 1
                st.rerun()
        with col_info:
            st.markdown(
                f'<p style="color:#8B949E;text-align:center;padding-top:6px;">Page {st.session_state.page_idx + 1} of {total_pages}</p>',
                unsafe_allow_html=True,
            )
        with col_next:
            if st.button("Next →", disabled=st.session_state.page_idx >= total_pages - 1):
                st.session_state.page_idx += 1
                st.rerun()

    page_idx = st.session_state.page_idx
    start    = page_idx * PAGE_SIZE
    page_df  = filtered.iloc[start : start + PAGE_SIZE]

    for _, row in page_df.iterrows():
        render_job_card(row)

    if total_pages > 1:
        st.markdown(
            f'<p style="color:#8B949E;font-size:12px;text-align:center;">Page {page_idx + 1} of {total_pages} · {total_filtered} results</p>',
            unsafe_allow_html=True,
        )
