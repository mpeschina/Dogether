from __future__ import annotations

from datetime import datetime
from html import escape

import streamlit as st

from src.db.persistence import activity_calendar_weeks


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
    cols[2].metric("Days using app", stats["days_using_app"])
    cols[3].metric("Month completion", f"{stats['completion_rate']}%")

    st.subheader("Activity")
    st.markdown(_activity_diagram(stats.get("activity_days", {}), now), unsafe_allow_html=True)


def _activity_diagram(activity_days: dict, now: datetime | None = None) -> str:
    weeks = activity_calendar_weeks(activity_days, now)
    rows = []
    for week in weeks:
        cells = []
        for day in week:
            if day is None:
                cells.append("<td></td>")
                continue
            percent = float(day["percent"])
            color = _activity_color(percent, int(day["active_goals"]))
            title = escape(
                f"{day['date']}: {day['fulfilled_goals']} / {day['active_goals']} goals fulfilled ({percent}%)"
            )
            cells.append(
                (
                    "<td>"
                    f"<div title='{title}' style='height:2.4rem;border-radius:6px;"
                    f"background:{color};display:flex;align-items:center;justify-content:center;"
                    "font-size:0.8rem;color:#111827;'>"
                    f"{day['day']}"
                    "</div>"
                    "</td>"
                )
            )
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        "<table style='width:100%;border-spacing:0.35rem;border-collapse:separate;'>"
        "<thead><tr>"
        "<th>Mon</th><th>Tue</th><th>Wed</th><th>Thu</th><th>Fri</th><th>Sat</th><th>Sun</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _activity_color(percent: float, active_goals: int) -> str:
    if active_goals <= 0:
        return "#f3f4f6"
    if percent >= 100:
        return "#86efac"
    if percent >= 67:
        return "#bef264"
    if percent >= 34:
        return "#fde68a"
    if percent > 0:
        return "#fdba74"
    return "#fecaca"
