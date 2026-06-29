"""Send Web Push notifications."""
from __future__ import annotations

import json
from typing import Any, Mapping

import streamlit as st

from .storage import PushStorage


def push_config(secrets: Mapping[str, Any] | None = None) -> dict[str, str]:
    secrets = st.secrets if secrets is None else secrets
    push = secrets.get("push", {})
    return {
        "vapid_public_key": str(push.get("vapid_public_key", "")),
        "vapid_private_key": str(push.get("vapid_private_key", "")),
        "vapid_subject": str(push.get("vapid_subject", "")),
    }


def push_configured(config: Mapping[str, str]) -> bool:
    return bool(
        config.get("vapid_public_key")
        and config.get("vapid_private_key")
        and config.get("vapid_subject")
    )


def send_push(
    *,
    subscription: dict[str, Any],
    title: str,
    body: str,
    url: str,
    vapid_private_key: str,
    vapid_subject: str,
) -> None:
    from pywebpush import webpush

    webpush(
        subscription_info=subscription,
        data=json.dumps({"title": title, "body": body, "url": url}),
        vapid_private_key=vapid_private_key,
        vapid_claims={"sub": vapid_subject},
    )


def send_push_to_user(
    push_storage: PushStorage,
    user_id: str,
    title: str,
    body: str,
    url: str = "/",
    *,
    vapid_private_key: str,
    vapid_subject: str,
) -> dict[str, Any]:
    from pywebpush import WebPushException

    sent = 0
    removed = 0
    errors = []

    for record in push_storage.subscriptions_for_user(user_id):
        try:
            send_push(
                subscription=record["subscription"],
                title=title,
                body=body,
                url=url,
                vapid_private_key=vapid_private_key,
                vapid_subject=vapid_subject,
            )
            sent += 1
        except WebPushException as error:
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            if status_code in (404, 410):
                push_storage.delete_subscription(record["endpoint"])
                removed += 1
            else:
                errors.append(str(error))

    return {"sent": sent, "removed": removed, "errors": errors}
