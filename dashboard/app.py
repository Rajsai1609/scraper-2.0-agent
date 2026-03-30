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

# ── Founder story ─────────────────────────────────────────────────────────────
with st.expander("👤 About the builder", expanded=False):
    st.markdown("""
<div style="background:#161B22;border:0.5px solid #30363D;border-radius:12px;padding:28px 32px;">

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

  <div style="border-top:0.5px solid #30363D;padding-top:14px;color:#484F58;font-size:12px;">
    Built by an immigrant who lived this problem ·
    <a href="https://www.linkedin.com/in/rajsainaredla09" target="_blank"
       style="color:#58A6FF;text-decoration:none;">linkedin.com/in/rajsainaredla09</a>
    · MCTechnology LLC · Seattle, WA
  </div>

</div>
""", unsafe_allow_html=True)

# ── How this tool gets you jobs ───────────────────────────────────────────────
if "show_why" not in st.session_state:
    st.session_state.show_why = False

_why_label = "How this works ▲" if st.session_state.show_why else "How this works ▼"
if st.button(_why_label, key="toggle_why"):
    st.session_state.show_why = not st.session_state.show_why
    st.rerun()

if st.session_state.show_why:
    st.markdown("""
<div style="background:#161B22;border:0.5px solid #30363D;border-radius:12px;padding:28px 32px;margin-top:4px;">

  <!-- Section header -->
  <div style="margin-bottom:6px;">
    <div style="color:#E6EDF3;font-size:20px;font-weight:700;">How this tool gets you jobs</div>
    <div style="color:#8B949E;font-size:13px;margin-top:4px;">
      No tech talk. Just what this does for you every single day.
    </div>
  </div>

  <hr style="border-color:#30363D;margin:18px 0;">

  <!-- Part 1: 3 step cards -->
  <div style="color:#8B949E;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px;">How it works — 3 steps</div>
  <div style="display:flex;gap:12px;margin-bottom:28px;">

    <div style="flex:1;background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:18px 16px;">
      <div style="color:#484F58;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Step 1 — Every morning</div>
      <div style="color:#58A6FF;font-size:14px;font-weight:600;margin-bottom:8px;">Fresh jobs land in your feed</div>
      <div style="color:#8B949E;font-size:13px;line-height:1.6;">
        Every day at 7AM this tool visits the career pages of 20+ top companies and pulls
        their latest job openings. You wake up to a fresh list — no manual searching required.
      </div>
    </div>

    <div style="flex:1;background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:18px 16px;">
      <div style="color:#484F58;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Step 2 — Instantly filtered</div>
      <div style="color:#3FB950;font-size:14px;font-weight:600;margin-bottom:8px;">Only jobs that work for your visa</div>
      <div style="color:#8B949E;font-size:13px;line-height:1.6;">
        Every job is automatically checked for H1B sponsorship history, OPT eligibility,
        and STEM OPT status. You only see jobs where you can legally work. No more wasted applications.
      </div>
    </div>

    <div style="flex:1;background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:18px 16px;">
      <div style="color:#484F58;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Step 3 — Ranked for you</div>
      <div style="color:#FFA657;font-size:14px;font-weight:600;margin-bottom:8px;">Best matches shown first</div>
      <div style="color:#8B949E;font-size:13px;line-height:1.6;">
        Your resume is compared against every job using AI. Jobs that match your skills are shown
        at the top with a score. The highest scores are your best bets — apply those first.
      </div>
    </div>

  </div>

  <hr style="border-color:#30363D;margin:0 0 24px;">

  <!-- Part 2: comparison -->
  <div style="color:#8B949E;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px;">Why others fail you</div>
  <div style="display:flex;gap:12px;margin-bottom:28px;">

    <div style="flex:1;background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:18px 16px;">
      <div style="color:#F85149;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:12px;">
        LinkedIn / Indeed / Glassdoor
      </div>
      <ul style="color:#8B949E;font-size:13px;line-height:2;margin:0;padding-left:0;list-style:none;">
        <li><span style="color:#F85149;margin-right:8px;">✗</span>No H1B filter — waste hours on wrong companies</li>
        <li><span style="color:#F85149;margin-right:8px;">✗</span>Sponsorship checkboxes are self-reported — wrong</li>
        <li><span style="color:#F85149;margin-right:8px;">✗</span>No STEM OPT filter — cannot tell 3yr vs 1yr</li>
        <li><span style="color:#F85149;margin-right:8px;">✗</span>Built for US citizens — you are an afterthought</li>
        <li><span style="color:#F85149;margin-right:8px;">✗</span>Paid ads push irrelevant jobs to the top</li>
      </ul>
    </div>

    <div style="flex:1;background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:18px 16px;">
      <div style="color:#3FB950;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:12px;">
        Scraper 2.0 — MCT PathAI
      </div>
      <ul style="color:#8B949E;font-size:13px;line-height:2;margin:0;padding-left:0;list-style:none;">
        <li><span style="color:#3FB950;margin-right:8px;">✓</span>H1B verified from real USCIS government data</li>
        <li><span style="color:#3FB950;margin-right:8px;">✓</span>STEM OPT companies flagged before you apply</li>
        <li><span style="color:#3FB950;margin-right:8px;">✓</span>Jobs direct from company websites — no delay</li>
        <li><span style="color:#3FB950;margin-right:8px;">✓</span>Built for F1 and OPT students specifically</li>
        <li><span style="color:#3FB950;margin-right:8px;">✓</span>Zero ads — every job earned its place</li>
      </ul>
    </div>

  </div>

  <hr style="border-color:#30363D;margin:0 0 24px;">

  <!-- Part 3: 4 unique value cards -->
  <div style="color:#8B949E;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:12px;">What makes this different</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px;">

    <div style="background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:18px 16px;display:flex;gap:14px;align-items:flex-start;">
      <div style="width:36px;height:36px;border-radius:8px;background:#033A16;flex-shrink:0;
                  display:flex;align-items:center;justify-content:center;font-size:18px;">🛂</div>
      <div>
        <div style="color:#E6EDF3;font-size:13px;font-weight:600;margin-bottom:6px;">Your visa status is the filter</div>
        <div style="color:#8B949E;font-size:12px;line-height:1.6;">
          Every job filtered through your visa situation first. H1B needed? Only see sponsors.
          STEM OPT? Only see eligible companies.
        </div>
      </div>
    </div>

    <div style="background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:18px 16px;display:flex;gap:14px;align-items:flex-start;">
      <div style="width:36px;height:36px;border-radius:8px;background:#0D419D;flex-shrink:0;
                  display:flex;align-items:center;justify-content:center;font-size:18px;">🏢</div>
      <div>
        <div style="color:#E6EDF3;font-size:13px;font-weight:600;margin-bottom:6px;">Direct from company — no board</div>
        <div style="color:#8B949E;font-size:12px;line-height:1.6;">
          Jobs from Stripe, Airbnb, Anthropic, Snowflake career pages directly.
          Same morning they post.
        </div>
      </div>
    </div>

    <div style="background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:18px 16px;display:flex;gap:14px;align-items:flex-start;">
      <div style="width:36px;height:36px;border-radius:8px;background:#2D1B00;flex-shrink:0;
                  display:flex;align-items:center;justify-content:center;font-size:18px;">🎯</div>
      <div>
        <div style="color:#E6EDF3;font-size:13px;font-weight:600;margin-bottom:6px;">Resume score tells you where to focus</div>
        <div style="color:#8B949E;font-size:12px;line-height:1.6;">
          AI scores every job 0 to 100 against your resume. Jobs 80+ are your best matches.
          Stop applying blindly.
        </div>
      </div>
    </div>

    <div style="background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:18px 16px;display:flex;gap:14px;align-items:flex-start;">
      <div style="width:36px;height:36px;border-radius:8px;background:#2E1065;flex-shrink:0;
                  display:flex;align-items:center;justify-content:center;font-size:18px;">⏱️</div>
      <div>
        <div style="color:#E6EDF3;font-size:13px;font-weight:600;margin-bottom:6px;">Built for the 60-day clock</div>
        <div style="color:#8B949E;font-size:12px;line-height:1.6;">
          After graduation you have 60 days. Fresh jobs delivered every morning automatically.
          Your time is too valuable right now.
        </div>
      </div>
    </div>

  </div>

  <!-- Bottom banner -->
  <div style="border:1px solid #1F6FEB;border-radius:8px;padding:16px 20px;display:flex;gap:14px;align-items:flex-start;">
    <div style="width:10px;height:10px;border-radius:50%;background:#3FB950;flex-shrink:0;margin-top:4px;"></div>
    <div style="color:#C9D1D9;font-size:13px;line-height:1.75;">
      Zero ads. Zero sponsored listings. Zero fluff. Every job passed through a real visa filter,
      a real experience check, and a real resume match. Built by an immigrant who needed this
      and could not find it anywhere.
    </div>
  </div>

</div>
""", unsafe_allow_html=True)

st.markdown('<hr style="border-color:#30363D;margin:20px 0 16px;">', unsafe_allow_html=True)

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
