from __future__ import annotations

from datetime import datetime
from html import escape

import streamlit as st

from src.db.persistence import Persistence
from src.pages.account_page import render_activity_diagram
from src.pages.page_helpers import participant_name, progress_bar, schedule_label


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


def render_main(persistence: Persistence, current_user: dict, user_id: str, now: datetime | None = None) -> None:
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
                    name_cols = st.columns([2.4, 1.4, 6.2]) if can_invite_participant else st.columns([3.8, 6.2])
                    name_cols[0].write(participant_name(users, participant_id))
                    if can_invite_participant:
                        if name_cols[1].button("Add Friend", key=f"add_friend_{goal['id']}_{participant_id}"):
                            try:
                                persistence.create_friend_invite(user_id, current_user["email"], participant_email, now=now)
                                st.success("Friend invite sent.")
                                st.rerun()
                            except ValueError as error:
                                st.error(str(error))
                        name_cols[2].caption(f"{current} / {max(1, target)}")
                    else:
                        name_cols[1].caption(f"{current} / {max(1, target)}")
                    progress_bar(current, target, show_caption=False)
                if is_current_user:
                    with cols[1]:
                        action_cols = st.columns([1, 1])
                        if action_cols[0].button("Done", key=f"done_{goal['id']}", use_container_width=True):
                            persistence.update_goal_progress(
                                goal["id"],
                                user_id,
                                current=int(participant.get("target", 1)),
                                now=now,
                            )
                            st.rerun()
                        with action_cols[1].popover("...", use_container_width=True):
                            current_key = f"current_{goal['id']}"
                            current = st.number_input(
                                "Current",
                                min_value=0,
                                value=int(participant.get("current", 0)),
                                key=current_key,
                            )
                            detail_cols = st.columns(3)
                            if detail_cols[0].button("Save", key=f"save_{goal['id']}", use_container_width=True):
                                persistence.update_goal_progress(goal["id"], user_id, current=current, now=now)
                                st.rerun()
                            if detail_cols[1].button("+1", key=f"plus_{goal['id']}", use_container_width=True):
                                persistence.update_goal_progress(goal["id"], user_id, delta=1, now=now)
                                st.rerun()
                            if detail_cols[2].button("-1", key=f"minus_{goal['id']}", use_container_width=True):
                                persistence.update_goal_progress(goal["id"], user_id, delta=-1, now=now)
                                st.rerun()
