from datetime import datetime
from pathlib import Path

from src.db.persistence import JsonPersistence
from src.friends.share_links import (
    FRIEND_SHARE_MESSAGE_KEY,
    FRIEND_SHARE_QUERY_PARAM,
    PENDING_FRIEND_SHARE_CODE_KEY,
    apply_pending_friend_share,
    capture_friend_share_code,
    pop_friend_share_message,
)


def at(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_capture_friend_share_code_persists_login_intent() -> None:
    session_state = {}

    captured = capture_friend_share_code({FRIEND_SHARE_QUERY_PARAM: " share_123 "}, session_state)

    assert captured == "share_123"
    assert session_state[PENDING_FRIEND_SHARE_CODE_KEY] == "share_123"


def test_share_link_applies_after_first_login(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    share_code = persistence.ensure_friend_share_code(alice["user_id"], at("2026-06-01T09:01:00"))
    session_state = {}

    capture_friend_share_code({FRIEND_SHARE_QUERY_PARAM: share_code}, session_state)
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob", at("2026-06-01T09:02:00"))
    result = apply_pending_friend_share(
        persistence,
        bob,
        bob["user_id"],
        session_state,
        now=at("2026-06-01T09:03:00"),
    )

    invites = persistence.incoming_friend_invites(alice["email"], alice["user_id"])
    assert result == {"level": "success", "text": "Friend invite sent to Alice."}
    assert session_state.get(PENDING_FRIEND_SHARE_CODE_KEY) is None
    assert invites[0]["from_user_id"] == "bob"
    assert invites[0]["to_user_id"] == "alice"
    assert pop_friend_share_message(session_state) == result
    assert FRIEND_SHARE_MESSAGE_KEY not in session_state


def test_share_link_does_not_duplicate_pending_invites(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    share_code = persistence.ensure_friend_share_code(alice["user_id"])
    first_invite = persistence.create_friend_invite_to_user(bob["user_id"], bob["email"], alice["user_id"])
    session_state = {PENDING_FRIEND_SHARE_CODE_KEY: share_code}

    result = apply_pending_friend_share(persistence, bob, bob["user_id"], session_state)

    assert result == {"level": "info", "text": "A friend invite with Alice is already pending."}
    assert persistence.incoming_friend_invites(alice["email"], alice["user_id"]) == [first_invite]


def test_share_link_ignores_self_and_already_friends(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    share_code = persistence.ensure_friend_share_code(alice["user_id"])

    self_result = apply_pending_friend_share(
        persistence,
        alice,
        alice["user_id"],
        {PENDING_FRIEND_SHARE_CODE_KEY: share_code},
    )
    invite = persistence.create_friend_invite_to_user(alice["user_id"], alice["email"], bob["user_id"])
    persistence.respond_friend_invite(invite["id"], bob["user_id"], bob["email"], approve=True)
    friend_result = apply_pending_friend_share(
        persistence,
        bob,
        bob["user_id"],
        {PENDING_FRIEND_SHARE_CODE_KEY: share_code},
    )

    assert self_result == {"level": "info", "text": "That is your own friend share link."}
    assert friend_result == {"level": "info", "text": "You and Alice are already friends."}


def test_share_link_reports_unknown_code(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")

    result = apply_pending_friend_share(
        persistence,
        bob,
        bob["user_id"],
        {PENDING_FRIEND_SHARE_CODE_KEY: "missing"},
    )

    assert result == {"level": "warning", "text": "That friend share link is no longer valid."}
