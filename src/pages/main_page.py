from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from html import escape

import streamlit as st

from src.db.persistence import Persistence
from src.db.persistence_helpers import _now, _period_fulfilled, _period_start, _schedule
from src.pages.account_page import render_activity_diagram
from src.pages.page_helpers import participant_name, progress_bar, schedule_label
from src.push.notifications import create_friend_invite_with_push, update_goal_progress_with_push
from src.push.storage import PushStorage


DONE_BUTTON_GREEN = "#2E9E57"
DONE_BUTTON_GREEN_HOVER = "#218243"
DONE_BUTTON_GREEN_ACTIVE = "#1b6d38"
PARTICIPANT_PROGRESS_COLOR = "rgba(49, 51, 63, 0.6)"
MINI_ACTIVITY_COLORS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
STREAMLIT_PRIMARY_COLOR = "#1F2937"
X_PER_SCHEDULE_CLASSES = {"daily_x_per_week", "weekly_x_per_month"}
MINI_ACTIVITY_NAME_MAX_LENGTH = 25


def ordered_active_participant_ids(goal: dict, current_user_id: str) -> list[str]:
    participants = goal.get("participants", {})
    ordered_ids = [
        uid
        for uid in goal.get("participant_user_ids", [])
        if uid in participants and not participants.get(uid, {}).get("left_at")
    ]
    ordered_id_set = set(ordered_ids)
    ordered_ids.extend(
        sorted(
            uid
            for uid, participant in participants.items()
            if uid not in ordered_id_set and not participant.get("left_at")
        )
    )
    if current_user_id not in ordered_ids:
        return ordered_ids
    return [current_user_id, *[uid for uid in ordered_ids if uid != current_user_id]]


def participant_progress_label(current: int, target: int, skipped: bool) -> str:
    if skipped:
        return "skipped"
    return f"{current}/{max(1, target)}"


def truncate_participant_name(name: str, max_length: int = MINI_ACTIVITY_NAME_MAX_LENGTH) -> str:
    if len(name) <= max_length:
        return name
    return f"{name[: max(0, max_length - 3)]}..."


def participant_name_with_progress_html(
    name: str,
    progress_label: str,
    goal: dict | None = None,
    participant: dict | None = None,
    now: datetime | None = None,
) -> str:
    dots_html = (
        compact_goal_activity_html(goal, participant, now=now)
        if goal is not None and participant is not None
        else ""
    )
    return (
        "<div class='participant-progress-row'>"
        f"<span class='participant-progress-name' title='{escape(name, quote=True)}'>"
        f"{escape(truncate_participant_name(name))}</span>"
        f"<span class='participant-progress-count'>{escape(progress_label)}</span>"
        f"{dots_html}"
        "</div>"
    )


def compact_goal_activity_html(goal: dict, participant: dict, now: datetime | None = None) -> str:
    now_dt = _now(now)
    schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
    period_starts = _mini_activity_period_starts(now_dt, schedule)
    current_period_start = _period_start(now_dt, schedule["base"])
    dots = [
        (
            f"<span class='{_mini_activity_dot_class(period_start, current_period_start)}' "
            f"title='{escape(period_start.isoformat(), quote=True)}' "
            f"style='background:{_mini_activity_color(goal, participant, period_start, now_dt)};'></span>"
        )
        for period_start in period_starts
    ]
    return f"<span class='mini-activity-dots'>{''.join(dots)}</span>"


def _mini_activity_dot_class(period_start: datetime, current_period_start: datetime) -> str:
    class_name = "mini-activity-dot"
    if period_start == current_period_start:
        class_name += " mini-activity-dot-current"
    return class_name


def _mini_activity_period_starts(now_dt: datetime, schedule: dict) -> list[datetime]:
    if schedule["base"] == "day":
        week_start = _period_start(now_dt, "week")
        return [week_start + timedelta(days=offset) for offset in range(7)]

    month_start = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _, month_days = calendar.monthrange(month_start.year, month_start.month)
    return [
        month_start + timedelta(days=day_offset)
        for day_offset in range(month_days)
        if (month_start + timedelta(days=day_offset)).weekday() == 0
    ]


