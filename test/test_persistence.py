from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import copy
import json
import pytest

from src.db.mongodb_persistence import MongoPersistence
from src.db.persistence import JsonPersistence, create_persistence, persistence_settings
from src.pages.debug_page import DebugMechanics, debug_now, debug_view_enabled

BERLIN = ZoneInfo("Europe/Berlin")


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=BERLIN)


class FakeMongoCollection:
    def __init__(self) -> None:
        self.document = None

    def find_one(self, query: dict) -> dict | None:
        if self.document and query == {"_id": self.document["_id"]}:
            return copy.deepcopy(self.document)
        return None

    def replace_one(self, query: dict, replacement: dict, upsert: bool = False) -> None:
        assert query == {"_id": replacement["_id"]}
        assert upsert is True
        self.document = copy.deepcopy(replacement)


def users_and_friendship(persistence: JsonPersistence) -> tuple[dict, dict]:
    alice = persistence.upsert_user("alice", "Alice@Example.com", "Alice", at("2026-06-01T09:00:00"))
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob", at("2026-06-01T09:01:00"))
    invite = persistence.create_friend_invite("alice", alice["email"], bob["email"], at("2026-06-01T09:02:00"))
    persistence.respond_friend_invite(invite["id"], "bob", bob["email"], approve=True, now=at("2026-06-01T09:03:00"))
    return alice, bob


