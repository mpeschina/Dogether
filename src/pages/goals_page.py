from __future__ import annotations

from datetime import datetime

import streamlit as st

from src.db.persistence import Persistence
from src.pages.page_helpers import schedule_label


def _addable_friend_options(goal: dict, friend_options: dict[str, str]) -> dict[str, str]:
    existing_participant_ids = set(goal.get("participants", {}))
    return {
        label: friend_id
        for label, friend_id in friend_options.items()
        if friend_id not in existing_participant_ids
    }


def _render_goal_summary(
    persistence: Persistence,
    goal: dict,
    user_id: str,
    participant: dict,
    now: datetime | None,
) -> None:
    summary_cols = st.columns([3, 1.6, 1.2])
    summary_cols[0].write(goal["description"])
    summary_cols[1].write(schedule_label(goal))
    with summary_cols[2]:
        _render_goal_notifications(persistence, goal, user_id, participant, now)


def _render_goal_notifications(
    persistence: Persistence,
    goal: dict,
    user_id: str,
    participant: dict,
    now: datetime | None,
) -> None:
    notifications_enabled = bool(participant.get("completion_notifications_enabled", True))
    selected_notifications_enabled = st.toggle(
        "Notify me when others complete",
        value=notifications_enabled,
        key=f"completion_notifications_{goal['id']}",
    )
    if selected_notifications_enabled != notifications_enabled:
        persistence.set_goal_completion_notifications(
            goal["id"],
            user_id,
            selected_notifications_enabled,
            now=now,
        )
        st.rerun()


def _render_goal_reaction_notifications(
    persistence: Persistence,
    goal: dict,
    user_id: str,
    participant: dict,
    now: datetime | None,
) -> None:
    notifications_enabled = bool(participant.get("reaction_notifications_enabled", True))
    selected_notifications_enabled = st.toggle(
        "Notify me on emote reactions",
        value=notifications_enabled,
        key=f"reaction_notifications_{goal['id']}",
    )
    if selected_notifications_enabled != notifications_enabled:
        persistence.set_goal_reaction_notifications(
            goal["id"],
            user_id,
            selected_notifications_enabled,
            now=now,
        )
        st.rerun()


def _render_goal_notification_limit(
    persistence: Persistence,
    goal: dict,
    user_id: str,
    participant: dict,
    now: datetime | None,
) -> None:
    current_limit = max(1, int(participant.get("completion_notifications_max_per_day", 3) or 3))
    with st.popover("Max completion notifications/day", use_container_width=True):
        with st.form(f"configure_notification_limit_{goal['id']}"):
            selected_limit = st.number_input(
                "Max push notifications/day",
                min_value=1,
                value=current_limit,
                step=1,
                key=f"completion_notifications_limit_{goal['id']}",
            )
            if st.form_submit_button("Save"):
                persistence.set_goal_completion_notification_limit(
                    goal["id"],
                    user_id,
                    int(selected_limit),
                    now=now,
                )
                st.success("Max push notifications updated.")
                st.rerun()


def _render_configure_max_value(
    persistence: Persistence,
    goal: dict,
    user_id: str,
    participant: dict,
    now: datetime | None,
) -> None:
    with st.popover("Max value", use_container_width=True):
        with st.form(f"configure_max_value_{goal['id']}"):
            target = st.number_input(
                "Max value",
                min_value=1,
                value=max(1, int(participant.get("target", 1))),
            )
            if st.form_submit_button("Save"):
                persistence.update_goal_progress(
                    goal["id"],
                    user_id,
                    target=int(target),
                    now=now,
                )
                st.success("Max value updated.")
                st.rerun()


def _render_add_goal_friends(
    persistence: Persistence,
    goal: dict,
    user_id: str,
    addable_friend_options: dict[str, str],
    now: datetime | None,
) -> None:
    if not addable_friend_options:
        st.caption("All friends are already on this goal.")
        return

    with st.form(f"add_friends_{goal['id']}", border=False):
        selected_new_friends = st.multiselect(
            "Friends",
            list(addable_friend_options),
            key=f"add_friends_select_{goal['id']}",
        )
        add_submitted = st.form_submit_button("Add")
        if add_submitted:
            try:
                if not selected_new_friends:
                    st.warning("Choose at least one friend to add.")
                else:
                    persistence.add_goal_friends(
                        goal_id=goal["id"],
                        user_id=user_id,
                        friend_user_ids=[
                            addable_friend_options[label]
                            for label in selected_new_friends
                        ],
                        now=now,
                    )
                    st.success("Friends added.")
                    st.rerun()
            except ValueError as error:
                st.error(str(error))


