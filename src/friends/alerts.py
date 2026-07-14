from __future__ import annotations

from src.db.persistence import Persistence


def pending_friend_request_alert_items(
    persistence: Persistence,
    user_email: str,
    user_id: str,
) -> list[tuple[str, str]]:
    invites = [
        ("invite", invite["id"])
        for invite in persistence.incoming_friend_invites(user_email, user_id)
    ]
    suggestions = [
        ("suggestion", suggestion["id"])
        for suggestion in persistence.incoming_friend_suggestions(user_id)
    ]
    return invites + suggestions
