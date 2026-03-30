"""Top metrics row — six key numbers at a glance."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_stats(df: pd.DataFrame) -> None:
    """Render a single row of st.metric cards above the job list."""
    def _count(col: str, value) -> int:
        if col not in df.columns:
            return 0
        return int((df[col] == value).sum())

    def _bool_count(col: str) -> int:
        if col not in df.columns:
            return 0
        return int(df[col].eq(True).sum())

    total   = len(df)
    remote  = _count("work_mode", "remote")
    hybrid  = _count("work_mode", "hybrid")
    h1b     = _bool_count("h1b_sponsor")
    opt     = _bool_count("opt_friendly")
    entry   = _bool_count("is_entry_eligible")

    cols = st.columns(6)
    cols[0].metric("Total Jobs",     total)
    cols[1].metric("Remote",         remote)
    cols[2].metric("Hybrid",         hybrid)
    cols[3].metric("H-1B Sponsor",   h1b)
    cols[4].metric("OPT Friendly",   opt)
    cols[5].metric("Entry Eligible", entry)
