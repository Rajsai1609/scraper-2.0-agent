"""Sidebar filter controls — returns a dict of active filter values."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_sidebar(df: pd.DataFrame) -> dict:
    """
    Render all filter widgets in st.sidebar.
    Returns only filters that deviate from their default so the caller can
    apply them without extra logic.
    """
    st.sidebar.markdown("""
<div style="padding:8px 0 12px;border-bottom:0.5px solid #30363D;margin-bottom:12px;">
  <div style="font-size:15px;font-weight:500;color:#E6EDF3;">MCT PathAI</div>
  <div style="font-size:11px;color:#484F58;margin-top:2px;">F1 · OPT · STEM OPT jobs</div>
</div>
""", unsafe_allow_html=True)
    st.sidebar.title("Filters")
    filters: dict = {}

    # ── Free-text search ──────────────────────────────────────────────────
    search = st.sidebar.text_input(
        "Search title / company",
        placeholder="e.g. Machine Learning, Google",
    )
    if search.strip():
        filters["search"] = search.strip()

    st.sidebar.divider()

    # ── Categorical multiselects ──────────────────────────────────────────
    def _unique_sorted(col: str) -> list[str]:
        if col not in df.columns:
            return []
        return sorted(str(v) for v in df[col].dropna().unique() if str(v))

    selected_modes = st.sidebar.multiselect(
        "Work Mode",
        options=["hybrid", "onsite", "remote", "unknown"],
        default=[],
    )
    if selected_modes:
        filters["work_mode"] = selected_modes

    selected_exp = st.sidebar.multiselect(
        "Experience Level", options=_unique_sorted("experience_level"), default=[]
    )
    if selected_exp:
        filters["experience_level"] = selected_exp

    selected_cats = st.sidebar.multiselect(
        "Job Category", options=_unique_sorted("job_category"), default=[]
    )
    if selected_cats:
        filters["job_category"] = selected_cats

    region_opts = [r for r in _unique_sorted("usa_region") if r]
    selected_regions = st.sidebar.multiselect(
        "USA Region", options=region_opts, default=[]
    )
    if selected_regions:
        filters["usa_region"] = selected_regions

    st.sidebar.divider()

    # ── Visa checkboxes ───────────────────────────────────────────────────
    st.sidebar.subheader("Visa Sponsorship")
    if st.sidebar.checkbox("H-1B Sponsor"):
        filters["h1b_sponsor"] = True
    if st.sidebar.checkbox("OPT Friendly"):
        filters["opt_friendly"] = True
    if st.sidebar.checkbox("STEM OPT Eligible"):
        filters["stem_opt_eligible"] = True
    if st.sidebar.checkbox("Entry Eligible Only"):
        filters["is_entry_eligible"] = True

    st.sidebar.divider()

    # ── Experience slider ─────────────────────────────────────────────────
    st.sidebar.subheader("Experience Cap")
    max_years = st.sidebar.slider(
        "Max years required",
        min_value=0,
        max_value=10,
        value=5,
        help="Hides jobs that require more years than this (0–10+)",
    )
    filters["max_years"] = max_years

    # ── Fit score slider (only when scores exist) ─────────────────────────
    if "fit_score" in df.columns and df["fit_score"].notna().any():
        min_score = st.sidebar.slider("Min Fit Score", min_value=0, max_value=100, value=0)
        if min_score > 0:
            filters["min_score"] = min_score

    st.sidebar.divider()

    if st.sidebar.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    return filters
