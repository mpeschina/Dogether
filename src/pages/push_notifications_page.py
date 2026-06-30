from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Mapping

import streamlit as st

from push_component import push_subscribe
from src.push.sender import push_configured, send_push_to_user
from src.push.storage import PushStorage


def render_push_notifications(
    current_user: dict,
    user_id: str,
    push_storage: PushStorage | None = None,
    push_settings: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> None:
    st.title("Push Notifications")
    st.warning(
        "iPhone/iPad setup: open Dogether in Safari, use Share > Add to Home Screen, "
        "then open Dogether from the Home Screen before enabling notifications."
    )

    push_settings = push_settings or {}
    if not push_configured(push_settings):
        st.info("Push notifications are not configured for this deployment yet.")
        return
    if push_storage is None:
        st.info("Push notification storage is unavailable.")
        return

    value = push_subscribe(
        vapid_public_key=push_settings["vapid_public_key"],
        service_worker_url="/~/+/app/static/sw.js",
        key=f"push-subscribe-{user_id}",
    )

    if value:
        if value.get("ok") and value.get("subscription"):
            try:
                push_storage.save_subscription(
                    user_id,
                    current_user["email"],
                    value["subscription"],
                    user_agent=value.get("userAgent"),
                    now=now,
                )
                st.success("Push notifications are enabled for this device.")
            except ValueError as error:
                st.error(str(error))
        elif value.get("ok") and value.get("unsubscribe"):
            push_storage.delete_subscription(value.get("endpoint", ""))
            st.success("Push notifications are disabled for this device.")
        elif not value.get("ok"):
            st.error(value.get("error", "Could not update push notification settings."))

    render_subscribed_notifications(push_storage, user_id)

    if st.button("Send test notification", key="send_test_push"):
        result = send_push_to_user(
            push_storage,
            user_id,
            title="Dogether test",
            body="Push notifications are working.",
            url="/",
            vapid_private_key=push_settings["vapid_private_key"],
            vapid_subject=push_settings["vapid_subject"],
        )
        if result["sent"]:
            st.success(f"Sent {result['sent']} test notification(s).")
        elif result["removed"]:
            st.info("Removed expired push subscriptions. Enable notifications again on this device.")
        else:
            st.info("No active push subscriptions found for your account yet.")
        if result["errors"]:
            st.error("; ".join(result["errors"]))


def render_subscribed_notifications(push_storage: PushStorage, user_id: str) -> None:
    subscriptions = push_storage.subscriptions_for_user(user_id)

    st.subheader("Subscribed notifications")
    if not subscriptions:
        st.caption("No subscribed notifications yet.")
        return

    for index, subscription in enumerate(subscriptions, start=1):
        endpoint = str(subscription.get("endpoint", ""))
        key_hash = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:12]
        user_agent = str(subscription.get("user_agent") or "Unknown device")
        updated_at = str(subscription.get("updated_at") or subscription.get("created_at") or "")

        with st.container(border=True):
            cols = st.columns([4, 1])
            cols[0].write(f"Notification {index}")
            cols[0].caption(user_agent)
            if updated_at:
                cols[0].caption(f"Last updated: {updated_at}")
            cols[0].caption(endpoint)

            if cols[1].button("Remove", key=f"remove_push_subscription_{key_hash}", use_container_width=True):
                push_storage.delete_subscription(endpoint)
                st.success("Notification subscription removed.")
                st.rerun()
