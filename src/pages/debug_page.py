from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import streamlit as st

from src.pages.account_page import reset_assistant_session_state
from src.db.persistence import APP_ZONE, Persistence
from src.db.persistence_helpers import debug_info_enabled
from src.push.sender import push_configured, send_push_to_user
from src.push.storage import PushStorage
from src.viewport_component import viewport_info


@dataclass
class DebugMechanics:
    persistence: Persistence
    enabled: bool

    @classmethod
    def from_secrets(
        cls,
        persistence: Persistence,
        secrets: Mapping[str, Any] | None = None,
    ) -> "DebugMechanics":
        return cls(
            persistence=persistence,
            enabled=debug_view_enabled(secrets),
        )

    @property
    def debug_login_enabled(self) -> bool:
        return self.enabled

    @property
    def effective_now(self) -> datetime:
        return debug_now(self.persistence, self.enabled)

    def current_debug_user(self) -> dict[str, Any] | None:
        if not self.debug_login_enabled:
            self.clear_debug_user()
            return None

        debug_user_id = st.session_state.get("debug_user_id")
        if not debug_user_id:
            return None

        debug_user = self.persistence.get_user(debug_user_id)
        if not debug_user:
            self.clear_debug_user()
            st.rerun()
        return debug_user

    def clear_debug_user(self) -> None:
        st.session_state.pop("debug_user_id", None)


def debug_view_enabled(secrets: Mapping[str, Any] | None = None) -> bool:
    secrets = st.secrets if secrets is None else secrets
    debug_config = secrets.get("debug", {})
    if isinstance(debug_config, Mapping):
        return _as_bool(debug_config.get("view", False))
    return False


def debug_now(persistence: Persistence, debug_mode: bool, now: datetime | None = None) -> datetime:
    server_now = _server_now(now)
    if not debug_mode:
        return server_now
    return server_now + timedelta(seconds=int(persistence.debug_time_offset_seconds()))


def render_debug(
    persistence: Persistence,
    push_storage: PushStorage | None = None,
    push_settings: Mapping[str, str] | None = None,
    *,
    current_user: Mapping[str, Any],
    user_id: str,
    now: datetime | None = None,
) -> None:
    if not debug_info_enabled(current_user):
        return

    st.title("Debug")
    flash = st.session_state.pop("debug_account_purge_flash", None)
    if flash:
        st.success(str(flash))
    offset_seconds = int(persistence.debug_time_offset_seconds())
    server_now = _server_now()
    effective_now = debug_now(persistence, True, server_now)

    cols = st.columns(3)
    cols[0].metric("Server time", server_now.strftime("%Y-%m-%d %H:%M"))
    cols[1].metric("Debug offset", _format_offset(offset_seconds))
    cols[2].metric("Effective time", effective_now.strftime("%Y-%m-%d %H:%M"))

    action_cols = st.columns(3)
    if action_cols[0].button("+1 hr", use_container_width=True):
        persistence.add_debug_time_offset(60 * 60)
        st.rerun()
    if action_cols[1].button("+1 day", use_container_width=True):
        persistence.add_debug_time_offset(24 * 60 * 60)
        st.rerun()
    if action_cols[2].button("Reset", use_container_width=True):
        persistence.reset_debug_time_offset()
        st.rerun()

    render_deployment_diagnostics()
    render_viewport_diagnostics()
    render_debug_push_notification(persistence, push_storage, push_settings or {})
    render_account_purge(persistence, push_storage, user_id, now=now)


