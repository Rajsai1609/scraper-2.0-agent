"""Individual job card — renders one DataFrame row as a GitHub-dark styled HTML card."""
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
        f'<span style="background:{bg};color:{fg};padding:3px 9px;'
        f'border-radius:4px;font-size:11px;font-weight:500;white-space:nowrap;">'
        f'{text}</span>'
    )


def render_job_card(row: pd.Series) -> None:
    """Render one job as a GitHub-dark HTML card."""
    url   = row.get("url", "#") or "#"
    title = row.get("title", "Untitled") or "Untitled"

    company  = row.get("company", "") or ""
    platform = row.get("ats_platform", "") or ""
    location = row.get("location", "") or ""
    region   = row.get("usa_region", "") or ""

    company_meta = " · ".join(p for p in [company, platform] if p)
    loc_meta     = ", ".join(p for p in [location, region] if p)
    meta_display = " · ".join(p for p in [company_meta, loc_meta] if p)

    # ── Score circle ─────────────────────────────────────────────────────────
    score = row.get("fit_score")
    has_score = score is not None and not (isinstance(score, float) and pd.isna(score))
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

    # ── Badges ────────────────────────────────────────────────────────────────
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

    badges_html = " ".join(badges)

    # ── Skills ────────────────────────────────────────────────────────────────
    skills = row.get("skills", [])
    if isinstance(skills, list) and skills:
        skills_str  = " · ".join(skills[:12])
        skills_html = f'<div style="color:#484F58;font-size:10px;margin-top:8px;">{skills_str}</div>'
    else:
        skills_html = ""

    # ── Posted ────────────────────────────────────────────────────────────────
    posted = _days_ago(row.get("date_posted"))
    posted_html = (
        f'<span style="color:#484F58;font-size:10px;">{posted}</span>'
        if posted else '<span></span>'
    )

    html = f"""
<div style="background:#161B22;border:0.5px solid #30363D;border-radius:8px;padding:16px 20px;margin-bottom:12px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;">
    <div style="flex:1;min-width:0;">
      <a href="{url}" target="_blank"
         style="color:#58A6FF;font-size:18px;font-weight:600;text-decoration:none;word-break:break-word;">{title}</a>
    </div>
    <div style="background:{score_bg};color:{score_fg};width:44px;height:44px;border-radius:50%;
                display:flex;align-items:center;justify-content:center;
                font-weight:700;font-size:15px;flex-shrink:0;margin-left:16px;">{score_text}</div>
  </div>
  <div style="color:#8B949E;font-size:13px;margin-bottom:10px;">{meta_display}</div>
  <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:4px;">{badges_html}</div>
  {skills_html}
  <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px;">
    {posted_html}
    <a href="{url}" target="_blank"
       style="background:#238636;color:#ffffff;padding:6px 14px;border-radius:6px;
              text-decoration:none;font-size:13px;font-weight:500;">Apply</a>
  </div>
</div>
"""
    st.html(html)
