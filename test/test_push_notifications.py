from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=BERLIN)

from src.db.json_persistence import JsonPersistence
from src.push.notifications import (
    create_friend_invite_with_push,
    create_friend_suggestion_with_push,
    set_goal_completion_reaction_with_push,
    update_goal_progress_with_push,
)


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

def test_new_friend_suggestion_sends_push_to_both_users(monkeypatch, tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    calls = []

    monkeypatch.setattr(
        "src.push.notifications.send_push_to_user",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"sent": 1, "removed": 0, "errors": []},
    )

    suggestion = create_friend_suggestion_with_push(
        persistence,
        MemoryPushStorage(),
        {
            "vapid_public_key": "public",
            "vapid_private_key": "private",
            "vapid_subject": "mailto:test@example.com",
        },
        suggested_by_user_id=alice["user_id"],
        suggested_user_ids=[bob["user_id"], charlie["user_id"]],
        source_goal_id="goal_1",
    )

    assert suggestion["suggested_user_ids"] == ["bob", "charlie"]
    assert [call[0][1] for call in calls] == ["bob", "charlie"]
    assert calls[0][1]["title"] == "New friend suggestion"
    assert "Alice suggested you and Charlie" in calls[0][1]["body"]
    assert "Alice suggested you and Bob" in calls[1][1]["body"]


def test_duplicate_friend_suggestion_does_not_send_push(monkeypatch, tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    calls = []
    monkeypatch.setattr(
        "src.push.notifications.send_push_to_user",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"sent": 1, "removed": 0, "errors": []},
    )

    first = create_friend_suggestion_with_push(
        persistence,
        MemoryPushStorage(),
        {
            "vapid_public_key": "public",
            "vapid_private_key": "private",
            "vapid_subject": "mailto:test@example.com",
        },
        suggested_by_user_id=alice["user_id"],
        suggested_user_ids=[bob["user_id"], charlie["user_id"]],
    )
    second = create_friend_suggestion_with_push(
        persistence,
        MemoryPushStorage(),
        {
            "vapid_public_key": "public",
            "vapid_private_key": "private",
            "vapid_subject": "mailto:test@example.com",
        },
        suggested_by_user_id=alice["user_id"],
        suggested_user_ids=[charlie["user_id"], bob["user_id"]],
    )

    assert second["id"] == first["id"]
    assert len(calls) == 2


