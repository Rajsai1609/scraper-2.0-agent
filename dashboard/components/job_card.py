"""Job cards — all 25 cards rendered in ONE st.markdown() call to prevent
Streamlit's per-element white background wrapper from leaking through."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

_EXP_LABEL = {
    "new_grad": "New Grad",
    "junior":   "Junior",
    "mid":      "Mid",
    "senior":   "Senior",
    "unknown":  "",
}

_CARD_CSS = """
<style>
.jc-wrap { background: #0D1117; }
.job-card {
    background: #161B22 !important;
    border: 0.5px solid #30363D;
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 10px;
    width: 100%;
    box-sizing: border-box;
}
.card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 6px;
}
.job-title {
    font-size: 15px;
    font-weight: 600;
    color: #58A6FF !important;
    word-break: break-word;
    flex: 1;
    text-decoration: none;
    line-height: 1.4;
}
.job-title:hover { text-decoration: underline; }
.job-meta {
    font-size: 12px;
    color: #8B949E !important;
    margin-bottom: 10px;
    word-break: break-word;
}
.score-circle {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    font-weight: 700;
    flex-shrink: 0;
}
.badges {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-bottom: 6px;
}
.badge {
    font-size: 10px;
    padding: 3px 8px;
    border-radius: 4px;
    font-weight: 500;
    white-space: nowrap;
}
.skills-row {
    font-size: 10px;
    color: #484F58 !important;
    margin-bottom: 8px;
    word-break: break-word;
}
.card-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 10px;
}
.posted-time {
    font-size: 10px;
    color: #484F58 !important;
}
.apply-btn {
    font-size: 13px;
    padding: 8px 18px;
    background: #238636 !important;
    color: #ffffff !important;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-weight: 500;
    min-width: 90px;
    text-align: center;
    text-decoration: none !important;
    display: inline-block;
    white-space: nowrap;
}
@media (max-width: 600px) {
    .job-title  { font-size: 14px; }
    .badge      { font-size: 9px; padding: 2px 6px; }
    .apply-btn  {
        display: block;
        width: 100%;
        text-align: center;
        padding: 10px;
        box-sizing: border-box;
    }
    .card-footer { flex-direction: column; align-items: stretch; }
}
</style>
"""


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


def _badge(text: str, bg: str, fg: str) -> str:
    return (
        f'<span class="badge" style="background:{bg};color:{fg};">'
        f'{text}</span>'
    )


def _build_card(row: pd.Series) -> str:
    """Return the HTML string for a single job card (no st.* calls)."""
    url   = row.get("url", "#") or "#"
    title = row.get("title", "Untitled") or "Untitled"

    company  = row.get("company", "") or ""
    platform = row.get("ats_platform", "") or ""
    location = row.get("location", "") or ""
    region   = row.get("usa_region", "") or ""

    company_meta = " · ".join(p for p in [company, platform] if p)
    loc_meta     = ", ".join(p for p in [location, region] if p)
    meta_display = " · ".join(p for p in [company_meta, loc_meta] if p)

    # ── Score circle ──────────────────────────────────────────────────────
    score = row.get("fit_score")
    has_score = (
        score is not None
        and not (isinstance(score, float) and pd.isna(score))
        and float(score) > 0
    )
    if has_score:
        score_int = int(score)
        if score_int >= 80:
            score_bg, score_fg = "#033A16", "#3FB950"
        elif score_int >= 60:
            score_bg, score_fg = "#2D1B00", "#FFA657"
        else:
            score_bg, score_fg = "#161B22", "#484F58"
        score_text = str(score_int)
    else:
        score_bg, score_fg, score_text = "#161B22", "#484F58", "—"

    # ── Badges ────────────────────────────────────────────────────────────
    badges: list[str] = []

    wm = str(row.get("work_mode", "unknown")).lower()
    _wm_map = {
        "remote": ("#0C4A6E", "#58A6FF", "Remote"),
        "hybrid": ("#2E1065", "#D2A8FF", "Hybrid"),
        "onsite": ("#2D1B00", "#FFA657", "Onsite"),
    }
    if wm in _wm_map:
        bg, fg, label = _wm_map[wm]
        badges.append(_badge(label, bg, fg))

    h1b = row.get("h1b_sponsor")
    if h1b is True:
        badges.append(_badge("H-1B ✓", "#033A16", "#3FB950"))
    elif h1b is False:
        badges.append(_badge("No Sponsor", "#3B0A0A", "#F85149"))
    else:
        badges.append(_badge("H-1B ?", "#1C2128", "#8B949E"))

    if row.get("opt_friendly") is True:
        badges.append(_badge("OPT ✓", "#033A16", "#3FB950"))
    if row.get("stem_opt_eligible") is True:
        badges.append(_badge("STEM OPT", "#0D419D", "#58A6FF"))

    if region:
        badges.append(_badge(region, "#1C2128", "#8B949E"))

    exp_key   = str(row.get("experience_level", ""))
    exp_label = _EXP_LABEL.get(exp_key, exp_key)
    if exp_label:
        badges.append(_badge(exp_label, "#1C2128", "#484F58"))

    badges_html = "".join(badges)

    # ── Skills ────────────────────────────────────────────────────────────
    skills = row.get("skills", [])
    if isinstance(skills, list) and skills:
        skills_str  = " · ".join(skills[:12])
        skills_html = f'<div class="skills-row">{skills_str}</div>'
    else:
        skills_html = ""

    # ── Posted ────────────────────────────────────────────────────────────
    posted = _days_ago(row.get("date_posted"))
    posted_html = (
        f'<span class="posted-time">{posted}</span>' if posted else '<span></span>'
    )

    return f"""
<div class="job-card">
  <div class="card-top">
    <div style="flex:1;min-width:0;">
      <a href="{url}" target="_blank" class="job-title">{title}</a>
      <div class="job-meta">{meta_display}</div>
    </div>
    <div class="score-circle"
         style="background:{score_bg};color:{score_fg};">{score_text}</div>
  </div>
  <div class="badges">{badges_html}</div>
  {skills_html}
  <div class="card-footer">
    {posted_html}
    <a href="{url}" target="_blank" class="apply-btn">Apply</a>
  </div>
</div>"""


def render_all_cards(jobs_df: pd.DataFrame) -> None:
    """Render all job cards in ONE st.markdown() call.

    Batching into a single call means Streamlit wraps the entire block in
    one div instead of wrapping each card individually, eliminating the
    per-card white background that bleeds through from Streamlit's wrapper.
    """
    cards_html = [_build_card(row) for _, row in jobs_df.iterrows()]
    st.markdown(
        _CARD_CSS
        + '<div class="jc-wrap">'
        + "".join(cards_html)
        + "</div>",
        unsafe_allow_html=True,
    )