def test_missing_file_gets_new_app_schema(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")

    assert persistence.raw_data() == {
        "users": {},
        "friend_invites": {},
        "friendships": {},
        "goals": {},
        "user_stats": {},
        "debug": {"time_offset_seconds": 0},
    }


def test_old_counter_state_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    path.write_text(json.dumps({"users": {"old-user": {"count": 3, "text": "hello"}}}), encoding="utf-8")
    persistence = JsonPersistence(path)

    assert persistence.raw_data()["users"] == {}


def test_user_profile_upsert_normalizes_email_and_preserves_created_at(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")

    first = persistence.upsert_user("alice", "Alice@Example.com", "Alice", at("2026-06-01T09:00:00"))
    second = persistence.upsert_user("alice", "ALICE@example.com", "Alice A.", at("2026-06-02T09:00:00"))

    assert first["email"] == "alice@example.com"
    assert second["email"] == "alice@example.com"
    assert second["name"] == "Alice A."
    assert second["created_at"] == first["created_at"]
    assert second["last_seen_at"] != first["last_seen_at"]


def test_friend_invite_lifecycle_and_duplicate_prevention(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob", at("2026-06-01T09:01:00"))

    invite = persistence.create_friend_invite("alice", alice["email"], "BOB@example.com", at("2026-06-01T09:02:00"))
    duplicate = persistence.create_friend_invite("alice", alice["email"], "bob@example.com", at("2026-06-01T09:03:00"))

    assert duplicate["id"] == invite["id"]
    assert persistence.incoming_friend_invites("bob@example.com") == [invite]
    persistence.respond_friend_invite(invite["id"], "bob", bob["email"], approve=True, now=at("2026-06-01T09:04:00"))

    assert invite["id"] not in persistence.raw_data()["friend_invites"]
    assert [friend["user_id"] for friend in persistence.list_friends("alice")] == ["bob"]
    assert [friend["user_id"] for friend in persistence.list_friends("bob")] == ["alice"]
    with pytest.raises(ValueError, match="already friends"):
        persistence.create_friend_invite("alice", alice["email"], "bob@example.com")

    persistence.remove_friend("alice", "bob", at("2026-06-01T09:05:00"))
    assert persistence.list_friends("alice") == []


def test_declined_friend_invite_does_not_create_friendship(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    invite = persistence.create_friend_invite("alice", alice["email"], bob["email"])

    persistence.respond_friend_invite(invite["id"], "bob", bob["email"], approve=False)

    assert persistence.incoming_friend_invites(bob["email"]) == []
    assert persistence.list_friends("alice") == []


def test_pending_invite_appears_when_email_owner_logs_in(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    invite = persistence.create_friend_invite("alice", alice["email"], "future@example.com")

    future = persistence.upsert_user("future-user", "future@example.com", "Future")

    assert persistence.incoming_friend_invites(future["email"])[0]["id"] == invite["id"]


def test_debug_time_offset_is_persisted_and_applied_only_when_enabled(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    persistence = JsonPersistence(path)

    assert persistence.debug_time_offset_seconds() == 0
    assert persistence.add_debug_time_offset(60 * 60) == 60 * 60
    assert JsonPersistence(path).debug_time_offset_seconds() == 60 * 60

    server_now = at("2026-06-01T10:00:00")
    assert debug_now(persistence, False, server_now) == server_now
    assert debug_now(persistence, True, server_now) == at("2026-06-01T11:00:00")


def test_debug_view_enabled_comes_from_secrets() -> None:
    assert debug_view_enabled({"debug": {"view": True}}) is True
    assert debug_view_enabled({"debug": {"view": "yes"}}) is True
    assert debug_view_enabled({"debug": {"enabled": "yes"}}) is False
    assert debug_view_enabled({"debug_view": True}) is False
    assert debug_view_enabled({"debug_view": "false"}) is False


def test_debug_mechanics_uses_same_secrets_flag(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")

    enabled = DebugMechanics.from_secrets(persistence, secrets={"debug": {"view": True}})
    disabled = DebugMechanics.from_secrets(persistence, secrets={"debug": {"view": False}})

    assert enabled.enabled is True
    assert enabled.debug_login_enabled is True
    assert disabled.enabled is False
    assert disabled.debug_login_enabled is False


def test_goal_creation_requires_friends_and_creates_per_user_participants(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    users_and_friendship(persistence)

    goal = persistence.create_goal(
        created_by="alice",
        description="Read pages",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=["bob"],
        target=20,
        current=5,
        now=at("2026-06-01T10:00:00"),
    )

    assert goal["participant_user_ids"] == ["alice", "bob"]
    assert goal["participants"]["alice"]["target"] == 20
    assert goal["participants"]["alice"]["current"] == 5
    assert goal["participants"]["alice"]["completion_streak"] == 0
    assert goal["participants"]["bob"]["target"] == 20
    assert goal["participants"]["bob"]["current"] == 0
    assert goal["participants"]["bob"]["completion_streak"] == 0

    with pytest.raises(ValueError, match="accepted friends"):
        persistence.create_goal("alice", "Stretch", "daily", 1, ["charlie"], 10)


def test_goal_participant_can_add_more_accepted_friends(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice, _bob = users_and_friendship(persistence)
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie", at("2026-06-01T09:04:00"))
    invite = persistence.create_friend_invite(
        "alice",
        alice["email"],
        charlie["email"],
        at("2026-06-01T09:05:00"),
    )
    persistence.respond_friend_invite(
        invite["id"],
        "charlie",
        charlie["email"],
        approve=True,
        now=at("2026-06-01T09:06:00"),
    )
    goal = persistence.create_goal(
        created_by="alice",
        description="Read pages",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=["bob"],
        target=20,
        current=5,
        now=at("2026-06-01T10:00:00"),
    )

    updated = persistence.add_goal_friends(
        goal["id"],
        "alice",
        ["charlie"],
        now=at("2026-06-01T11:00:00"),
    )

    assert updated["participant_user_ids"] == ["alice", "bob", "charlie"]
    assert updated["participants"]["charlie"]["target"] == 20
    assert updated["participants"]["charlie"]["current"] == 0
    assert updated["participants"]["charlie"]["completion_streak"] == 0
    assert persistence.list_goals_for_user("charlie")[0]["id"] == goal["id"]

    with pytest.raises(ValueError, match="accepted friends"):
        persistence.add_goal_friends(goal["id"], "alice", ["dana"])


def test_participant_updates_own_progress_and_can_leave_goal(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    users_and_friendship(persistence)
    goal = persistence.create_goal("alice", "Run", "weekly", 1, ["bob"], 10, current=2)

    persistence.update_goal_progress(goal["id"], "bob", current=4, target=12)
    updated = persistence.list_goals_for_user("bob")[0]

    assert updated["participants"]["bob"]["current"] == 4
    assert updated["participants"]["bob"]["target"] == 12
    assert updated["participants"]["alice"]["target"] == 10

    persistence.leave_goal(goal["id"], "bob")
    data = persistence.raw_data()

    assert "bob" not in data["goals"][goal["id"]]["participants"]
    assert data["goals"][goal["id"]]["participant_user_ids"] == ["alice"]
    assert persistence.list_goals_for_user("bob") == []
    assert persistence.list_goals_for_user("alice") != []


def test_last_participant_leaving_deletes_goal_record(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    goal = persistence.create_goal(
        created_by=alice["user_id"],
        description="Meditate",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=[],
        target=1,
    )

    persistence.leave_goal(goal["id"], alice["user_id"])

    assert goal["id"] not in persistence.raw_data()["goals"]
    assert persistence.list_goals_for_user(alice["user_id"]) == []


def test_period_rollover_updates_streak_activity_and_resets_progress(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    goal = persistence.create_goal(
        created_by="alice",
        description="Drink water",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=[],
        target=3,
        current=4,
        now=at("2026-06-01T12:00:00"),
    )

    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-02T08:00:00"))
    data = persistence.raw_data()
    updated_goal = data["goals"][goal["id"]]
    activity = data["user_stats"]["alice"]["activity_days"]["2026-06-01"]

    assert "period_records" not in data
    assert updated_goal["participants"]["alice"]["current"] == 0
    assert updated_goal["participants"]["alice"]["completion_streak"] == 1
    assert activity == {"active_goals": 1, "fulfilled_goals": 1, "percent": 100.0}


def test_missed_daily_period_resets_streak(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    goal = persistence.create_goal(
        created_by="alice",
        description="Drink water",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=[],
        target=3,
        current=4,
        now=at("2026-06-01T12:00:00"),
    )

    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-02T08:00:00"))
    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-03T08:00:00"))

    participant = persistence.raw_data()["goals"][goal["id"]]["participants"]["alice"]
    assert participant["completion_streak"] == 0


def test_daily_x_per_week_increments_streak_for_each_completed_daily_period(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    goal = persistence.create_goal(
        created_by="alice",
        description="Practice",
        schedule_class="daily_x_per_week",
        required_periods=3,
        friend_user_ids=[],
        target=10,
        current=8,
        now=at("2026-06-01T12:00:00"),
    )

    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-02T08:00:00"))
    persistence.update_goal_progress(goal["id"], alice["user_id"], current=10, now=at("2026-06-02T09:00:00"))
    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-03T08:00:00"))
    persistence.update_goal_progress(goal["id"], alice["user_id"], current=13, now=at("2026-06-03T09:00:00"))
    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-04T08:00:00"))

    participant = persistence.raw_data()["goals"][goal["id"]]["participants"]["alice"]
    assert participant["completion_streak"] == 2


def test_weekly_x_per_month_increments_streak_for_each_completed_weekly_period(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    goal = persistence.create_goal(
        created_by="alice",
        description="Long run",
        schedule_class="weekly_x_per_month",
        required_periods=2,
        friend_user_ids=[],
        target=5,
        current=4,
        now=at("2026-06-01T12:00:00"),
    )

    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-08T08:00:00"))
    persistence.update_goal_progress(goal["id"], alice["user_id"], current=6, now=at("2026-06-08T09:00:00"))
    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-15T08:00:00"))

    participant = persistence.raw_data()["goals"][goal["id"]]["participants"]["alice"]
    assert participant["completion_streak"] == 1


def test_activity_summaries_keep_last_365_days(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2025-01-01T09:00:00"))
    persistence.create_goal(
        created_by="alice",
        description="Drink water",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=[],
        target=1,
        current=0,
        now=at("2025-01-01T12:00:00"),
    )

    persistence.list_goals_for_user(alice["user_id"], now=at("2026-02-01T08:00:00"))

    activity_days = persistence.raw_data()["user_stats"]["alice"]["activity_days"]
    assert len(activity_days) == 365
    assert "2025-01-01" not in activity_days
    assert "2026-02-01" in activity_days


def test_account_stats_report_current_month_rate_and_days_using_app(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    goal = persistence.create_goal(
        created_by="alice",
        description="Drink water",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=[],
        target=1,
        current=1,
        now=at("2026-06-01T12:00:00"),
    )

    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-02T08:00:00"))
    persistence.update_goal_progress(goal["id"], alice["user_id"], current=0, now=at("2026-06-02T09:00:00"))
    stats = persistence.account_stats(alice["user_id"], now=at("2026-06-02T10:00:00"))

    assert stats["days_using_app"] == 2
    assert stats["completion_rate"] == 50.0
    assert stats["activity_days"]["2026-06-01"]["percent"] == 100.0
    assert stats["activity_days"]["2026-06-02"]["percent"] == 0.0


def test_mongodb_document_backend_uses_same_store_contract() -> None:
    collection = FakeMongoCollection()
    persistence = MongoPersistence(mongo_collection=collection)

    user = persistence.upsert_user("alice", "Alice@Example.com", "Alice", at("2026-06-01T09:00:00"))

    assert user["email"] == "alice@example.com"
    assert collection.document["_id"] == "app_store"
    assert collection.document["data"]["users"]["alice"]["name"] == "Alice"
    assert MongoPersistence(mongo_collection=collection).get_user("alice") == user


def test_factory_creates_mongodb_backend() -> None:
    persistence = create_persistence(
        "mongodb",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="dogether_test",
        mongodb_collection="app_store",
    )

    assert isinstance(persistence, MongoPersistence)
    persistence.close()


def test_factory_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="Unsupported persistence backend"):
        create_persistence("sqlite")


def test_persistence_settings_come_from_secrets() -> None:
    assert persistence_settings({"persistence": {"json_path": "custom/users.json"}}) == {
        "backend": "json",
        "json_path": "custom/users.json",
        "mongodb_uri": "",
        "mongodb_database": "dogether",
        "mongodb_collection": "users",
    }
