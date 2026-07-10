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


def create_friend_suggestion_with_push(
    persistence: Persistence,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
    *,
    suggested_by_user_id: str,
    suggested_user_ids: list[str],
    source_goal_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    suggested_pair = sorted(set(suggested_user_ids))
    pending_before = set()
    if len(suggested_pair) == 2:
        pending_before = {
            suggestion["id"]
            for suggestion in persistence.list_friend_suggestions_for_pair(*suggested_pair)
            if suggestion.get("status") == "pending"
        }

    suggestion = persistence.create_friend_suggestion(
        suggested_by_user_id,
        suggested_pair,
        source_goal_id=source_goal_id,
        now=now,
    )
    if suggestion["id"] in pending_before:
        return suggestion
    if not push_storage or not push_configured(push_settings):
        return suggestion

    users = persistence.users_by_ids([suggested_by_user_id, *suggestion["suggested_user_ids"]])
    suggester = users.get(suggested_by_user_id, {})
    suggester_name = suggester.get("name") or suggester.get("email") or "A friend"
    for recipient_id in suggestion["suggested_user_ids"]:
        other_id = next(
            user_id
            for user_id in suggestion["suggested_user_ids"]
            if user_id != recipient_id
        )
        other = users.get(other_id, {})
        other_name = other.get("name") or other.get("email") or "another friend"
        send_push_to_user(
            push_storage,
            recipient_id,
            title="New friend suggestion",
            body=f"{suggester_name} suggested you and {other_name} become friends in Dogether.",
            url="/",
            vapid_private_key=push_settings["vapid_private_key"],
            vapid_subject=push_settings["vapid_subject"],
        )
    return suggestion


def update_goal_progress_with_push(
    persistence: Persistence,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
    *,
    goal_id: str,
    user_id: str,
    current: int | None = None,
    target: int | None = None,
    delta: int = 0,
    skipped: bool | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    goal = persistence.update_goal_progress(
        goal_id,
        user_id,
        current=current,
        target=target,
        delta=delta,
        skipped=skipped,
        now=now,
    )
    event = goal.get("_notification_event")
    if not event or not push_storage or not push_configured(push_settings):
        return goal

    friend_ids = {friend["user_id"] for friend in persistence.list_friends(user_id)}
    participant_ids = [
        participant_id
        for participant_id in goal.get("participant_user_ids", [])
        if participant_id != user_id
        and participant_id in friend_ids
        and not goal.get("participants", {}).get(participant_id, {}).get("left_at")
        and goal.get("participants", {}).get(participant_id, {}).get("completion_notifications_enabled", True)
    ]
    if not participant_ids:
        return goal

    users = persistence.users_by_ids([user_id, *participant_ids])
    completed_by = users.get(user_id, {}).get("name") or users.get(user_id, {}).get("email") or "A friend"
    description = str(goal.get("description") or "a shared goal")
    completed_participant = goal.get("participants", {}).get(user_id, {})
    current_value = max(0, int(completed_participant.get("current", 0)))
    target_value = max(1, int(completed_participant.get("target", 1)))

    for participant_id in participant_ids:
        send_push_to_user(
            push_storage,
            participant_id,
            title="Shared goal completed",
            body=f"{completed_by} completed {description}: {current_value} / {target_value}.",
            url="/",
            vapid_private_key=push_settings["vapid_private_key"],
            vapid_subject=push_settings["vapid_subject"],
        )
    return goal