def _render_leave_goal(
    persistence: Persistence,
    goal: dict,
    user_id: str,
    now: datetime | None,
) -> None:
    pending_leave = st.session_state.get("goals_pending_leave_id") == goal["id"]
    leave_label = "Really Leave" if pending_leave else "Leave"
    leave_type = "primary" if pending_leave else "secondary"
    if st.button(
        leave_label,
        key=f"leave_{goal['id']}",
        type=leave_type,
        use_container_width=True,
    ):
        if pending_leave:
            persistence.leave_goal(goal["id"], user_id, now=now)
            st.session_state.pop("goals_pending_leave_id", None)
        else:
            st.session_state["goals_pending_leave_id"] = goal["id"]
        st.rerun()


def _render_active_goal(
    persistence: Persistence,
    goal: dict,
    user_id: str,
    friend_options: dict[str, str],
    now: datetime | None,
) -> None:
    participant = goal["participants"][user_id]
    with st.container(border=True):
        _render_goal_summary(persistence, goal, user_id, participant, now)
        with st.expander("Show Controls", expanded=False):
            control_cols = st.columns([1.4, 1.6, 1])
            with control_cols[0]:
                _render_configure_max_value(persistence, goal, user_id, participant, now)
            with control_cols[1]:
                _render_goal_notification_limit(persistence, goal, user_id, participant, now)
                _render_goal_reaction_notifications(persistence, goal, user_id, participant, now)
            with control_cols[2]:
                _render_leave_goal(persistence, goal, user_id, now)
            _render_add_goal_friends(
                persistence,
                goal,
                user_id,
                _addable_friend_options(goal, friend_options),
                now,
            )


def render_goals(persistence: Persistence, user_id: str, now: datetime | None = None) -> None:
    st.markdown(
        """
        <style>
        .goals-mobile-separator {
            display: none;
        }
        @media (max-width: 640px) {
            .goals-mobile-separator {
                display: block;
                border: 0;
                border-top: 1px solid #e5e7eb;
                margin: 1rem 0;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Create / Manage Shared Goals")
    friends = persistence.list_friends(user_id)
    friend_options = {f"{friend.get('name', friend['email'])} <{friend['email']}>": friend["user_id"] for friend in friends}

    with st.container(border=True):
        description = st.text_input("Task description")
        schedule_options = {
            "Daily": "daily",
            "Weekly": "weekly",
            "Daily with X per week": "daily_x_per_week",
            "Weekly with X per month": "weekly_x_per_month",
        }
        schedule_label_value = st.selectbox("Class", list(schedule_options))
        required_periods = 1
        if schedule_options[schedule_label_value] == "daily_x_per_week":
            required_periods = st.number_input("X times per week", min_value=1, max_value=6, value=5)
        elif schedule_options[schedule_label_value] == "weekly_x_per_month":
            required_periods = st.number_input("X times per month", min_value=1, max_value=6, value=3)
        selected_friends = st.multiselect("Shared with friends", list(friend_options))
        target = st.number_input("Progress max", min_value=1, value=1)
        submitted = st.button("Create goal", type="primary")
        if submitted:
            try:
                persistence.create_goal(
                    created_by=user_id,
                    description=description,
                    schedule_class=schedule_options[schedule_label_value],
                    required_periods=int(required_periods),
                    friend_user_ids=[friend_options[label] for label in selected_friends],
                    target=int(target),
                    current=int(0),
                    now=now,
                )
                st.success("Goal created.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    st.subheader("Your active goals")
    goals = persistence.list_goals_for_user(user_id, now=now)
    if not goals:
        st.info("No active goals.")
    active_goal_ids = {goal["id"] for goal in goals}
    if st.session_state.get("goals_pending_leave_id") not in active_goal_ids:
        st.session_state.pop("goals_pending_leave_id", None)
    for goal_index, goal in enumerate(goals):
        _render_active_goal(persistence, goal, user_id, friend_options, now)
        if goal_index < len(goals) - 1:
            st.markdown('<hr class="goals-mobile-separator">', unsafe_allow_html=True)
