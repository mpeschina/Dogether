"""Deferred user-information notifications for the Goals startup flow."""

from __future__ import annotations

import streamlit as st


NOTIFICATION_QUEUE_SESSION_KEY = "app_notifications:queue"
SHOWN_NOTIFICATION_KEYS_SESSION_KEY = "app_notifications:shown_keys"


def queue_user_notification(
    body: str,
    *,
    key: str | None = None,
    icon: str | None = None,
    duration: str | int = "short",
) -> bool:
    """Queue an automatic user-information notification for the next Goals render.

    A stable ``key`` makes a notification appear at most once per browser
    session. Omit it for repeatable notifications.
    """
    if key is not None and not key:
        raise ValueError("Notification keys must be non-empty when provided.")
    queue = st.session_state.setdefault(NOTIFICATION_QUEUE_SESSION_KEY, [])
    shown = st.session_state.setdefault(SHOWN_NOTIFICATION_KEYS_SESSION_KEY, set())
    if not isinstance(queue, list) or not isinstance(shown, set):
        raise RuntimeError("App notification session state has an invalid shape.")
    if key is not None and (
        key in shown or any(item.get("key") == key for item in queue if isinstance(item, dict))
    ):
        return False
    queue.append({"body": body, "key": key, "icon": icon, "duration": duration})
    return True


def clear_user_notification(key: str) -> None:
    """Allow a keyed user-information notification to be queued again."""
    queue = st.session_state.get(NOTIFICATION_QUEUE_SESSION_KEY, [])
    if isinstance(queue, list):
        st.session_state[NOTIFICATION_QUEUE_SESSION_KEY] = [
            item for item in queue if not isinstance(item, dict) or item.get("key") != key
        ]
    shown = st.session_state.get(SHOWN_NOTIFICATION_KEYS_SESSION_KEY)
    if isinstance(shown, set):
        shown.discard(key)


def flush_startup_notifications(*, viewport_ready: bool) -> int:
    """Show queued automatic notifications once the Goals viewport is ready."""
    queue = st.session_state.get(NOTIFICATION_QUEUE_SESSION_KEY, [])
    if not isinstance(queue, list) or not queue or not viewport_ready:
        return 0
    shown = st.session_state.setdefault(SHOWN_NOTIFICATION_KEYS_SESSION_KEY, set())
    if not isinstance(shown, set):
        raise RuntimeError("App notification session state has an invalid shape.")

    emitted = 0
    for item in queue:
        if not isinstance(item, dict):
            continue
        body = item.get("body")
        if not isinstance(body, str):
            continue
        st.toast(body, icon=item.get("icon"), duration=item.get("duration", "short"))
        key = item.get("key")
        if isinstance(key, str):
            shown.add(key)
        emitted += 1
    st.session_state[NOTIFICATION_QUEUE_SESSION_KEY] = []
    return emitted
