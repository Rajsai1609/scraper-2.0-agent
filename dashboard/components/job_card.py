"""Individual job card — renders one DataFrame row as a bordered container."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

_WORK_MODE_BADGE = {
    "remote":  "🟢 Remote",
    "hybrid":  "🟡 Hybrid",
    "onsite":  "🔵 Onsite",
    "unknown": "⚪ Unknown",
}

_EXP_LABEL = {
    "new_grad": "New Grad",
    "junior":   "Junior",
    "mid":      "Mid",
    "senior":   "Senior",
    "unknown":  "",
}

_CATEGORY_LABEL = {
    "software_engineer":  "Software Engineer",
    "data_analyst":       "Data Analyst",
    "data_engineer":      "Data Engineer",
    "ml_ai_engineer":     "ML / AI Engineer",
    "devops_cloud":       "DevOps / Cloud",
    "frontend_engineer":  "Frontend Engineer",
    "backend_engineer":   "Backend Engineer",
    "fullstack_engineer": "Fullstack Engineer",
    "product_manager":    "Product Manager",
    "other":              "Other",
}


def _days_ago(dt) -> str:
    if dt is None or (isinstance(dt, float) and pd.isna(dt)):
        return ""
    try:
        ts = pd.Timestamp(dt)
        if pd.isna(ts):
            return ""
        now = datetime.now(tz=timezone.utc)
        delta = now - ts.to_pydatetime()
        d = delta.days
        if d == 0:
            return "today"
        if d == 1:
            return "1 day ago"
        return f"{d} days ago"
    except Exception:
        return ""


def render_job_card(row: pd.Series) -> None:
    """Render one job as a clean card with header, detail columns, and skill tags."""
    with st.container(border=True):

        # ── Row 1: title + work-mode badge ───────────────────────────────
        col_title, col_badge = st.columns([5, 1])

        with col_title:
            url   = row.get("url", "#") or "#"
            title = row.get("title", "Untitled") or "Untitled"
            st.markdown(f"### [{title}]({url})")

            company  = row.get("company", "")
            platform = row.get("ats_platform", "")
            meta = " · ".join(p for p in [company, platform] if p)
            if meta:
                st.caption(meta)

        with col_badge:
            wm = str(row.get("work_mode", "unknown")).lower()
            st.markdown(_WORK_MODE_BADGE.get(wm, wm))
            score = row.get("fit_score")
            if score is not None and not (isinstance(score, float) and pd.isna(score)):
                st.markdown(f"**Score: {int(score)}**")

        # ── Row 2: three detail columns ───────────────────────────────────
        col1, col2, col3 = st.columns(3)

        with col1:
            exp_key = str(row.get("experience_level", ""))
            exp     = _EXP_LABEL.get(exp_key, exp_key)
            yr_min  = row.get("years_min")
            yr_max  = row.get("years_max")
            has_min = yr_min is not None and not (isinstance(yr_min, float) and pd.isna(yr_min))
            has_max = yr_max is not None and not (isinstance(yr_max, float) and pd.isna(yr_max))

            if has_min:
                yr_str = f"{int(yr_min)}"
                if has_max:
                    yr_str += f"–{int(yr_max)}"
                exp_display = f"{exp} ({yr_str} yrs)" if exp else f"{yr_str} yrs"
            else:
                exp_display = exp

            if exp_display:
                st.markdown(f"**Experience:** {exp_display}")

            cat_key = str(row.get("job_category", ""))
            cat     = _CATEGORY_LABEL.get(cat_key, cat_key)
            if cat and cat_key != "other":
                st.markdown(f"**Category:** {cat}")

        with col2:
            location = row.get("location", "")
            region   = row.get("usa_region", "")
            loc_str  = ", ".join(p for p in [location, region] if p)
            if loc_str:
                st.markdown(f"**Location:** {loc_str}")

            posted = _days_ago(row.get("date_posted"))
            if posted:
                st.markdown(f"**Posted:** {posted}")

        with col3:
            visa_parts = []
            if row.get("h1b_sponsor") is True:
                visa_parts.append("H-1B ✓")
            if row.get("opt_friendly") is True:
                visa_parts.append("OPT ✓")
            if row.get("stem_opt_eligible") is True:
                visa_parts.append("STEM OPT ✓")
            if visa_parts:
                st.markdown(f"**Visa:** {' · '.join(visa_parts)}")

            if row.get("is_entry_eligible") is True:
                st.markdown("**Entry Eligible** ✓")

        # ── Row 3: skill tags ─────────────────────────────────────────────
        skills = row.get("skills", [])
        if isinstance(skills, list) and skills:
            st.markdown(" ".join(f"`{s}`" for s in skills[:12]))
