"""Top metrics row — responsive 2x2 (mobile) / 4x1 (desktop) grid."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_stats(df: pd.DataFrame) -> None:
    """Render a responsive grid of four colored metric cards."""
    def _bool_count(col: str) -> int:
        if col not in df.columns:
            return 0
        return int(df[col].eq(True).sum())

    total = len(df)
    h1b   = _bool_count("h1b_sponsor")
    opt   = _bool_count("opt_friendly")

    if "fit_score" in df.columns and df["fit_score"].notna().any():
        top_score: int | None = int(df["fit_score"].max())
    else:
        top_score = None

    score_val = str(top_score) if top_score is not None else "0"
    score_fg  = "#F0E68C" if top_score is not None else "#484F58"

    html = f"""
<style>
.stats-container {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    margin-bottom: 16px;
}}
@media (min-width: 768px) {{
    .stats-container {{
        grid-template-columns: repeat(4, 1fr);
    }}
}}
.stat-box {{
    background: #161B22;
    border: 0.5px solid #30363D;
    border-radius: 8px;
    padding: 12px 14px;
}}
.stat-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 4px;
}}
.stat-value {{
    font-size: 26px;
    font-weight: 700;
    line-height: 1;
}}
.stat-sub {{
    font-size: 10px;
    color: #484F58;
    margin-top: 4px;
}}
</style>
<div class="stats-container">
  <div class="stat-box">
    <div class="stat-label" style="color:#8B949E;">Total Jobs</div>
    <div class="stat-value" style="color:#E6EDF3;">{total:,}</div>
    <div class="stat-sub">USA only · 0-5 yrs</div>
  </div>
  <div class="stat-box">
    <div class="stat-label" style="color:#58A6FF;">H-1B Sponsor</div>
    <div class="stat-value" style="color:#58A6FF;">{h1b:,}</div>
    <div class="stat-sub">verified companies</div>
  </div>
  <div class="stat-box">
    <div class="stat-label" style="color:#3FB950;">OPT Friendly</div>
    <div class="stat-value" style="color:#3FB950;">{opt:,}</div>
    <div class="stat-sub">F1 / OPT ready</div>
  </div>
  <div class="stat-box">
    <div class="stat-label" style="color:#F85149;">Top Score</div>
    <div class="stat-value" style="color:{score_fg};">{score_val}</div>
    <div class="stat-sub">your resume match</div>
  </div>
</div>
"""
    st.html(html)
