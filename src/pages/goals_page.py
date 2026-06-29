from __future__ import annotations

from datetime import datetime

import streamlit as st

from src.db.persistence import Persistence
from src.pages.page_helpers import schedule_label


def render_goals(persistence: Persistence, user_id: str, now: datetime | None = None) -> None:
    st.title("Create / Manage Shared Goals")
    friends = persistence.list_friends(user_id)
    friend_options = {f"{friend.get('name', friend['email'])} <{friend['email']}>": friend["user_id"] for friend in friends}

    with st.form("create_goal"):
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
            required_periods = st.number_input("X times per week", min_value=1, max_value=7, value=5)
        elif schedule_options[schedule_label_value] == "weekly_x_per_month":
            required_periods = st.number_input("X times per month", min_value=1, max_value=5, value=3)
        selected_friends = st.multiselect("Shared with friends", list(friend_options))
        target = st.number_input("Progress max", min_value=1, value=1)
        submitted = st.form_submit_button("Create goal")
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
    for goal in goals:
        participant = goal["participants"][user_id]
        cols = st.columns([4, 2, 2, 3, 1])
        cols[0].write(goal["description"])
        cols[1].write(schedule_label(goal))
        cols[2].write(f"{participant.get('current', 0)} / {participant.get('target', 1)}")
        existing_participant_ids = set(goal.get("participants", {}))
        addable_friend_options = {
            label: friend_id
            for label, friend_id in friend_options.items()
            if friend_id not in existing_participant_ids
        }
        if addable_friend_options:
            with cols[3].popover("Add Friends", use_container_width=True):
                with st.form(f"add_friends_{goal['id']}"):
                    selected_new_friends = st.multiselect("Friends", list(addable_friend_options))
                    add_submitted = st.form_submit_button("Add")
                    if add_submitted:
                        try:
                            if not selected_new_friends:
                                st.warning("Choose at least one friend to add.")
                            else:
                                persistence.add_goal_friends(
                                    goal_id=goal["id"],
                                    user_id=user_id,
                                    friend_user_ids=[addable_friend_options[label] for label in selected_new_friends],
                                    now=now,
                                )
                                st.success("Friends added.")
                                st.rerun()
                        except ValueError as error:
                            st.error(str(error))
        else:
            cols[3].caption("All friends are already on this goal.")
        pending_leave = st.session_state.get("goals_pending_leave_id") == goal["id"]
        leave_label = "Really Leave" if pending_leave else "Leave"
        leave_type = "primary" if pending_leave else "secondary"
        if cols[4].button(leave_label, key=f"leave_{goal['id']}", type=leave_type):
            if pending_leave:
                persistence.leave_goal(goal["id"], user_id, now=now)
                st.session_state.pop("goals_pending_leave_id", None)
            else:
                st.session_state["goals_pending_leave_id"] = goal["id"]
            st.rerun()
