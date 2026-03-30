"""Top metrics row — four key numbers rendered as GitHub-dark styled cards."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_stats(df: pd.DataFrame) -> None:
    """Render a single row of four colored metric cards above the job list."""
    def _bool_count(col: str) -> int:
        if col not in df.columns:
            return 0
        return int(df[col].eq(True).sum())

    total     = len(df)
    h1b       = _bool_count("h1b_sponsor")
    opt       = _bool_count("opt_friendly")

    if "fit_score" in df.columns and df["fit_score"].notna().any():
        top_score: int | None = int(df["fit_score"].max())
    else:
        top_score = None

    top_score_val = str(top_score) if top_score is not None else "—"
    top_score_fg  = "#F0E68C" if top_score is not None else "#484F58"

    html = f"""
<div style="display:flex;gap:12px;margin-bottom:8px;">
  <div style="flex:1;background:#161B22;border:0.5px solid #30363D;border-radius:8px;padding:14px 18px;">
    <div style="color:#8B949E;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Total Jobs</div>
    <div style="color:#E6EDF3;font-size:30px;font-weight:700;line-height:1;">{total}</div>
  </div>
  <div style="flex:1;background:#161B22;border:0.5px solid #30363D;border-radius:8px;padding:14px 18px;">
    <div style="color:#58A6FF;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">H-1B Sponsor</div>
    <div style="color:#58A6FF;font-size:30px;font-weight:700;line-height:1;">{h1b}</div>
  </div>
  <div style="flex:1;background:#161B22;border:0.5px solid #30363D;border-radius:8px;padding:14px 18px;">
    <div style="color:#3FB950;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">OPT Friendly</div>
    <div style="color:#3FB950;font-size:30px;font-weight:700;line-height:1;">{opt}</div>
  </div>
  <div style="flex:1;background:#161B22;border:0.5px solid #30363D;border-radius:8px;padding:14px 18px;">
    <div style="color:#F85149;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Top Score</div>
    <div style="color:{top_score_fg};font-size:30px;font-weight:700;line-height:1;">{top_score_val}</div>
  </div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)