def test_missing_push_configuration_does_not_block_friend_suggestion(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")

    suggestion = create_friend_suggestion_with_push(
        persistence,
        None,
        {},
        suggested_by_user_id=alice["user_id"],
        suggested_user_ids=[bob["user_id"], charlie["user_id"]],
    )

    assert suggestion["status"] == "pending"


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
    assert "Alice completed Daily Steps: 10 / 10." == calls[0][1]["body"]


def test_skipped_goal_does_not_send_completion_push(monkeypatch, tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    invite = persistence.create_friend_invite("alice", alice["email"], bob["email"])
    persistence.respond_friend_invite(invite["id"], "bob", bob["email"], approve=True)
    goal = persistence.create_goal("alice", "Daily Steps", "daily_x_per_week", 5, ["bob"], 10, current=0)
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
        skipped=True,
    )

    assert calls == []


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


def test_goal_completion_pushes_are_capped_per_recipient_goal_day(monkeypatch, tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    friend_ids = ["bob", "charlie", "dave", "eve"]
    for friend_id in friend_ids:
        friend = persistence.upsert_user(friend_id, f"{friend_id}@example.com", friend_id.title())
        invite = persistence.create_friend_invite("alice", alice["email"], friend["email"])
        persistence.respond_friend_invite(invite["id"], friend_id, friend["email"], approve=True)

    goal = persistence.create_goal("alice", "Daily Steps", "daily", 1, friend_ids, 10, current=0)
    calls = []

    monkeypatch.setattr(
        "src.push.notifications.send_push_to_user",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"sent": 1, "removed": 0, "errors": []},
    )

    push_settings = {
        "vapid_public_key": "public",
        "vapid_private_key": "private",
        "vapid_subject": "mailto:test@example.com",
    }
    for friend_id in friend_ids:
        update_goal_progress_with_push(
            persistence,
            MemoryPushStorage(),
            push_settings,
            goal_id=goal["id"],
            user_id=friend_id,
            current=10,
        )

    assert [call[0][1] for call in calls] == ["alice", "alice", "alice"]


def test_goal_reaction_pushes_to_completed_user_once_per_two_hours_per_reacting_user(monkeypatch, tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    invite = persistence.create_friend_invite("alice", alice["email"], bob["email"])
    persistence.respond_friend_invite(invite["id"], "bob", bob["email"], approve=True)
    goal = persistence.create_goal("alice", "Daily Steps", "daily", 1, ["bob"], 10, current=10, now=at("2026-06-01T09:00:00"))
    calls = []

    monkeypatch.setattr(
        "src.push.notifications.send_push_to_user",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"sent": 1, "removed": 0, "errors": []},
    )
    push_settings = {
        "vapid_public_key": "public",
        "vapid_private_key": "private",
        "vapid_subject": "mailto:test@example.com",
    }

    set_goal_completion_reaction_with_push(
        persistence,
        MemoryPushStorage(),
        push_settings,
        goal_id=goal["id"],
        completed_user_id="alice",
        reacting_user_id="bob",
        emote="👍",
        now=at("2026-06-01T10:00:00"),
    )
    set_goal_completion_reaction_with_push(
        persistence,
        MemoryPushStorage(),
        push_settings,
        goal_id=goal["id"],
        completed_user_id="alice",
        reacting_user_id="bob",
        emote="🎉",
        now=at("2026-06-01T11:59:00"),
    )
    set_goal_completion_reaction_with_push(
        persistence,
        MemoryPushStorage(),
        push_settings,
        goal_id=goal["id"],
        completed_user_id="alice",
        reacting_user_id="bob",
        emote="🔥",
        now=at("2026-06-01T12:00:00"),
    )

    assert [call[0][1] for call in calls] == ["alice", "alice"]
    assert calls[0][1]["title"] == "New goal reaction"
    assert calls[0][1]["body"] == "Bob reacted 👍 to your completed goal Daily Steps."
    assert calls[1][1]["body"] == "Bob reacted 🔥 to your completed goal Daily Steps."


def test_goal_reaction_push_throttle_allows_different_reacting_users(monkeypatch, tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    for friend in [bob, charlie]:
        invite = persistence.create_friend_invite("alice", alice["email"], friend["email"])
        persistence.respond_friend_invite(invite["id"], friend["user_id"], friend["email"], approve=True)
    goal = persistence.create_goal("alice", "Steps", "daily", 1, ["bob", "charlie"], 10, current=10, now=at("2026-06-01T09:00:00"))
    calls = []
    monkeypatch.setattr(
        "src.push.notifications.send_push_to_user",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"sent": 1, "removed": 0, "errors": []},
    )
    push_settings = {
        "vapid_public_key": "public",
        "vapid_private_key": "private",
        "vapid_subject": "mailto:test@example.com",
    }

    set_goal_completion_reaction_with_push(
        persistence, MemoryPushStorage(), push_settings,
        goal_id=goal["id"], completed_user_id="alice", reacting_user_id="bob", emote="👍", now=at("2026-06-01T10:00:00")
    )
    set_goal_completion_reaction_with_push(
        persistence, MemoryPushStorage(), push_settings,
        goal_id=goal["id"], completed_user_id="alice", reacting_user_id="charlie", emote="🎉", now=at("2026-06-01T10:30:00")
    )
    set_goal_completion_reaction_with_push(
        persistence, MemoryPushStorage(), push_settings,
        goal_id=goal["id"], completed_user_id="alice", reacting_user_id="bob", emote="🔥", now=at("2026-06-01T11:00:00")
    )

    assert [call[0][1] for call in calls] == ["alice", "alice"]
    assert "Bob reacted 👍" in calls[0][1]["body"]
    assert "Charlie reacted 🎉" in calls[1][1]["body"]


def test_goal_reaction_without_push_configuration_still_saves(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    invite = persistence.create_friend_invite("alice", alice["email"], bob["email"])
    persistence.respond_friend_invite(invite["id"], "bob", bob["email"], approve=True)
    goal = persistence.create_goal("alice", "Daily Steps", "daily", 1, ["bob"], 10, current=10)

    updated = set_goal_completion_reaction_with_push(
        persistence,
        None,
        {},
        goal_id=goal["id"],
        completed_user_id="alice",
        reacting_user_id="bob",
        emote="👍",
    )

    assert updated["participants"]["alice"]["completion_reactions"]
    assert "reaction_notification_timestamps" not in (persistence.get_user("alice") or {})
