from __future__ import annotations

import uuid
from typing import Any

import streamlit as st

from src.db.persistence import JsonPersistence, normalize_email


def login_screen(persistence: Any | None = None, json_mode: bool = False) -> None:
    st.header("Dogether")
    st.button("Log in with Google", on_click=st.login)

    if not json_mode or not isinstance(persistence, JsonPersistence):
        return

    st.divider()
    st.subheader("Debug login (only present in local dev mode)")

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
            user = existing or persistence.upsert_user(f"debug_{uuid.uuid4().hex[:12]}", normalized_email, name)
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
