from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping

import streamlit as st

from src.db.persistence import APP_ZONE


@dataclass
class DebugMechanics:
    persistence: Any
    enabled: bool

    @classmethod
    def from_secrets(
        cls,
        persistence: Any,
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


def debug_now(persistence: Any, debug_mode: bool, now: datetime | None = None) -> datetime:
    server_now = _server_now(now)
    if not debug_mode or not hasattr(persistence, "debug_time_offset_seconds"):
        return server_now
    return server_now + timedelta(seconds=int(persistence.debug_time_offset_seconds()))


def render_debug(persistence: Any) -> None:
    st.title("Debug")
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
