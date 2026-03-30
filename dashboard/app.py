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

# ── Founder story ─────────────────────────────────────────────────────────────
st.markdown('<hr style="border-color:#30363D;margin:32px 0 16px;">', unsafe_allow_html=True)

with st.expander("👤 About the builder", expanded=False):
    st.markdown("""
<div style="background:#161B22;border:0.5px solid #30363D;border-radius:12px;padding:28px 32px;">

  <!-- Header: avatar + name + badge -->
  <div style="display:flex;align-items:center;gap:20px;margin-bottom:20px;">
    <div style="width:64px;height:64px;border-radius:50%;flex-shrink:0;
                background:linear-gradient(135deg,#1F6FEB,#238636);
                display:flex;align-items:center;justify-content:center;
                font-size:22px;font-weight:700;color:#ffffff;letter-spacing:1px;">RS</div>
    <div>
      <div style="color:#E6EDF3;font-size:20px;font-weight:700;line-height:1.2;">Rajsai Naredla</div>
      <div style="color:#8B949E;font-size:13px;margin-top:3px;">AI Automation Engineer &amp; AI Architect</div>
      <div style="color:#8B949E;font-size:13px;">MCTechnology LLC · Seattle, WA</div>
      <div style="margin-top:8px;">
        <span style="background:#0D419D;color:#58A6FF;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:500;">
          Indian immigrant · F1/OPT survivor
        </span>
      </div>
    </div>
  </div>

  <!-- Quote -->
  <div style="border-left:3px solid #30363D;padding-left:16px;margin-bottom:24px;">
    <p style="color:#C9D1D9;font-size:14px;line-height:1.75;margin:0;font-style:italic;">
      "I came to the US as an international student.<br>
      I spent months manually checking company career<br>
      pages one by one — searching for H1B sponsors,<br>
      verifying STEM OPT eligibility, worrying about<br>
      the 60-day grace period. LinkedIn had no visa<br>
      filter. Indeed's data was wrong. No tool existed<br>
      that understood what I was going through.<br>
      So I built one."
    </p>
  </div>

  <!-- Pain point cards -->
  <div style="display:flex;gap:12px;margin-bottom:24px;">
    <div style="flex:1;background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:14px 16px;text-align:center;">
      <div style="color:#58A6FF;font-size:26px;font-weight:700;">1M+</div>
      <div style="color:#8B949E;font-size:11px;margin-top:4px;">job listings scanned with zero visa filter</div>
    </div>
    <div style="flex:1;background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:14px 16px;text-align:center;">
      <div style="color:#F85149;font-size:26px;font-weight:700;">60 days</div>
      <div style="color:#8B949E;font-size:11px;margin-top:4px;">grace period counting down after graduation</div>
    </div>
    <div style="flex:1;background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:14px 16px;text-align:center;">
      <div style="color:#3FB950;font-size:26px;font-weight:700;">0</div>
      <div style="color:#8B949E;font-size:11px;margin-top:4px;">tools that filtered by H-1B or STEM OPT — until now</div>
    </div>
  </div>

  <!-- What this tool does -->
  <div style="margin-bottom:20px;">
    <div style="color:#E6EDF3;font-size:14px;font-weight:600;margin-bottom:12px;">What this tool does</div>
    <ul style="color:#C9D1D9;font-size:13px;line-height:2;margin:0;padding-left:20px;">
      <li>Scrapes 500+ job boards daily and surfaces fresh listings automatically</li>
      <li>Flags verified H-1B sponsor history so you never apply to dead ends</li>
      <li>Detects STEM OPT eligibility based on SOC codes and employer history</li>
      <li>Scores each role 0–100 for fit so you apply smarter, not harder</li>
      <li>Filters out senior/staff roles that won't clear OPT or CPT timelines</li>
    </ul>
  </div>

  <!-- Footer -->
  <div style="border-top:0.5px solid #30363D;padding-top:14px;color:#484F58;font-size:12px;">
    Built by an immigrant who lived this problem ·
    <a href="https://www.linkedin.com/in/rajsainaredla09" target="_blank"
       style="color:#58A6FF;text-decoration:none;">linkedin.com/in/rajsainaredla09</a>
    · MCTechnology LLC · Seattle, WA
  </div>

</div>
""", unsafe_allow_html=True)
