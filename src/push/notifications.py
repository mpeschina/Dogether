"""Application-level push notification hooks."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from src.db.persistence import Persistence
from src.db.persistence_helpers import normalize_email

from .sender import push_configured, send_push_to_user
from .storage import PushStorage


def create_friend_invite_with_push(
    persistence: Persistence,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
    *,
    from_user_id: str,
    from_email: str,
    to_email: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized_to_email = normalize_email(to_email)
    pending_before = {
        invite["id"]
        for invite in persistence.outgoing_friend_invites(from_user_id)
        if invite.get("to_email") == normalized_to_email
    }

    invite = persistence.create_friend_invite(from_user_id, from_email, to_email, now=now)
    if invite["id"] in pending_before:
        return invite

    recipient = persistence.find_user_by_email(normalized_to_email)
    if not recipient or not push_storage or not push_configured(push_settings):
        return invite

    send_push_to_user(
        push_storage,
        recipient["user_id"],
        title="New friend request",
        body="You have a new friend request in Dogether.",
        url="/",
        vapid_private_key=push_settings["vapid_private_key"],
        vapid_subject=push_settings["vapid_subject"],
    )
    return invite
