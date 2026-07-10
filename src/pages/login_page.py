from __future__ import annotations

from datetime import datetime
import uuid
from typing import Any

import streamlit as st

from src.db.persistence import Persistence, normalize_email


def login_screen(persistence: Persistence | None = None, debug_enabled: bool = False, now: datetime | None = None) -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"],
        [data-testid="collapsedControl"] {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not debug_enabled:
        st.markdown(
            """
            <style>
            .block-container {
                min-height: calc(100vh - 6rem);
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
            }

            .block-container > div {
                width: min(100%, 28rem);
            }

            .block-container h1,
            .block-container h2,
            .block-container h3,
            .block-container [data-testid="stButton"] {
                text-align: center;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    st.header("Dogether")
    st.button("Log in with Google", on_click=st.login, use_container_width=not debug_enabled)

    if not debug_enabled:
        return
    if persistence is None:
        st.error("Debug login requires persistence.")
        return

    st.divider()
    st.subheader("Debug login (only present when view = true is under [debug] in secrets.toml)")

    with st.form("debug_login_form"):
        email = st.text_input("Mail")
        name = st.text_input("Name")
        submitted = st.form_submit_button("Login or create User")

    if submitted:
        normalized_email = normalize_email(email)
        if not normalized_email or "@" not in normalized_email:
            st.error("Enter a valid email address.")
        else:
            existing = persistence.find_user_by_email(normalized_email)
            user = existing or persistence.upsert_user(f"debug_{uuid.uuid4().hex[:12]}", normalized_email, name, now=now)
            _log_in_debug_user(user)

    users = persistence.list_users()
    if users:
        st.caption("Existing users")
        for user in users:
            label = f"{user.get('name') or user['email']} <{user['email']}>"
            if st.button(label, key=f"debug_login_{user['user_id']}", use_container_width=True):
                _log_in_debug_user(user)


def _log_in_debug_user(user: dict[str, Any]) -> None:
    st.session_state["debug_user_id"] = user["user_id"]
    st.rerun()
