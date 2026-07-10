from __future__ import annotations

from datetime import datetime
from typing import Mapping

import streamlit as st

from src.db.persistence import Persistence
from src.pages.health_data_import_page import active_health_data_import_goal
from src.push.notifications import update_goal_progress_with_push
from src.push.storage import PushStorage


def handle_health_data_import(
    persistence: Persistence,
    user_id: str,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
    *,
    now: datetime | None = None,
) -> None:
    action = st.query_params.get("action")
    steps_param = st.query_params.get("steps")
    if action != "import_steps" or not steps_param:
        return

    try:
        steps = max(0, int(float(str(steps_param))))
    except (TypeError, ValueError):
        st.error("Invalid Apple Health step count.")
        st.query_params.clear()
        return

    goals = persistence.list_goals_for_user(user_id, now=now)
    target_goal = active_health_data_import_goal(goals, user_id)
    if not target_goal:
        st.warning("Apple Health import is not active for any goal.")
        st.query_params.clear()
        return

    try:
        update_goal_progress_with_push(
            persistence,
            push_storage,
            push_settings,
            goal_id=target_goal["id"],
            user_id=user_id,
            current=steps,
            now=now,
        )
        st.success(f"Received {steps:,} steps for {target_goal['description']}.")
    except Exception as error:
        st.error(f"Could not import Apple Health data: {error}")
    finally:
        st.query_params.clear()
