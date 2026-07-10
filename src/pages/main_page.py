from __future__ import annotations

from datetime import datetime
from html import escape

import streamlit as st

from src.db.persistence import Persistence
from src.pages.account_page import render_activity_diagram
from src.pages.common_helpers import compact_goal_activity_html, mini_activity_styles
from src.pages.health_data_import_page import (
    apple_steps_shortcut_run_url,
    health_data_import_settings,
    health_data_import_enabled,
)
from src.pages.page_helpers import participant_name, progress_bar, schedule_label
from src.push.notifications import update_goal_progress_with_push
from src.push.storage import PushStorage


DONE_BUTTON_GREEN = "#2E9E57"
DONE_BUTTON_GREEN_HOVER = "#218243"
DONE_BUTTON_GREEN_ACTIVE = "#1b6d38"
PARTICIPANT_PROGRESS_COLOR = "rgba(49, 51, 63, 0.6)"
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


def visible_participant_ids(goal: dict, current_user_id: str, friend_ids: set[str]) -> list[str]:
    return [
        participant_id
        for participant_id in ordered_active_participant_ids(goal, current_user_id)
        if participant_id == current_user_id or participant_id in friend_ids
    ]


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
        {mini_activity_styles()}
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
            participant_ids = visible_participant_ids(goal, user_id, friend_ids)
            for participant_id in participant_ids:
                participant = goal["participants"][participant_id]
                current = int(participant.get("current", 0))
                target = int(participant.get("target", 1))
                skipped = bool(participant.get("skipped", False))
                is_current_user = participant_id == user_id
                cols = st.columns([6, 2])
                with cols[0]:
                    name = participant_name(users, participant_id)
                    progress_label = participant_progress_label(current, target, skipped)
                    st.markdown(
                        participant_name_with_progress_html(name, progress_label, goal, participant, now=now),
                        unsafe_allow_html=True,
                    )
                    if not skipped:
                        progress_bar(current, target, show_caption=False)
                if is_current_user:
                    with cols[1]:
                        action_cols = st.columns([1, 1])
                        goal_is_done = current >= max(1, target)
                        uses_health_data = health_data_import_enabled(goal, user_id)
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
                        elif uses_health_data:
                            shortcut_name = health_data_import_settings().get(
                                "apple_steps_shortcut_name", "Dogether Steps"
                            )
                            action_cols[0].link_button(
                                "Input Data",
                                apple_steps_shortcut_run_url(shortcut_name),
                                type="primary",
                                use_container_width=True,
                            )
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
                        if not (goal_is_done or skipped):
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