def render_account_purge(
    persistence: Persistence,
    push_storage: PushStorage | None,
    user_id: str,
    *,
    now: datetime | None = None,
) -> None:
    """Render a deliberately explicit, session-scoped account purge control."""
    pending_key = "debug_account_purge_pending"
    nonce_key = "debug_account_purge_nonce"
    error_key = "debug_account_purge_error"

    def show_confirmation() -> None:
        st.session_state[pending_key] = True
        st.session_state.pop(error_key, None)

    def cancel_confirmation() -> None:
        st.session_state.pop(pending_key, None)
        st.session_state.pop(error_key, None)
        st.session_state[nonce_key] = int(st.session_state.get(nonce_key, 0)) + 1

    def submit_purge() -> None:
        nonce = int(st.session_state.get(nonce_key, 0))
        confirmation = str(st.session_state.get(f"debug_account_purge_confirmation_{nonce}", "")).strip()
        if confirmation != "clear account":
            st.session_state[error_key] = 'Enter exactly "clear account" to confirm the purge.'
            return
        if push_storage is None:
            st.session_state[error_key] = "Push subscription storage is unavailable; account was not reset."
            return
        try:
            push_storage.delete_subscriptions_for_user(user_id)
            persistence.purge_account(user_id, now=now)
        except Exception as error:
            st.session_state[error_key] = f"Account purge failed: {error}"
            return

        debug_user_id = st.session_state.get("debug_user_id")
        reset_assistant_session_state(st.session_state, user_id)
        for key in list(st.session_state):
            if key != "debug_user_id":
                st.session_state.pop(key, None)
        if debug_user_id:
            st.session_state["debug_user_id"] = debug_user_id
        st.session_state["debug_account_purge_flash"] = "Account reset to standard values."

    st.divider()
    st.subheader("Danger zone")
    st.warning("This permanently clears this account's app data, shared-account links, and push subscriptions.")
    if not st.session_state.get(pending_key):
        st.button("Full purge account", type="primary", key="debug_account_purge_start", on_click=show_confirmation)
        return

    st.write('Type `clear account` to permanently reset the currently logged-in account.')
    nonce = int(st.session_state.get(nonce_key, 0))
    st.text_input("Confirmation", key=f"debug_account_purge_confirmation_{nonce}")
    if error := st.session_state.get(error_key):
        st.error(str(error))
    submit_col, cancel_col = st.columns(2)
    submit_col.button("Submit purge", type="primary", use_container_width=True, key="debug_account_purge_submit", on_click=submit_purge)
    cancel_col.button("Cancel", use_container_width=True, key="debug_account_purge_cancel", on_click=cancel_confirmation)


def render_deployment_diagnostics() -> None:
    st.subheader("Deployment Diagnostics")
    rows = {
        "static serving": st.get_option("server.enableStaticServing"),
        ".streamlit/config.toml exists": Path(".streamlit/config.toml").exists(),
        "static/sw.js exists": Path("static/sw.js").exists(),
        "static/manifest.json exists": Path("static/manifest.json").exists(),
        "static/icon-192.png exists": Path("static/icon-192.png").exists(),
        "static/icon-512.png exists": Path("static/icon-512.png").exists(),
        "push component build exists": Path("src/push_component/frontend/build/index.html").exists(),
    }
    st.table([{"Check": key, "Value": value} for key, value in rows.items()])


def render_viewport_diagnostics() -> None:
    st.subheader("Viewport Diagnostics")
    viewport = viewport_info(require_ready=False)
    if viewport is None:
        st.info("Browser viewport information has not reported yet. Streamlit may rerun shortly.")
        return

    st.json(viewport)


def render_debug_push_notification(
    persistence: Persistence,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
) -> None:
    st.subheader("Push Notification")
    if not push_configured(push_settings):
        st.info("Push notifications are not configured for this deployment.")
        return
    if push_storage is None:
        st.info("Push notification storage is unavailable.")
        return

    with st.form("debug_push_notification"):
        email = st.text_input("Recipient email")
        title = st.text_input("Title", "Dogether debug")
        body = st.text_area("Body", "This is a debug push notification.")
        url = st.text_input("URL", "/")
        submitted = st.form_submit_button("Send push notification")

    if not submitted:
        return

    recipient = persistence.find_user_by_email(email)
    if not recipient:
        st.error("No Dogether user found for that email address.")
        return

    result = send_push_to_user(
        push_storage,
        recipient["user_id"],
        title=title.strip() or "Dogether debug",
        body=body.strip(),
        url=url.strip() or "/",
        vapid_private_key=push_settings["vapid_private_key"],
        vapid_subject=push_settings["vapid_subject"],
    )
    if result["sent"]:
        st.success(f"Sent {result['sent']} push notification(s) to {recipient['email']}.")
    elif result["removed"]:
        st.info("No active subscriptions remained; expired subscriptions were removed.")
    else:
        st.info("No active push subscriptions found for that user.")
    if result["errors"]:
        st.error("; ".join(result["errors"]))


def _server_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(APP_ZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=APP_ZONE)
    return now.astimezone(APP_ZONE)


def _format_offset(seconds: int) -> str:
    hours = max(0, seconds) // 3600
    days, remaining_hours = divmod(hours, 24)
    if days and remaining_hours:
        return f"{days}d {remaining_hours}h"
    if days:
        return f"{days}d"
    return f"{remaining_hours}h"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
