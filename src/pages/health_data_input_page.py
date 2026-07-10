from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
from urllib.parse import quote

import streamlit as st

from src.db.persistence import Persistence
from src.pages.page_helpers import schedule_label

DEFAULT_SHORTCUT_NAME = "Dogether Steps"
DEFAULT_SHORTCUT_INSTALL_URL = "https://www.icloud.com/shortcuts/e7e2d701ee3c4b65b76c2c5942dd0e52"
DEFAULT_RETURN_URL = "https://dogether.streamlit.app/"


def health_data_settings(secrets: Mapping[str, Any] | None = None) -> dict[str, str]:
    secrets = st.secrets if secrets is None else secrets
    config = secrets.get("health_data", {})
    return {
        "apple_steps_shortcut_install_url": str(
            config.get("apple_steps_shortcut_install_url", DEFAULT_SHORTCUT_INSTALL_URL)
        ),
        "apple_steps_shortcut_name": str(config.get("apple_steps_shortcut_name", DEFAULT_SHORTCUT_NAME)),
        "return_url": str(config.get("return_url", DEFAULT_RETURN_URL)),
    }


def apple_steps_shortcut_run_url(shortcut_name: str) -> str:
    return "shortcuts://run-shortcut?name=" + quote(shortcut_name)


def health_data_workflow_enabled(goal: dict, user_id: str) -> bool:
    participant = goal.get("participants", {}).get(user_id, {})
    workflow = participant.get("health_data_workflow", {})
    return bool(isinstance(workflow, dict) and workflow.get("enabled"))


def active_health_data_goal(goals: list[dict], user_id: str) -> dict | None:
    for goal in goals:
        if health_data_workflow_enabled(goal, user_id):
            return goal
    return None


def render_health_data_input(
    persistence: Persistence,
    user_id: str,
    *,
    settings: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> None:
    settings = dict(settings or health_data_settings())
    st.title("Health Data Input")

    goals = persistence.list_goals_for_user(user_id, now=now)
    if not goals:
        st.info("Create a goal before connecting Apple Health input.")
        return

    current_target = active_health_data_goal(goals, user_id)
    goal_options = {
        f"{goal['description']} ({schedule_label(goal)})": goal["id"]
        for goal in goals
    }
    goal_labels = list(goal_options)
    current_index = 0
    if current_target:
        current_index = next(
            (index for index, label in enumerate(goal_labels) if goal_options[label] == current_target["id"]),
            0,
        )

    with st.container(border=True):
        st.subheader("Apple Health Steps")
        if current_target:
            participant = current_target["participants"][user_id]
            st.success(f"Active target: {current_target['description']}")
            st.caption(f"Current progress: {participant.get('current', 0)} / {participant.get('target', 1)}")
        else:
            st.info("No goal is currently connected to Apple Health input.")

        selected_label = st.selectbox("Target goal", goal_labels, index=current_index)
        selected_goal_id = goal_options[selected_label]
        action_cols = st.columns(2)
        if action_cols[0].button("Activate for goal", type="primary", use_container_width=True):
            persistence.set_health_data_workflow_target(selected_goal_id, user_id, True, now=now)
            st.success("Apple Health input is active for this goal.")
            st.rerun()
        if action_cols[1].button(
            "Deactivate",
            disabled=current_target is None,
            use_container_width=True,
        ):
            persistence.set_health_data_workflow_target(None, user_id, False, now=now)
            st.success("Apple Health input is deactivated.")
            st.rerun()

    with st.container(border=True):
        st.subheader("Shortcut")
        install_url = settings.get("apple_steps_shortcut_install_url", "").strip()
        shortcut_name = (
            settings.get("apple_steps_shortcut_name", DEFAULT_SHORTCUT_NAME).strip()
            or DEFAULT_SHORTCUT_NAME
        )
        if install_url:
            st.link_button("Install Shortcut", install_url, use_container_width=True)
        else:
            st.warning(
                "Add health_data.apple_steps_shortcut_install_url to Streamlit secrets "
                "to show the install button."
            )
        st.link_button("Input Data", apple_steps_shortcut_run_url(shortcut_name), use_container_width=True)
        st.caption(
            f"Shortcut return URL: "
            f"{settings.get('return_url', DEFAULT_RETURN_URL)}?action=import_steps&steps=[steps]"
        )
