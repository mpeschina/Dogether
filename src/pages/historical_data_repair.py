from __future__ import annotations

from datetime import datetime, timedelta
import streamlit as st

from src.db.persistence import Persistence
from src.db.persistence_helpers import (
    _next_period_start,
    _now,
    _parse_dt,
    _period_start,
    _schedule,
)
from src.pages.page_helpers import schedule_label


LOOKBACK_PERIODS = 14


def editable_period_starts(
    goal: dict,
    now: datetime | None = None,
    lookback_periods: int = LOOKBACK_PERIODS,
) -> list[datetime]:
    schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
    current_start = _period_start(_now(now), schedule["base"])
    created_at = _parse_dt(goal.get("created_at"))
    first_goal_start = _period_start(created_at, schedule["base"]) if created_at else None
    period_delta = timedelta(days=1) if schedule["base"] == "day" else timedelta(weeks=1)

    starts = []
    cursor = current_start - period_delta
    while len(starts) < max(1, int(lookback_periods)):
        if first_goal_start is not None and cursor < first_goal_start:
            break
        starts.append(cursor)
        cursor -= period_delta
    return starts


def period_label(goal: dict, period_start: datetime) -> str:
    schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
    if schedule["base"] == "week":
        period_end = _next_period_start(period_start, schedule["base"]) - timedelta(days=1)
        return f"Week of {period_start.date().isoformat()} to {period_end.date().isoformat()}"
    return period_start.date().isoformat()


def _status_label(outcome: dict | None) -> str:
    if not isinstance(outcome, dict):
        return "No input"
    if outcome.get("fulfilled", outcome.get("completed", False)):
        return "Fulfilled"
    if outcome.get("completed"):
        return "Complete"
    return "Missed"


def _render_period_row(
    persistence: Persistence,
    goal: dict,
    user_id: str,
    participant: dict,
    period_start: datetime,
    now: datetime | None,
) -> None:
    period_key = period_start.date().isoformat()
    outcome = participant.get("period_outcomes", {}).get(period_key)
    target = max(1, int((outcome or {}).get("target", participant.get("target", 1)) or 1))
    current = max(0, int((outcome or {}).get("current", 0) or 0))

    with st.form(f"historical_data_repair_{goal['id']}_{period_key}", border=False):
        cols = st.columns([2.2, 1, 1.35, 1])
        cols[0].write(period_label(goal, period_start))
        cols[1].write(_status_label(outcome))
        value_cols = cols[2].columns([1, 0.65], vertical_alignment="center")
        corrected_current = value_cols[0].number_input(
            "Value",
            min_value=0,
            value=current,
            step=1,
            key=f"historical_data_repair_value_{goal['id']}_{period_key}",
            label_visibility="collapsed",
        )
        value_cols[1].caption(f"/ {target}")
        submitted = cols[3].form_submit_button("Save", use_container_width=True)
        if submitted:
            try:
                persistence.correct_goal_period_progress(
                    goal["id"],
                    user_id,
                    period_start,
                    int(corrected_current),
                    target=target,
                    now=now,
                )
                st.success("Input corrected.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))


def render_historical_data_repair(
    persistence: Persistence,
    user_id: str,
    now: datetime | None = None,
) -> None:
    st.title("Historical Data Repair")
    goals = persistence.list_goals_for_user(user_id, now=now)
    if not goals:
        st.info("No active goals.")
        return

    st.caption(f"Repair older goal values for the last {LOOKBACK_PERIODS} completed periods.")
    for goal in goals:
        participant = goal.get("participants", {}).get(user_id)
        if not isinstance(participant, dict):
            continue
        expander_label = f"{goal['description']} - {schedule_label(goal)}"
        with st.expander(expander_label, expanded=False):
            starts = editable_period_starts(goal, now=now)
            if not starts:
                st.caption("No completed periods are available for this goal yet.")
                continue
            header_cols = st.columns([2.2, 1, 1, 1])
            header_cols[0].caption("Period")
            header_cols[1].caption("Status")
            header_cols[2].caption("Value")
            header_cols[3].caption("Action")
            for period_start in starts:
                _render_period_row(persistence, goal, user_id, participant, period_start, now)
