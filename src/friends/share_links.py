from __future__ import annotations

from datetime import datetime
from typing import Any, MutableMapping

from src.db.persistence import Persistence


FRIEND_SHARE_QUERY_PARAM = "friend_share"
PENDING_FRIEND_SHARE_CODE_KEY = "pending_friend_share_code"
FRIEND_SHARE_MESSAGE_KEY = "friend_share_message"


def capture_friend_share_code(
    query_params: Any,
    session_state: MutableMapping[str, Any],
) -> str | None:
    share_code = str(query_params.get(FRIEND_SHARE_QUERY_PARAM) or "").strip()
    if not share_code:
        return None
    session_state[PENDING_FRIEND_SHARE_CODE_KEY] = share_code
    return share_code


def apply_pending_friend_share(
    persistence: Persistence,
    current_user: dict[str, Any],
    user_id: str,
    session_state: MutableMapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, str] | None:
    share_code = str(session_state.get(PENDING_FRIEND_SHARE_CODE_KEY) or "").strip()
    if not share_code:
        return None

    session_state.pop(PENDING_FRIEND_SHARE_CODE_KEY, None)
    owner = persistence.find_user_by_friend_share_code(share_code)
    if not owner:
        return _store_message(
            session_state,
            "warning",
            "That friend share link is no longer valid.",
        )

    owner_id = owner["user_id"]
    owner_name = _display_name(owner)
    if owner_id == user_id:
        return _store_message(
            session_state,
            "info",
            "That is your own friend share link.",
        )

    if any(friend["user_id"] == owner_id for friend in persistence.list_friends(user_id)):
        return _store_message(
            session_state,
            "info",
            f"You and {owner_name} are already friends.",
        )

    pending_before = _pending_invite_ids_between(persistence, current_user, user_id, owner)
    try:
        invite = persistence.create_friend_invite_to_user(
            user_id,
            current_user["email"],
            owner_id,
            now=now,
        )
    except ValueError as error:
        return _store_message(session_state, "warning", str(error))

    if invite["id"] in pending_before:
        return _store_message(
            session_state,
            "info",
            f"A friend invite with {owner_name} is already pending.",
        )

    return _store_message(
        session_state,
        "success",
        f"Friend invite sent to {owner_name}.",
    )


def pop_friend_share_message(session_state: MutableMapping[str, Any]) -> dict[str, str] | None:
    message = session_state.pop(FRIEND_SHARE_MESSAGE_KEY, None)
    return message if isinstance(message, dict) else None


def _pending_invite_ids_between(
    persistence: Persistence,
    current_user: dict[str, Any],
    user_id: str,
    owner: dict[str, Any],
) -> set[str]:
    owner_id = owner["user_id"]
    owner_email = owner.get("email", "")
    pending_ids = {
        invite["id"]
        for invite in persistence.outgoing_friend_invites(user_id)
        if invite.get("to_user_id") == owner_id or invite.get("to_email") == owner_email
    }
    pending_ids.update(
        invite["id"]
        for invite in persistence.incoming_friend_invites(current_user["email"], user_id)
        if invite.get("from_user_id") == owner_id
    )
    return pending_ids


def _store_message(
    session_state: MutableMapping[str, Any],
    level: str,
    text: str,
) -> dict[str, str]:
    message = {"level": level, "text": text}
    session_state[FRIEND_SHARE_MESSAGE_KEY] = message
    return message


def _display_name(user: dict[str, Any]) -> str:
    return str(user.get("name") or user.get("email") or "that user")
