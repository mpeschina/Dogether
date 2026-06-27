from __future__ import annotations

from datetime import datetime

import streamlit as st


def render_account(persistence, current_user: dict, user_id: str, now: datetime | None = None) -> None:
    st.title("Account")
    st.write("Name")
    st.subheader(current_user["name"])
    st.write("Email")
    st.subheader(current_user["email"])

    stats = persistence.account_stats(user_id, now=now)
    cols = st.columns(4)
    cols[0].metric("Active goals", stats["active_goals"])
    cols[1].metric("Friends", stats["friend_count"])
    cols[2].metric("Completed periods", stats["completed_periods"])
    cols[3].metric("Completion rate", f"{stats['completion_rate']}%")
    st.caption(f"Recorded periods: {stats['recorded_periods']}")
