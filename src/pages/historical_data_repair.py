from __future__ import annotations

from datetime import datetime, timedelta
import random

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
READY_SESSION_KEY = "historical_data_repair_ready"
READY_OPTION_SESSION_KEY = "historical_data_repair_ready_option"
READINESS_GATE_OPTIONS = [
    {
        "id": "sentence_repeat",
        "sentence1_html": "Playing around with the Histroy is dangerous.",
        "wait1_seconds": 2,
        "sentence2_html": "-- repeat this sentence 30 times in your head.",
        "wait2_seconds": 4,
        "progress_seconds": 30,
        "button_text": "I did it. I am ready!",
    },
    {
        "id": "timeline_paradox",
        "sentence1_html": (
            "⚠️ <strong>Historical records are about to be modified.</strong><br>"
            "<span>(Please avoid creating timeline paradoxes.)</span>"
        ),
        "wait1_seconds": 2,
        "sentence2_html": (
            "Before proceeding, repeat this sentence <strong>30 times in your head:</strong><br>"
            "&quot;I will not accidentally invent a new past.&quot;"
        ),
        "wait2_seconds": 4,
        "progress_seconds": 60,
        "button_text": "Ready",
    },
]


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


def _outcome_fulfilled(outcome: dict | None) -> bool:
    return isinstance(outcome, dict) and bool(outcome.get("fulfilled", outcome.get("completed", False)))


def _status_label(outcome: dict | None) -> str:
    if not isinstance(outcome, dict):
        return "No input"
    if _outcome_fulfilled(outcome):
        return "Fulfilled"
    if outcome.get("completed"):
        return "Complete"
    return "Missed"


def _goal_option_label(goal: dict, duplicate_descriptions: set[str]) -> str:
    description = str(goal.get("description", "Goal"))
    label = f"{description} - {schedule_label(goal)}"
    if description in duplicate_descriptions:
        label = f"{label} ({str(goal.get('id', ''))[-6:]})"
    return label


def _render_period_inputs(
    goal: dict,
    participant: dict,
    period_starts: list[datetime],
) -> dict[datetime, tuple[int, int, int]]:
    values = {}
    header_cols = st.columns([2.2, 1, 1.35])
    header_cols[0].caption("Period")
    header_cols[1].caption("Status")
    header_cols[2].caption("Value")
    for period_start in period_starts:
        period_key = period_start.date().isoformat()
        outcome = participant.get("period_outcomes", {}).get(period_key)
        target = max(1, int((outcome or {}).get("target", participant.get("target", 1)) or 1))
        current = max(0, int((outcome or {}).get("current", 0) or 0))
        row_state = "fulfilled" if _outcome_fulfilled(outcome) else "unfulfilled"
        with st.container(key=f"history_repair_row_{row_state}_{goal['id']}_{period_key}"):
            cols = st.columns([2.2, 1, 1.35])
            cols[0].write(period_label(goal, period_start))
            status = _status_label(outcome)
            if row_state == "unfulfilled":
                cols[1].markdown(
                    f"<span class='history-repair-status-unfulfilled'>{status}</span>",
                    unsafe_allow_html=True,
                )
            else:
                cols[1].write(status)
            value_cols = cols[2].columns([1, 0.65], vertical_alignment="center")
            corrected_current = value_cols[0].number_input(
                "Value",
                min_value=0,
                value=current,
                step=1,
                key=f"history_repair_value_{row_state}_{goal['id']}_{period_key}",
                label_visibility="collapsed",
            )
            value_cols[1].caption(f"/ {target}")
        values[period_start] = (int(corrected_current), target, current)
    return values


def _readiness_gate_option() -> dict:
    option_id = st.session_state.get(READY_OPTION_SESSION_KEY)
    options_by_id = {option["id"]: option for option in READINESS_GATE_OPTIONS}
    if option_id not in options_by_id:
        option = random.choice(READINESS_GATE_OPTIONS)
        st.session_state[READY_OPTION_SESSION_KEY] = option["id"]
        return option
    return options_by_id[option_id]