def _mini_activity_color(goal: dict, participant: dict, period_start: datetime, now_dt: datetime) -> str:
    schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
    current_period_start = _period_start(now_dt, schedule["base"])
    if period_start > current_period_start:
        return MINI_ACTIVITY_COLORS[0]

    outcome = participant.get("period_outcomes", {}).get(period_start.date().isoformat())
    if isinstance(outcome, dict):
        completed = bool(outcome.get("completed", False))
        fulfilled = bool(outcome.get("fulfilled", completed))
        if completed:
            return MINI_ACTIVITY_COLORS[4]
        if _uses_required_period_allowance(goal):
            if fulfilled and outcome.get("skipped"):
                return STREAMLIT_PRIMARY_COLOR
            if not fulfilled:
                return MINI_ACTIVITY_COLORS[0]
        if fulfilled:
            return MINI_ACTIVITY_COLORS[4]
        return _mini_activity_progress_color(_outcome_percent(outcome))

    if period_start == current_period_start:
        fulfilled = _period_fulfilled(goal, participant, period_start)
        skipped = bool(participant.get("skipped", False))
        if _uses_required_period_allowance(goal):
            if fulfilled and skipped:
                return STREAMLIT_PRIMARY_COLOR
            if not fulfilled:
                return MINI_ACTIVITY_COLORS[0]
        if skipped and not fulfilled:
            return MINI_ACTIVITY_COLORS[0]
        if fulfilled:
            return MINI_ACTIVITY_COLORS[4]
        target = max(1, int(participant.get("target", 1) or 1))
        current = max(0, int(participant.get("current", 0) or 0))
        return _mini_activity_progress_color((current / target) * 100)

    return MINI_ACTIVITY_COLORS[0]


def _uses_required_period_allowance(goal: dict) -> bool:
    return goal.get("schedule_class") in X_PER_SCHEDULE_CLASSES


def _outcome_percent(outcome: dict) -> float:
    if "percent" in outcome:
        return max(0.0, float(outcome.get("percent") or 0.0))
    target = max(1, int(outcome.get("target", 1) or 1))
    current = max(0, int(outcome.get("current", 0) or 0))
    return (current / target) * 100


def _mini_activity_progress_color(percent: float) -> str:
    if percent >= 100:
        return MINI_ACTIVITY_COLORS[4]
    if percent >= 75:
        return MINI_ACTIVITY_COLORS[3]
    if percent >= 50:
        return MINI_ACTIVITY_COLORS[2]
    if percent > 0:
        return MINI_ACTIVITY_COLORS[1]
    return MINI_ACTIVITY_COLORS[0]


