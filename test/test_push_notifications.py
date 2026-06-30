from pathlib import Path

from src.db.json_persistence import JsonPersistence
from src.push.notifications import create_friend_invite_with_push, update_goal_progress_with_push


class MemoryPushStorage:
    def subscriptions_for_user(self, user_id: str) -> list[dict]:
        return []

    def delete_subscription(self, endpoint: str) -> None:
        pass


def test_new_friend_invite_sends_push_to_registered_recipient(monkeypatch, tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    calls = []

    monkeypatch.setattr(
        "src.push.notifications.send_push_to_user",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"sent": 1, "removed": 0, "errors": []},
    )

    invite = create_friend_invite_with_push(
        persistence,
        MemoryPushStorage(),
        {
            "vapid_public_key": "public",
            "vapid_private_key": "private",
            "vapid_subject": "mailto:test@example.com",
        },
        from_user_id=alice["user_id"],
        from_email=alice["email"],
        to_email=bob["email"],
    )

    assert invite["to_email"] == "bob@example.com"
    assert len(calls) == 1
    assert calls[0][0][1] == "bob"


def test_duplicate_friend_invite_does_not_send_push(monkeypatch, tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    calls = []
    monkeypatch.setattr(
        "src.push.notifications.send_push_to_user",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"sent": 1, "removed": 0, "errors": []},
    )

    first = create_friend_invite_with_push(
        persistence,
        MemoryPushStorage(),
        {
            "vapid_public_key": "public",
            "vapid_private_key": "private",
            "vapid_subject": "mailto:test@example.com",
        },
        from_user_id=alice["user_id"],
        from_email=alice["email"],
        to_email=bob["email"],
    )
    second = create_friend_invite_with_push(
        persistence,
        MemoryPushStorage(),
        {
            "vapid_public_key": "public",
            "vapid_private_key": "private",
            "vapid_subject": "mailto:test@example.com",
        },
        from_user_id=alice["user_id"],
        from_email=alice["email"],
        to_email=bob["email"],
    )

    assert second["id"] == first["id"]
    assert len(calls) == 1


def test_missing_recipient_subscription_does_not_block_invite(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")

    invite = create_friend_invite_with_push(
        persistence,
        None,
        {},
        from_user_id=alice["user_id"],
        from_email=alice["email"],
        to_email=bob["email"],
    )

    assert invite["to_email"] == "bob@example.com"


def test_goal_completion_pushes_to_friends_sharing_goal_once(monkeypatch, tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    bob_invite = persistence.create_friend_invite("alice", alice["email"], bob["email"])
    persistence.respond_friend_invite(bob_invite["id"], "bob", bob["email"], approve=True)
    charlie_invite = persistence.create_friend_invite("alice", alice["email"], charlie["email"])
    persistence.respond_friend_invite(charlie_invite["id"], "charlie", charlie["email"], approve=True)
    goal = persistence.create_goal("alice", "Daily Steps", "daily", 1, ["bob"], 10, current=0)
    calls = []

    monkeypatch.setattr(
        "src.push.notifications.send_push_to_user",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"sent": 1, "removed": 0, "errors": []},
    )

    update_goal_progress_with_push(
        persistence,
        MemoryPushStorage(),
        {
            "vapid_public_key": "public",
            "vapid_private_key": "private",
            "vapid_subject": "mailto:test@example.com",
        },
        goal_id=goal["id"],
        user_id="alice",
        current=10,
    )
    update_goal_progress_with_push(
        persistence,
        MemoryPushStorage(),
        {
            "vapid_public_key": "public",
            "vapid_private_key": "private",
            "vapid_subject": "mailto:test@example.com",
        },
        goal_id=goal["id"],
        user_id="alice",
        current=11,
    )

    assert len(calls) == 1
    assert calls[0][0][1] == "bob"
    assert calls[0][1]["title"] == "Shared goal completed"
    assert "Alice completed Daily Steps." == calls[0][1]["body"]


def test_recipient_opted_out_goal_completion_push_does_not_send(monkeypatch, tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    invite = persistence.create_friend_invite("alice", alice["email"], bob["email"])
    persistence.respond_friend_invite(invite["id"], "bob", bob["email"], approve=True)
    goal = persistence.create_goal("alice", "Daily Steps", "daily", 1, ["bob"], 10, current=0)
    persistence.set_goal_completion_notifications(goal["id"], "bob", False)
    calls = []

    monkeypatch.setattr(
        "src.push.notifications.send_push_to_user",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"sent": 1, "removed": 0, "errors": []},
    )

    update_goal_progress_with_push(
        persistence,
        MemoryPushStorage(),
        {
            "vapid_public_key": "public",
            "vapid_private_key": "private",
            "vapid_subject": "mailto:test@example.com",
        },
        goal_id=goal["id"],
        user_id="alice",
        current=10,
    )

    assert calls == []