def _render_readiness_gate() -> bool:
    if st.session_state.get(READY_SESSION_KEY):
        return True

    option = _readiness_gate_option()
    wait1_seconds = max(0, int(option.get("wait1_seconds", 0) or 0))
    wait2_seconds = max(0, int(option.get("wait2_seconds", 0) or 0))
    button_delay_seconds = wait1_seconds + wait2_seconds
    progress_seconds = option.get("progress_seconds")
    progress_html = ""
    if progress_seconds is not None:
        progress_html = (
            '<div class="history-repair-progress" aria-hidden="true">'
            '<div class="history-repair-progress-fill"></div>'
            '</div>'
        )

    with st.container(key="history_repair_gate"):
        st.markdown(
            f"""
            <style>
            div[class*="st-key-history_repair_gate"] {{
                --history-repair-wait-1: {wait1_seconds}s;
                --history-repair-button-delay: {button_delay_seconds}s;
                --history-repair-progress-duration: {max(1, int(progress_seconds or 1))}s;
            }}
            </style>
            <div class="history-repair-game">
                <p class="history-repair-warning">{option["sentence1_html"]}</p>
                <p class="history-repair-task">{option["sentence2_html"]}</p>
                {progress_html}
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            str(option.get("button_text", "Ready")),
            type="primary",
            use_container_width=True,
            key="history_repair_ready_button",
        ):
            st.session_state[READY_SESSION_KEY] = True
            st.rerun()
    return False


def render_historical_data_repair(
    persistence: Persistence,
    user_id: str,
    now: datetime | None = None,
) -> None:
    st.markdown(
        """
        <style>
        div[class*="st-key-history_repair_row_"] {
            padding: 0.35rem 0.5rem;
            margin: 0.25rem 0;
        }
        div[class*="st-key-history_repair_value_"] div[data-testid="InputInstructions"] {
            display: none;
        }
        .history-repair-status-unfulfilled {
            color: #be123c;
        }
        div[class*="st-key-history_repair_value_unfulfilled_"] input {
            background-color: #fff1f2;
            border-color: #fecdd3;
        }
        div[class*="st-key-history_repair_gate"] {
            min-height: 62vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }
        .history-repair-game {
            width: 100%;
            max-width: 34rem;
            margin: 0 auto;
            background: #ffffff;
        }
        .history-repair-warning {
            margin: 0 0 1rem;
            color: #6b7280;
            font-size: 0.92rem;
            text-align: center;
            opacity: 0;
            animation: history-repair-fade-in 0.8s ease forwards;
        }
        .history-repair-task {
            margin: 0 0 0.75rem;
            color: #1f2937;
            font-weight: 700;
            text-align: center;
            opacity: 0;
            animation: history-repair-fade-in 0.6s ease var(--history-repair-wait-1) forwards;
        }
        .history-repair-progress {
            width: 100%;
            height: 0.55rem;
            overflow: hidden;
            border-radius: 999px;
            background: #e5e7eb;
            box-shadow: inset 0 0 0 1px rgba(31, 41, 55, 0.08);
            opacity: 0;
            animation: history-repair-fade-in 0.6s ease var(--history-repair-wait-1) forwards;
        }
        .history-repair-progress-fill {
            width: 100%;
            height: 100%;
            transform-origin: left center;
            transform: scaleX(0);
            animation: history-repair-fill var(--history-repair-progress-duration) linear var(--history-repair-wait-1) forwards;
            background: #1f2937;
        }
        div[class*="st-key-history_repair_ready_button"] {
            width: 100%;
            max-width: 34rem;
            margin: 1rem auto 0;
            visibility: hidden;
            opacity: 0;
            pointer-events: none;
            animation: history-repair-ready-button 0.8s ease var(--history-repair-button-delay) forwards;
        }
        @keyframes history-repair-fade-in {
            to { opacity: 1; }
        }
        @keyframes history-repair-fill {
            to { transform: scaleX(1); }
        }
        @keyframes history-repair-ready-button {
            to {
                visibility: visible;
                opacity: 1;
                pointer-events: auto;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if not _render_readiness_gate():
        return

    st.title("Historical Data Repair")
    goals = [
        goal
        for goal in persistence.list_goals_for_user(user_id, now=now)
        if isinstance(goal.get("participants", {}).get(user_id), dict)
    ]
    if not goals:
        st.info("No active goals.")
        return

    st.caption(f"Repair older goal values for the last {LOOKBACK_PERIODS} completed periods.")
    descriptions = [str(goal.get("description", "Goal")) for goal in goals]
    duplicate_descriptions = {description for description in descriptions if descriptions.count(description) > 1}
    goal_options = {_goal_option_label(goal, duplicate_descriptions): goal for goal in goals}
    placeholder = "Please select one of your goals ..."
    selected_goal_label = st.selectbox(
        "Goal",
        [placeholder, *goal_options],
        key="historical_data_repair_goal_picker",
    )
    if selected_goal_label == placeholder:
        return

    goal = goal_options[selected_goal_label]
    participant = goal["participants"][user_id]

    with st.container(border=True):
        starts = editable_period_starts(goal, now=now)
        if not starts:
            st.caption("No completed periods are available for this goal yet.")
            return
        values = _render_period_inputs(goal, participant, starts)
        changed_values = {
            period_start: (current, target)
            for period_start, (current, target, original_current) in values.items()
            if current != original_current
        }
        submitted = st.button(
            "Save",
            type="primary",
            use_container_width=True,
            disabled=not changed_values,
            key=f"historical_data_repair_save_{goal['id']}",
        )
        if submitted:
            try:
                for period_start, (current, target) in changed_values.items():
                    persistence.correct_goal_period_progress(
                        goal["id"],
                        user_id,
                        period_start,
                        current,
                        target=target,
                        now=now,
                    )
                st.success("Historical data repaired.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))