def render_main(
    persistence: Persistence,
    current_user: dict,
    user_id: str,
    push_storage: PushStorage | None = None,
    push_settings: dict[str, str] | None = None,
    now: datetime | None = None,
) -> None:
    st.markdown(
        f"""
        <style>
        div[class*="st-key-done_"] button {{
            background-color: {DONE_BUTTON_GREEN};
            border-color: {DONE_BUTTON_GREEN};
            color: #ffffff;
        }}
        div[class*="st-key-done_"] button:hover {{
            background-color: {DONE_BUTTON_GREEN_HOVER};
            border-color: {DONE_BUTTON_GREEN_HOVER};
            color: #ffffff;
        }}
        div[class*="st-key-done_"] button:active {{
            background-color: {DONE_BUTTON_GREEN_ACTIVE};
            border-color: {DONE_BUTTON_GREEN_ACTIVE};
            color: #ffffff;
        }}
        .participant-progress-row {{
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto auto;
            align-items: baseline;
            column-gap: 0.4rem;
            margin: 0.15rem 0;
            min-width: 0;
            white-space: nowrap;
        }}
        .participant-progress-name {{
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .participant-progress-count {{
            color: {PARTICIPANT_PROGRESS_COLOR};
            font-size: 0.875rem;
        }}
        .mini-activity-dots {{
            display: inline-flex;
            align-items: center;
            gap: 3px;
            white-space: nowrap;
        }}
        .mini-activity-dot {{
            width: 8px;
            height: 8px;
            border-radius: 2px;
            box-shadow: inset 0 0 0 1px rgba(27,31,36,0.06);
            flex: 0 0 auto;
        }}
        .mini-activity-dot-current {{
            box-shadow: 0 0 0 1.5px rgba(31,41,55,0.42);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    stats = persistence.account_stats(user_id, now=now)
    render_activity_diagram(stats.get("activity_days", {}), now=now, days=90)

    goals = persistence.list_goals_for_user(user_id, now=now)
    if not goals:
        st.info("Create a shared goal with a friend to get started.")
        return

    all_participant_ids = sorted({uid for goal in goals for uid in goal.get("participants", {})})
    users = persistence.users_by_ids(all_participant_ids)
    friend_ids = {friend["user_id"] for friend in persistence.list_friends(user_id)}
    for goal in goals:
        with st.container(border=True):
            st.markdown(
                (
                    "<div style='display:flex;align-items:baseline;gap:0.65rem;"
                    "flex-wrap:wrap;margin:0.15rem 0 0.65rem;'>"
                    f"<h3 style='margin:0;'>{escape(goal['description'])}</h3>"
                    "<span style='color:#6b7280;font-size:0.86rem;'>"
                    f"{escape(schedule_label(goal))}"
                    "</span>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            participant_ids = ordered_active_participant_ids(goal, user_id)
            for participant_id in participant_ids:
                participant = goal["participants"][participant_id]
                current = int(participant.get("current", 0))
                target = int(participant.get("target", 1))
                skipped = bool(participant.get("skipped", False))
                is_current_user = participant_id == user_id
                participant_user = users.get(participant_id, {})
                participant_email = participant_user.get("email")
                can_invite_participant = (
                    participant_id != user_id
                    and participant_id not in friend_ids
                    and bool(participant_email)
                )
                cols = st.columns([6, 2])
                with cols[0]:
                    name = participant_name(users, participant_id)
                    progress_label = participant_progress_label(current, target, skipped)
                    name_cols = st.columns([2.4, 1.4]) if can_invite_participant else st.columns([1])
                    name_cols[0].markdown(
                        participant_name_with_progress_html(name, progress_label, goal, participant, now=now),
                        unsafe_allow_html=True,
                    )
                    if can_invite_participant:
                        if name_cols[1].button("Add Friend", key=f"add_friend_{goal['id']}_{participant_id}"):
                            try:
                                create_friend_invite_with_push(
                                    persistence,
                                    push_storage,
                                    push_settings or {},
                                    from_user_id=user_id,
                                    from_email=current_user["email"],
                                    to_email=participant_email,
                                    now=now,
                                )
                                st.success("Friend invite sent.")
                                st.rerun()
                            except ValueError as error:
                                st.error(str(error))
                    if not skipped:
                        progress_bar(current, target, show_caption=False)
                if is_current_user:
                    with cols[1]:
                        action_cols = st.columns([1, 1])
                        goal_is_done = current >= max(1, target)
                        if goal_is_done or skipped:
                            if action_cols[0].button("Reset", key=f"reset_{goal['id']}", use_container_width=True):
                                update_goal_progress_with_push(
                                    persistence,
                                    push_storage,
                                    push_settings or {},
                                    goal_id=goal["id"],
                                    user_id=user_id,
                                    current=0,
                                    skipped=False,
                                    now=now,
                                )
                                st.rerun()
                        elif action_cols[0].button(
                            "Done",
                            key=f"done_{goal['id']}",
                            type="primary",
                            use_container_width=True,
                        ):
                            update_goal_progress_with_push(
                                persistence,
                                push_storage,
                                push_settings or {},
                                goal_id=goal["id"],
                                user_id=user_id,
                                current=max(1, target),
                                now=now,
                            )
                            st.rerun()
                        with action_cols[1].popover("Set", use_container_width=True):
                            current_key = f"current_{goal['id']}"
                            current = st.number_input(
                                "Current",
                                min_value=0,
                                value=int(participant.get("current", 0)),
                                key=current_key,
                            )
                            detail_cols = st.columns(3)
                            if detail_cols[0].button("Save", key=f"save_{goal['id']}", use_container_width=True):
                                update_goal_progress_with_push(
                                    persistence,
                                    push_storage,
                                    push_settings or {},
                                    goal_id=goal["id"],
                                    user_id=user_id,
                                    current=current,
                                    now=now,
                                )
                                st.rerun()
                            if detail_cols[1].button("+1", key=f"plus_{goal['id']}", use_container_width=True):
                                update_goal_progress_with_push(
                                    persistence,
                                    push_storage,
                                    push_settings or {},
                                    goal_id=goal["id"],
                                    user_id=user_id,
                                    delta=1,
                                    now=now,
                                )
                                st.rerun()
                            if detail_cols[2].button("-1", key=f"minus_{goal['id']}", use_container_width=True):
                                update_goal_progress_with_push(
                                    persistence,
                                    push_storage,
                                    push_settings or {},
                                    goal_id=goal["id"],
                                    user_id=user_id,
                                    delta=-1,
                                    now=now,
                                )
                                st.rerun()
                            if st.button("Skip", key=f"skip_{goal['id']}", use_container_width=True):
                                update_goal_progress_with_push(
                                    persistence,
                                    push_storage,
                                    push_settings or {},
                                    goal_id=goal["id"],
                                    user_id=user_id,
                                    skipped=True,
                                    now=now,
                                )
                                st.rerun()
