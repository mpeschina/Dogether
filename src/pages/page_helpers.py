from __future__ import annotations

import streamlit as st

from src.db.persistence import SCHEDULES


def schedule_label(goal: dict) -> str:
    label = SCHEDULES.get(goal.get("schedule_class"), {}).get(
        "label",
        goal.get("schedule_class", "Goal"),
    )
    if goal.get("schedule_class") in {"daily_x_per_week", "weekly_x_per_month"}:
        return label.replace("X", str(goal.get("required_periods", 1)), 1)
    return label


def participant_name(users: dict[str, dict], participant_id: str) -> str:
    user = users.get(participant_id, {})
    return user.get("name") or user.get("email") or participant_id


def progress_bar(current: int, target: int, show_caption: bool = True) -> None:
    target = max(1, int(target))
    st.progress(min(1.0, max(0.0, current / target)))
    if show_caption:
        st.caption(f"{current} / {target}")
