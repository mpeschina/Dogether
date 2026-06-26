from __future__ import annotations

import streamlit as st

from src.pages.page_helpers import participant_name, progress_bar, schedule_label


def render_main(persistence, user_id: str) -> None:
    stats = persistence.account_stats(user_id)
    metric_cols = st.columns(4)
    metric_cols[0].metric("Active goals", stats["active_goals"])
    metric_cols[1].metric("Friends", stats["friend_count"])
    metric_cols[2].metric("Completed periods", stats["completed_periods"])
    metric_cols[3].metric("Completion rate", f"{stats['completion_rate']}%")

    goals = persistence.list_goals_for_user(user_id)
    if not goals:
        st.info("Create a shared goal with a friend to get started.")
        return

    all_participant_ids = sorted({uid for goal in goals for uid in goal.get("participants", {})})
    users = persistence.users_by_ids(all_participant_ids)
    for goal in goals:
        st.subheader(goal["description"])
        st.caption(schedule_label(goal))
        participant_ids = [
            uid
            for uid in goal.get("participant_user_ids", [])
            if not goal.get("participants", {}).get(uid, {}).get("left_at")
        ]
        for participant_id in participant_ids:
            participant = goal["participants"][participant_id]
            cols = st.columns([2, 3, 4])
            cols[0].write(participant_name(users, participant_id))
            with cols[1]:
                progress_bar(int(participant.get("current", 0)), int(participant.get("target", 1)))
            if participant_id == user_id:
                with cols[2]:
                    current_key = f"current_{goal['id']}"
                    current = st.number_input(
                        "Current",
                        min_value=0,
                        value=int(participant.get("current", 0)),
                        key=current_key,
                    )
                    action_cols = st.columns(4)
                    if action_cols[0].button("Save", key=f"save_{goal['id']}"):
                        persistence.update_goal_progress(goal["id"], user_id, current=current)
                        st.rerun()
                    if action_cols[1].button("+1", key=f"plus_{goal['id']}"):
                        persistence.update_goal_progress(goal["id"], user_id, delta=1)
                        st.rerun()
                    if action_cols[2].button("-1", key=f"minus_{goal['id']}"):
                        persistence.update_goal_progress(goal["id"], user_id, delta=-1)
                        st.rerun()
                    if action_cols[3].button("Done", key=f"done_{goal['id']}"):
                        persistence.update_goal_progress(
                            goal["id"],
                            user_id,
                            current=int(participant.get("target", 1)),
                        )
                        st.rerun()
        st.divider()
