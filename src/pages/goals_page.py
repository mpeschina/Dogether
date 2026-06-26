from __future__ import annotations

import streamlit as st

from src.pages.page_helpers import schedule_label


def render_goals(persistence, user_id: str) -> None:
    st.title("Create / Remove Shared Goals")
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
                )
                st.success("Goal created.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    st.subheader("Your active goals")
    goals = persistence.list_goals_for_user(user_id)
    if not goals:
        st.info("No active goals.")
    for goal in goals:
        participant = goal["participants"][user_id]
        cols = st.columns([4, 2, 2, 1])
        cols[0].write(goal["description"])
        cols[1].write(schedule_label(goal))
        cols[2].write(f"{participant.get('current', 0)} / {participant.get('target', 1)}")
        if cols[3].button("Leave", key=f"leave_{goal['id']}"):
            persistence.leave_goal(goal["id"], user_id)
            st.rerun()
