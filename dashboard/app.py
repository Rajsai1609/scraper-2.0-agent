"""
MCT PathAI — Multi-Student Job Intelligence Dashboard (step4)
Extends the single-student view with a per-student score selector backed
by Supabase (MCT-Alesia).

Run:
    cd scraper-2.0
    streamlit run dashboard/app.py

Streamlit Cloud secrets required:
    GOOGLE_CREDENTIALS_JSON   — raw service-account JSON string
    SUPABASE_URL              — https://xxxx.supabase.co
    SUPABASE_ANON_KEY         — anon/public key (read-only RLS)
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from components.job_card import render_all_cards
from components.sidebar import render_sidebar
from components.stats_bar import render_stats
from sheets_reader import load_jobs

load_dotenv()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="MCT PathAI",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": (
            "MCT PathAI — Job Intelligence for "
            "F1/OPT students. Built by Rajsai Naredla "
            "· MCTechnology LLC · Seattle, WA"
        ),
    },
)

# ---------------------------------------------------------------------------
# Global CSS  (identical to original dashboard)
# ---------------------------------------------------------------------------
st.markdown("""
<style>
.stApp { background-color: #0D1117 !important; }
.main .block-container {
    background-color: #0D1117 !important;
    padding: 1rem !important;
    max-width: 100% !important;
    overflow-x: hidden !important;
}
div[data-testid="stVerticalBlock"]              { background-color: #0D1117 !important; }
div[data-testid="stVerticalBlockBorderWrapper"] { background-color: #0D1117 !important; border: none !important; }
div[data-testid="column"]                       { background-color: #0D1117 !important; }
div[data-testid="stExpander"]       { background-color: #161B22 !important; border: 0.5px solid #30363D !important; border-radius: 8px !important; }
div[data-testid="stExpanderDetails"] { background-color: #161B22 !important; }
div[class*="stVerticalBlock"] > div { background-color: #0D1117 !important; }
.stButton > button { background-color: #238636 !important; color: #ffffff !important; border: none !important; border-radius: 6px !important; width: 100% !important; }
.stButton > button:hover { background-color: #2EA043 !important; }
div[data-testid="stSelectbox"] > div { background-color: #161B22 !important; border: 0.5px solid #30363D !important; color: #E6EDF3 !important; }
div[data-testid="stTextInput"] > div { background-color: #161B22 !important; border: 0.5px solid #30363D !important; }
input { background-color: #161B22 !important; color: #E6EDF3 !important; }
.stMultiSelect > div > div { background-color: #0D1117; border: 0.5px solid #30363D; }
.stNumberInput > div > div > input { background-color: #0D1117; border: 0.5px solid #30363D; color: #C9D1D9; }
section[data-testid="stSidebar"] { background-color: #161B22 !important; border-right: 0.5px solid #30363D !important; }
section[data-testid="stSidebar"] > div { background-color: #161B22 !important; }
p, span, label, div { color: #E6EDF3; }
hr { border-color: #30363D !important; }
div[data-testid="metric-container"] { background-color: #161B22 !important; border: 0.5px solid #30363D !important; border-radius: 8px !important; padding: 12px 16px; }
* { scrollbar-color: #30363D #0D1117 !important; }
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #0D1117; }
::-webkit-scrollbar-thumb { background: #30363D; border-radius: 4px; }
@media (max-width: 768px) {
  .block-container { padding: 0.5rem 0.5rem !important; }
  h1 { font-size: 18px !important; }
  h2 { font-size: 16px !important; }
  .stButton > button { padding: 10px !important; font-size: 14px !important; }
}
.stMarkdown > div { background: #0D1117 !important; }
iframe { background: #0D1117 !important; }
.element-container { background: #0D1117 !important; }
.stHtml { background: #0D1117 !important; }
[data-testid="stHtml"] { background: #0D1117 !important; }
img { max-width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    '<h1 style="color:#E6EDF3;margin-bottom:2px;">🎯 MCT <span style="color:#58A6FF;">PathAI</span> — Job Intelligence</h1>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="color:#484F58;font-size:13px;margin-top:0;">Live data from Google Sheets · auto-refreshes every 5 minutes</p>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY", "")


def _supabase_available() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_KEY)


@st.cache_resource(show_spinner=False)
def _get_supabase_client():
    from supabase import create_client  # type: ignore[import]
    return create_client(_SUPABASE_URL, _SUPABASE_KEY)


@st.cache_data(ttl=300, show_spinner="Loading students from Supabase…")
def load_students() -> list[dict]:
    """Return [{id, name}, …] from Supabase students table."""
    if not _supabase_available():
        return []
    try:
        client = _get_supabase_client()
        result = client.table("students").select("id, name").order("name").execute()
        return result.data or []
    except Exception as exc:
        st.warning(f"Could not load students from Supabase: {exc}")
        return []


@st.cache_data(ttl=300, show_spinner="Loading scores from Supabase…")
def load_student_scores(student_id: str) -> dict[str, float]:
    """
    Return {job_id: fit_score} for the given student.
    fit_score is in [0, 1]; the dashboard multiplies by 100 for display.
    """
    if not _supabase_available():
        return {}
    try:
        client = _get_supabase_client()
        result = (
            client.table("student_job_scores")
            .select("job_id, fit_score")
            .eq("student_id", student_id)
            .execute()
        )
        return {row["job_id"]: row["fit_score"] for row in (result.data or [])}
    except Exception as exc:
        st.warning(f"Could not load scores for student: {exc}")
        return {}


def _apply_student_scores(df: pd.DataFrame, scores: dict[str, float]) -> pd.DataFrame:
    """
    Merge Supabase per-student scores into the DataFrame.
    Scores are in [0,1]; multiply by 100 to match the 0–100 display range
    expected by job_card.py and stats_bar.py.
    """
    if not scores:
        return df
    score_series = df["id"].map(scores)          # NaN for unscored jobs
    df = df.copy()
    df["fit_score"] = (score_series * 100).round(0)
    return df


def _scale_fit_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise fit_score to [0, 100] for display.
    Google Sheets stores scores as [0, 1] floats; job_card.py expects integers
    in [0, 100] for the coloured score circle.
    """
    if "fit_score" not in df.columns:
        return df
    max_val = df["fit_score"].dropna().max()
    if max_val is not None and max_val <= 1.0:
        df = df.copy()
        df["fit_score"] = (df["fit_score"] * 100).round(0)
    return df


# ---------------------------------------------------------------------------
# Load base job data from Google Sheets
# ---------------------------------------------------------------------------
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

# Scale single-student fit_score from [0,1] to [0,100] for correct display
df = _scale_fit_score(df)

# ---------------------------------------------------------------------------
# Student selector (sidebar — above existing filters)
# ---------------------------------------------------------------------------
students = load_students()
selected_student_id: str | None = None
selected_student_name = "All students"

if students:
    with st.sidebar:
        st.markdown("""
<div style="padding:8px 0 12px;border-bottom:0.5px solid #30363D;margin-bottom:12px;">
  <div style="font-size:13px;font-weight:600;color:#58A6FF;">👤 Student View</div>
  <div style="font-size:11px;color:#484F58;margin-top:2px;">Personalised scores from Supabase</div>
</div>
""", unsafe_allow_html=True)

        student_options = ["All students"] + [s["name"] for s in students]
        chosen = st.selectbox(
            "Score jobs as:",
            options=student_options,
            index=0,
            key="student_selector",
            label_visibility="collapsed",
        )

        if chosen != "All students":
            match = next((s for s in students if s["name"] == chosen), None)
            if match:
                selected_student_id = match["id"]
                selected_student_name = match["name"]

    # Overlay per-student scores when a student is chosen
    if selected_student_id:
        scores = load_student_scores(selected_student_id)
        if scores:
            df = _apply_student_scores(df, scores)
        else:
            st.sidebar.info("No scores yet for this student — run step3_multi_scorer.py.")
else:
    # Supabase not configured or no students yet — silent degradation
    pass

# ---------------------------------------------------------------------------
# Sidebar filters (render_sidebar unchanged from original)
# ---------------------------------------------------------------------------
filters = render_sidebar(df)

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
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

# Newest first, then by score descending for student-specific views
if selected_student_id:
    filtered = filtered.sort_values("fit_score", ascending=False, na_position="last")
else:
    filtered = filtered.sort_values(
        ["date_posted", "fetched_at"], ascending=False, na_position="last"
    )
filtered = filtered.reset_index(drop=True)

# ---------------------------------------------------------------------------
# Founder story (identical to original)
# ---------------------------------------------------------------------------
with st.expander("👤 About the builder", expanded=False):
    st.html("""
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
  <div style="border-top:0.5px solid #30363D;padding-top:14px;color:#484F58;font-size:12px;">
    Built by an immigrant who lived this problem ·
    <a href="https://www.linkedin.com/in/rajsainaredla09" target="_blank"
       style="color:#58A6FF;text-decoration:none;">linkedin.com/in/rajsainaredla09</a>
    · MCTechnology LLC · Seattle, WA
  </div>
</div>
""")

# ---------------------------------------------------------------------------
# "How this works" toggle (identical to original)
# ---------------------------------------------------------------------------
if "show_why" not in st.session_state:
    st.session_state.show_why = False

_why_label = "How this works ▲" if st.session_state.show_why else "How this works ▼"
if st.button(_why_label, key="toggle_why"):
    st.session_state.show_why = not st.session_state.show_why
    st.rerun()

if st.session_state.show_why:
    st.html("""
<div style="background:#161B22;border:0.5px solid #30363D;border-radius:12px;padding:28px 32px;margin-top:4px;">
  <div style="color:#E6EDF3;font-size:20px;font-weight:700;">How this tool gets you jobs</div>
  <div style="color:#8B949E;font-size:13px;margin-top:4px;">No tech talk. Just what this does for you every single day.</div>
  <hr style="border-color:#30363D;margin:18px 0;">
  <div style="display:flex;gap:12px;margin-bottom:28px;">
    <div style="flex:1;background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:18px 16px;">
      <div style="color:#484F58;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Step 1 — Every morning</div>
      <div style="color:#58A6FF;font-size:14px;font-weight:600;margin-bottom:8px;">Fresh jobs land in your feed</div>
      <div style="color:#8B949E;font-size:13px;line-height:1.6;">Every day at 7AM this tool visits the career pages of 20+ top companies and pulls their latest job openings.</div>
    </div>
    <div style="flex:1;background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:18px 16px;">
      <div style="color:#484F58;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Step 2 — Instantly filtered</div>
      <div style="color:#3FB950;font-size:14px;font-weight:600;margin-bottom:8px;">Only jobs that work for your visa</div>
      <div style="color:#8B949E;font-size:13px;line-height:1.6;">Every job is checked for H1B sponsorship, OPT eligibility, and STEM OPT status automatically.</div>
    </div>
    <div style="flex:1;background:#0D1117;border:0.5px solid #30363D;border-radius:8px;padding:18px 16px;">
      <div style="color:#484F58;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Step 3 — Ranked for you</div>
      <div style="color:#FFA657;font-size:14px;font-weight:600;margin-bottom:8px;">Best matches shown first</div>
      <div style="color:#8B949E;font-size:13px;line-height:1.6;">Your resume is compared against every job using AI. Jobs matching your skills are shown at the top.</div>
    </div>
  </div>
  <div style="border:1px solid #1F6FEB;border-radius:8px;padding:16px 20px;display:flex;gap:14px;align-items:flex-start;">
    <div style="width:10px;height:10px;border-radius:50%;background:#3FB950;flex-shrink:0;margin-top:4px;"></div>
    <div style="color:#C9D1D9;font-size:13px;line-height:1.75;">
      Zero ads. Zero sponsored listings. Every job passed through a real visa filter, a real experience
      check, and a real resume match. Built by an immigrant who needed this and could not find it anywhere.
    </div>
  </div>
</div>
""")

st.markdown('<hr style="border-color:#30363D;margin:20px 0 16px;">', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Student context banner (when student selected)
# ---------------------------------------------------------------------------
if selected_student_id:
    top_score = filtered["fit_score"].dropna().max() if not filtered.empty else None
    top_str = f"Top match: **{int(top_score)}**" if top_score else "No scores yet"
    st.markdown(
        f'<div style="background:#0D419D22;border:0.5px solid #1F6FEB;border-radius:8px;'
        f'padding:10px 16px;margin-bottom:12px;font-size:13px;color:#58A6FF;">'
        f'👤 Showing scores for <strong>{selected_student_name}</strong>  ·  {top_str}'
        f'</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Stats row
# ---------------------------------------------------------------------------
render_stats(filtered)
st.markdown('<hr style="border-color:#30363D;margin:16px 0;">', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Result count
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Paginated job cards
# ---------------------------------------------------------------------------
if filtered.empty:
    st.info("No jobs match the current filters. Try broadening your search.")
else:
    PAGE_SIZE = 25
    total_pages = max(1, (total_filtered + PAGE_SIZE - 1) // PAGE_SIZE)

    if "page_idx" not in st.session_state:
        st.session_state.page_idx = 0

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

    render_all_cards(page_df)

    if total_pages > 1:
        st.markdown(
            f'<p style="color:#8B949E;font-size:12px;text-align:center;">Page {page_idx + 1} of {total_pages} · {total_filtered} results</p>',
            unsafe_allow_html=True,
        )
