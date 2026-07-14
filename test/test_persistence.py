from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import copy
import json
import pytest

import src.db.cached_document_persistence as cached_document_persistence
from src.db.mongodb_persistence import MongoPersistence
from src.db.mongodb_native_persistence import MongoNativePersistence
from src.db.persistence import JsonPersistence, create_persistence, persistence_settings
from src.pages.debug_page import DebugMechanics, debug_now, debug_view_enabled

BERLIN = ZoneInfo("Europe/Berlin")


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=BERLIN)


class FakeMongoCollection:
    def __init__(self) -> None:
        self.document = None
        self.find_one_calls = 0

    def find_one(self, query: dict) -> dict | None:
        self.find_one_calls += 1
        if self.document and query == {"_id": self.document["_id"]}:
            return copy.deepcopy(self.document)
        return None

    def replace_one(self, query: dict, replacement: dict, upsert: bool = False) -> None:
        assert query == {"_id": replacement["_id"]}
        assert upsert is True
        self.document = copy.deepcopy(replacement)


class CountingJsonPersistence(JsonPersistence):
    def __init__(self, *args, **kwargs) -> None:
        self.write_count = 0
        super().__init__(*args, **kwargs)

    def _write_uncached(self, data: dict) -> None:
        self.write_count += 1
        super()._write_uncached(data)


class FakeMongoNativeCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.documents = {}
        self.calls = []
        self.indexes = []

    def create_index(self, spec):
        self.calls.append(("create_index", spec))
        self.indexes.append(spec)

    def find_one(self, query: dict) -> dict | None:
        self.calls.append(("find_one", copy.deepcopy(query)))
        for document in self.documents.values():
            if self._matches(document, query):
                return copy.deepcopy(document)
        return None

    def find(self, query: dict | None = None):
        query = query or {}
        self.calls.append(("find", copy.deepcopy(query)))
        return [copy.deepcopy(document) for document in self.documents.values() if self._matches(document, query)]

    def count_documents(self, query: dict) -> int:
        self.calls.append(("count_documents", copy.deepcopy(query)))
        return sum(1 for document in self.documents.values() if self._matches(document, query))

    def replace_one(self, query: dict, replacement: dict, upsert: bool = False) -> None:
        self.calls.append(("replace_one", copy.deepcopy(query), copy.deepcopy(replacement), upsert))
        document_id = query.get("_id", replacement.get("_id"))
        if document_id in self.documents or upsert:
            self.documents[document_id] = copy.deepcopy(replacement)

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
        self.calls.append(("update_one", copy.deepcopy(query), copy.deepcopy(update), upsert))
        document = None
        document_id = query.get("_id")
        if document_id is not None:
            document = self.documents.get(document_id)
        if document is None:
            for candidate in self.documents.values():
                if self._matches(candidate, query):
                    document = candidate
                    break
        if document is None:
            if not upsert:
                return
            document_id = document_id or update.get("$set", {}).get("id")
            document = {"_id": document_id}
            self.documents[document_id] = document
        for key, value in update.get("$set", {}).items():
            self._set_path(document, key, copy.deepcopy(value))

    def delete_one(self, query: dict) -> None:
        self.calls.append(("delete_one", copy.deepcopy(query)))
        for document_id, document in list(self.documents.items()):
            if self._matches(document, query):
                del self.documents[document_id]
                return

    def _matches(self, document: dict, query: dict) -> bool:
        for key, expected in query.items():
            actual = self._get_path(document, key)
            if isinstance(expected, dict):
                if "$in" in expected:
                    if actual not in expected["$in"]:
                        return False
                    continue
                if "$ne" in expected:
                    if actual == expected["$ne"]:
                        return False
                    continue
                if "$exists" in expected:
                    exists = actual is not None
                    if bool(expected["$exists"]) != exists:
                        return False
                    continue
            if isinstance(actual, list):
                if expected not in actual and actual != expected:
                    return False
            elif actual != expected:
                return False
        return True

    def _get_path(self, document: dict, path: str):
        current = document
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    def _set_path(self, document: dict, path: str, value) -> None:
        current = document
        parts = path.split(".")
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value


class FakeMongoNativeDatabase:
    def __init__(self) -> None:
        self.collections = {}

    def __getitem__(self, name: str) -> FakeMongoNativeCollection:
        if name not in self.collections:
            self.collections[name] = FakeMongoNativeCollection(name)
        return self.collections[name]


def users_and_friendship(persistence: JsonPersistence) -> tuple[dict, dict]:
    alice = persistence.upsert_user("alice", "Alice@Example.com", "Alice", at("2026-06-01T09:00:00"))
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob", at("2026-06-01T09:01:00"))
    invite = persistence.create_friend_invite("alice", alice["email"], bob["email"], at("2026-06-01T09:02:00"))
    persistence.respond_friend_invite(invite["id"], "bob", bob["email"], approve=True, now=at("2026-06-01T09:03:00"))
    return alice, bob


def test_json_persistence_uses_cache_inside_ttl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    now = 100.0
    monkeypatch.setattr(cached_document_persistence, "monotonic", lambda: now)
    path = tmp_path / "users.json"
    path.write_text(
        json.dumps({"users": {"alice": {"user_id": "alice", "email": "alice@example.com", "name": "Alice"}}}),
        encoding="utf-8",
    )
    persistence = JsonPersistence(path, cache_ttl_seconds=5)

    assert persistence.get_user("alice")["name"] == "Alice"
    path.write_text(
        json.dumps({"users": {"alice": {"user_id": "alice", "email": "alice@example.com", "name": "Alicia"}}}),
        encoding="utf-8",
    )

    assert persistence.get_user("alice")["name"] == "Alice"


def test_json_persistence_reloads_after_cache_ttl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    current_time = 100.0
    monkeypatch.setattr(cached_document_persistence, "monotonic", lambda: current_time)
    path = tmp_path / "users.json"
    path.write_text(
        json.dumps({"users": {"alice": {"user_id": "alice", "email": "alice@example.com", "name": "Alice"}}}),
        encoding="utf-8",
    )
    persistence = JsonPersistence(path, cache_ttl_seconds=5)

    assert persistence.get_user("alice")["name"] == "Alice"
    path.write_text(
        json.dumps({"users": {"alice": {"user_id": "alice", "email": "alice@example.com", "name": "Alicia"}}}),
        encoding="utf-8",
    )
    current_time = 106.0

    assert persistence.get_user("alice")["name"] == "Alicia"


def test_json_persistence_write_refreshes_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cached_document_persistence, "monotonic", lambda: 100.0)
    path = tmp_path / "users.json"
    persistence = JsonPersistence(path, cache_ttl_seconds=5)

    persistence.upsert_user("alice", "alice@example.com", "Alice")
    path.write_text(
        json.dumps({"users": {"charlie": {"user_id": "charlie", "email": "charlie@example.com", "name": "Charlie"}}}),
        encoding="utf-8",
    )
    persistence.upsert_user("bob", "bob@example.com", "Bob")

    assert persistence.get_user("bob")["name"] == "Bob"
    assert persistence.get_user("alice")["name"] == "Alice"
    assert persistence.get_user("charlie") is None


def test_json_persistence_cache_can_be_disabled(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    path.write_text(
        json.dumps({"users": {"alice": {"user_id": "alice", "email": "alice@example.com", "name": "Alice"}}}),
        encoding="utf-8",
    )
    persistence = JsonPersistence(path, cache_ttl_seconds=0)

    assert persistence.get_user("alice")["name"] == "Alice"
    path.write_text(
        json.dumps({"users": {"alice": {"user_id": "alice", "email": "alice@example.com", "name": "Alicia"}}}),
        encoding="utf-8",
    )

    assert persistence.get_user("alice")["name"] == "Alicia"


def test_mongodb_document_backend_uses_cache_inside_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cached_document_persistence, "monotonic", lambda: 100.0)
    collection = FakeMongoCollection()
    collection.document = {
        "_id": "app_store",
        "data": {"users": {"alice": {"user_id": "alice", "email": "alice@example.com", "name": "Alice"}}},
    }
    persistence = MongoPersistence(mongo_collection=collection, cache_ttl_seconds=5)

    assert persistence.get_user("alice")["name"] == "Alice"
    assert persistence.get_user("alice")["name"] == "Alice"

    assert collection.find_one_calls == 1

def test_missing_file_gets_new_app_schema(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")

    assert persistence.raw_data() == {
        "users": {},
        "friend_invites": {},
        "friend_suggestions": {},
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


def test_user_profile_upsert_normalizes_email_and_preserves_activity_timestamp(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")

    first = persistence.upsert_user("alice", "Alice@Example.com", "Alice", at("2026-06-01T09:00:00"))
    second = persistence.upsert_user("alice", "ALICE@example.com", "Alice A.", at("2026-06-02T09:00:00"))

    assert first["email"] == "alice@example.com"
    assert second["email"] == "alice@example.com"
    assert second["name"] == "Alice A."
    assert second["created_at"] == first["created_at"]
    assert second["last_seen_at"] == first["last_seen_at"]


def test_user_profile_upsert_skips_write_when_profile_is_unchanged(tmp_path: Path) -> None:
    persistence = CountingJsonPersistence(tmp_path / "users.json")

    first = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    writes_after_create = persistence.write_count
    second = persistence.upsert_user("alice", "ALICE@example.com", "Alice", at("2026-06-02T09:00:00"))

    assert second == first
    assert persistence.write_count == writes_after_create


def test_friend_invite_lifecycle_and_duplicate_prevention(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob", at("2026-06-01T09:01:00"))

    invite = persistence.create_friend_invite("alice", alice["email"], "BOB@example.com", at("2026-06-01T09:02:00"))
    duplicate = persistence.create_friend_invite("alice", alice["email"], "bob@example.com", at("2026-06-01T09:03:00"))

    assert duplicate["id"] == invite["id"]
    assert invite["to_user_id"] == "bob"
    assert persistence.incoming_friend_invites("bob@example.com", "bob") == [invite]
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


def test_outgoing_friend_invites_hide_stale_invites_without_existing_recipient(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    path.write_text(
        json.dumps(
            {
                "users": {
                    "alice": {
                        "user_id": "alice",
                        "email": "alice@example.com",
                        "name": "Alice",
                    }
                },
                "friend_invites": {
                    "invite_old": {
                        "id": "invite_old",
                        "from_user_id": "alice",
                        "from_email": "alice@example.com",
                        "to_email": "future@example.com",
                        "status": "pending",
                        "created_at": "2026-06-01T07:00:00+00:00",
                        "updated_at": "2026-06-01T07:00:00+00:00",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    persistence = JsonPersistence(path)

    assert persistence.outgoing_friend_invites("alice") == []


def test_incoming_friend_invite_matches_target_user_id(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    invite = persistence.create_friend_invite("alice", alice["email"], bob["email"])

    persistence.upsert_user("bob", "robert@example.com", "Bob")

    assert persistence.incoming_friend_invites("robert@example.com", "bob") == [invite]


def test_friend_invite_requires_existing_user(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")

    with pytest.raises(ValueError, match="No user found"):
        persistence.create_friend_invite("alice", alice["email"], "future@example.com")

    assert persistence.raw_data()["friend_invites"] == {}

def test_dismiss_friend_suggestion_pair_saves_sorted_pairs_once(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    persistence.upsert_user("alice", "alice@example.com", "Alice")

    user = persistence.dismiss_friend_suggestion_pair("alice", "charlie", "bob", now=at("2026-06-01T10:00:00"))
    duplicate = persistence.dismiss_friend_suggestion_pair("alice", "bob", "charlie", now=at("2026-06-01T10:01:00"))

    assert user["dismissed_friend_suggestion_pairs"] == [["bob", "charlie"]]
    assert duplicate["dismissed_friend_suggestion_pairs"] == [["bob", "charlie"]]
    assert persistence.dismissed_friend_suggestion_pairs("alice") == [["bob", "charlie"]]


def test_upsert_user_preserves_dismissed_friend_suggestion_pairs(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    persistence.dismiss_friend_suggestion_pair("alice", "charlie", "bob", now=at("2026-06-01T10:00:00"))

    updated = persistence.upsert_user("alice", "ALICE@example.com", "Alice A.", at("2026-06-02T09:00:00"))

    assert updated["name"] == "Alice A."
    assert updated["dismissed_friend_suggestion_pairs"] == [["bob", "charlie"]]


def test_friend_suggestion_requires_both_users_to_accept(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")

    suggestion = persistence.create_friend_suggestion(
        alice["user_id"],
        [bob["user_id"], charlie["user_id"]],
        source_goal_id="goal_1",
        now=at("2026-06-01T10:00:00"),
    )
    duplicate = persistence.create_friend_suggestion(
        alice["user_id"],
        [charlie["user_id"], bob["user_id"]],
        source_goal_id="goal_1",
        now=at("2026-06-01T10:01:00"),
    )

    assert duplicate["id"] == suggestion["id"]
    assert persistence.incoming_friend_suggestions("bob") == [suggestion]

    first_response = persistence.respond_friend_suggestion(
        suggestion["id"],
        "bob",
        approve=True,
        now=at("2026-06-01T10:02:00"),
    )

    assert first_response["status"] == "pending"
    assert persistence.list_friends("bob") == []
    assert persistence.incoming_friend_suggestions("bob") == []
    assert persistence.accepted_pending_friend_suggestions("bob") == [first_response]
    assert persistence.incoming_friend_suggestions("charlie") == [first_response]
    assert persistence.accepted_pending_friend_suggestions("charlie") == []

    second_response = persistence.respond_friend_suggestion(
        suggestion["id"],
        "charlie",
        approve=True,
        now=at("2026-06-01T10:03:00"),
    )

    assert second_response["status"] == "accepted"
    assert persistence.accepted_pending_friend_suggestions("bob") == []
    assert persistence.accepted_pending_friend_suggestions("charlie") == []
    assert [friend["user_id"] for friend in persistence.list_friends("bob")] == ["charlie"]
    assert [friend["user_id"] for friend in persistence.list_friends("charlie")] == ["bob"]
    assert persistence.list_friends("alice") == []


def test_friend_suggestion_decline_cancels_for_both_users(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    suggestion = persistence.create_friend_suggestion(alice["user_id"], [bob["user_id"], charlie["user_id"]])

    declined = persistence.respond_friend_suggestion(suggestion["id"], "bob", approve=False)

    assert declined["status"] == "declined"
    assert persistence.incoming_friend_suggestions("bob") == []
    assert persistence.incoming_friend_suggestions("charlie") == []
    assert persistence.list_friends("bob") == []


def test_friend_suggestion_rejects_already_friends(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    invite = persistence.create_friend_invite("bob", bob["email"], charlie["email"])
    persistence.respond_friend_invite(invite["id"], "charlie", charlie["email"], approve=True)

    with pytest.raises(ValueError, match="already friends"):
        persistence.create_friend_suggestion(alice["user_id"], [bob["user_id"], charlie["user_id"]])


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



def test_goal_completion_notifications_default_enabled_and_once_per_day(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    users_and_friendship(persistence)
    goal = persistence.create_goal(
        "alice",
        "Run",
        "daily",
        1,
        ["bob"],
        10,
        current=0,
        now=at("2026-06-01T09:00:00"),
    )

    assert goal["participants"]["alice"]["completion_notifications_enabled"] is True
    assert goal["participants"]["bob"]["completion_notifications_enabled"] is True

    completed = persistence.update_goal_progress(
        goal["id"],
        "alice",
        current=10,
        now=at("2026-06-01T10:00:00"),
    )
    repeated = persistence.update_goal_progress(
        goal["id"],
        "alice",
        current=11,
        now=at("2026-06-01T11:00:00"),
    )

    assert completed["_notification_event"]["type"] == "goal_completed"
    assert completed["_notification_event"]["day"] == "2026-06-01"
    assert "_notification_event" not in repeated


def test_goal_completion_notification_preference_is_per_participant(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    users_and_friendship(persistence)
    goal = persistence.create_goal("alice", "Run", "daily", 1, ["bob"], 10, current=0)

    updated = persistence.set_goal_completion_notifications(goal["id"], "bob", False)
    completed = persistence.update_goal_progress(goal["id"], "alice", current=10)

    assert updated["participants"]["bob"]["completion_notifications_enabled"] is False
    assert updated["participants"]["alice"]["completion_notifications_enabled"] is True
    assert completed["_notification_event"]["type"] == "goal_completed"


def test_health_data_workflow_target_is_unique_per_user(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    users_and_friendship(persistence)
    first = persistence.create_goal("alice", "Steps", "daily", 1, ["bob"], 8000, current=0)
    second = persistence.create_goal("alice", "Walk", "daily", 1, ["bob"], 30, current=0)

    activated_first = persistence.set_health_data_workflow_target(first["id"], "alice", True)
    activated_second = persistence.set_health_data_workflow_target(second["id"], "alice", True)
    goals = {goal["id"]: goal for goal in persistence.list_goals_for_user("alice")}

    assert activated_first["participants"]["alice"]["health_data_workflow"]["enabled"] is True
    assert activated_second["participants"]["alice"]["health_data_workflow"]["enabled"] is True
    assert goals[first["id"]]["participants"]["alice"]["health_data_workflow"]["enabled"] is False
    assert goals[second["id"]]["participants"]["alice"]["health_data_workflow"]["enabled"] is True
    assert "health_data_workflow" not in goals[second["id"]]["participants"]["bob"]

    persistence.set_health_data_workflow_target(None, "alice", False)
    disabled_goals = persistence.list_goals_for_user("alice")

    assert all(
        not goal["participants"]["alice"].get("health_data_workflow", {}).get("enabled", False)
        for goal in disabled_goals
    )

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
    _alice, bob = users_and_friendship(persistence)
    goal = persistence.create_goal("alice", "Run", "weekly", 1, ["bob"], 10, current=2)

    persistence.update_goal_progress(goal["id"], "bob", current=4, target=12, now=at("2026-06-01T09:04:00"))
    updated = persistence.list_goals_for_user("bob")[0]

    assert updated["participants"]["bob"]["current"] == 4
    assert updated["participants"]["bob"]["target"] == 12
    assert updated["participants"]["alice"]["target"] == 10
    assert persistence.raw_data()["users"]["bob"]["last_seen_at"] != bob["last_seen_at"]
    assert persistence.raw_data()["users"]["bob"]["last_seen_at"] == "2026-06-01T07:04:00+00:00"

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


def test_period_rollover_records_partial_progress_ratio(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    goal = persistence.create_goal(
        created_by="alice",
        description="Daily Steps",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=[],
        target=5000,
        current=3800,
        now=at("2026-06-01T12:00:00"),
    )

    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-02T08:00:00"))

    outcome = persistence.raw_data()["goals"][goal["id"]]["participants"]["alice"]["period_outcomes"]["2026-06-01"]
    assert outcome == {
        "completed": False,
        "skipped": False,
        "fulfilled": False,
        "current": 3800,
        "target": 5000,
        "percent": 76.0,
    }


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
    assert participant["completion_streak"] == 3


def test_skipped_goal_renders_as_zero_progress_state_until_reset(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    goal = persistence.create_goal(
        created_by="alice",
        description="Drink water",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=[],
        target=3,
        current=2,
        now=at("2026-06-01T12:00:00"),
    )

    skipped = persistence.update_goal_progress(
        goal["id"],
        alice["user_id"],
        skipped=True,
        now=at("2026-06-01T13:00:00"),
    )

    participant = skipped["participants"]["alice"]
    assert participant["current"] == 0
    assert participant["skipped"] is True

    reset = persistence.update_goal_progress(
        goal["id"],
        alice["user_id"],
        current=0,
        now=at("2026-06-01T14:00:00"),
    )

    assert reset["participants"]["alice"]["skipped"] is False


def test_daily_x_per_week_allows_only_surplus_skips_in_calendar_week(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    goal = persistence.create_goal(
        created_by="alice",
        description="Practice",
        schedule_class="daily_x_per_week",
        required_periods=5,
        friend_user_ids=[],
        target=10,
        current=0,
        now=at("2026-06-01T12:00:00"),
    )

    persistence.update_goal_progress(goal["id"], alice["user_id"], skipped=True, now=at("2026-06-01T13:00:00"))
    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-02T08:00:00"))
    persistence.update_goal_progress(goal["id"], alice["user_id"], skipped=True, now=at("2026-06-02T13:00:00"))
    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-03T08:00:00"))
    persistence.update_goal_progress(goal["id"], alice["user_id"], skipped=True, now=at("2026-06-03T13:00:00"))
    stats = persistence.account_stats(alice["user_id"], now=at("2026-06-03T14:00:00"))

    activity = stats["activity_days"]
    assert activity["2026-06-01"] == {"active_goals": 1, "fulfilled_goals": 1, "percent": 100.0}
    assert activity["2026-06-02"] == {"active_goals": 1, "fulfilled_goals": 1, "percent": 100.0}
    assert activity["2026-06-03"] == {"active_goals": 1, "fulfilled_goals": 0, "percent": 0.0}


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
    assert participant["completion_streak"] == 2


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


def test_activity_days_repair_runs_once_and_restores_stale_historical_cache(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    persistence = JsonPersistence(path, cache_ttl_seconds=0)
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-07-03T09:00:00"))
    goals = [
        persistence.create_goal(
            created_by="alice",
            description=f"Goal {index}",
            schedule_class="daily",
            required_periods=1,
            friend_user_ids=[],
            target=1,
            current=1,
            now=at("2026-07-03T10:00:00"),
        )
        for index in range(4)
    ]

    persistence.list_goals_for_user(alice["user_id"], now=at("2026-07-04T08:00:00"))
    for goal in goals:
        persistence.update_goal_progress(goal["id"], alice["user_id"], current=1, now=at("2026-07-04T10:00:00"))
    persistence.list_goals_for_user(alice["user_id"], now=at("2026-07-05T08:00:00"))

    data = persistence.raw_data()
    data["user_stats"]["alice"]["activity_days"]["2026-07-03"] = {
        "active_goals": 1,
        "fulfilled_goals": 0,
        "percent": 0.0,
    }
    data["user_stats"]["alice"]["activity_days"]["2026-07-04"] = {
        "active_goals": 1,
        "fulfilled_goals": 0,
        "percent": 0.0,
    }
    data["user_stats"]["alice"].pop("activity_days_repair_version", None)
    path.write_text(json.dumps(data), encoding="utf-8")

    stats = persistence.account_stats(alice["user_id"], now=at("2026-07-05T09:00:00"))

    assert stats["activity_days"]["2026-07-03"] == {
        "active_goals": 4,
        "fulfilled_goals": 4,
        "percent": 100.0,
    }
    assert stats["activity_days"]["2026-07-04"] == {
        "active_goals": 4,
        "fulfilled_goals": 4,
        "percent": 100.0,
    }
    assert persistence.raw_data()["user_stats"]["alice"]["activity_days_repair_version"] == 1

    data = persistence.raw_data()
    data["user_stats"]["alice"]["activity_days"]["2026-07-03"] = {
        "active_goals": 1,
        "fulfilled_goals": 0,
        "percent": 0.0,
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    stats = persistence.account_stats(alice["user_id"], now=at("2026-07-05T10:00:00"))

    assert stats["activity_days"]["2026-07-03"] == {
        "active_goals": 1,
        "fulfilled_goals": 0,
        "percent": 0.0,
    }


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


def test_account_stats_skips_write_when_activity_days_are_current(tmp_path: Path) -> None:
    persistence = CountingJsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    persistence.create_goal(
        created_by="alice",
        description="Drink water",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=[],
        target=1,
        current=1,
        now=at("2026-06-01T12:00:00"),
    )

    persistence.account_stats(alice["user_id"], now=at("2026-06-01T13:00:00"))
    writes_after_refresh = persistence.write_count
    persistence.account_stats(alice["user_id"], now=at("2026-06-01T13:00:00"))

    assert persistence.write_count == writes_after_refresh



def test_mongodb_native_migrates_legacy_app_store_once() -> None:
    database = FakeMongoNativeDatabase()
    database["users"].documents["app_store"] = {
        "_id": "app_store",
        "data": {
            "users": {"alice": {"user_id": "alice", "email": "alice@example.com", "name": "Alice"}},
            "goals": {},
            "friend_invites": {},
            "friend_suggestions": {},
            "friendships": {},
            "user_stats": {},
            "debug": {"time_offset_seconds": 3600},
        },
    }

    persistence = MongoNativePersistence(mongo_database=database)
    again = MongoNativePersistence(mongo_database=database)

    assert persistence.get_user("alice")["email"] == "alice@example.com"
    assert "alice" in database["users_inventory"].documents
    assert "alice" not in database["users"].documents
    assert [user["user_id"] for user in persistence.list_users()] == ["alice"]
    assert database["debug"].documents["debug"]["time_offset_seconds"] == 3600
    assert database["migrations"].documents["native_mongo_v1"]["source_collection"] == "users"
    migration_writes = [call for call in database["migrations"].calls if call[0] == "replace_one"]
    assert len(migration_writes) == 1
    assert again.get_user("alice")["name"] == "Alice"


def test_mongodb_native_goal_progress_uses_targeted_updates() -> None:
    database = FakeMongoNativeDatabase()
    persistence = MongoNativePersistence(mongo_database=database)
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    goal = persistence.create_goal(
        created_by=alice["user_id"],
        description="Run",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=[],
        target=10,
        current=0,
        now=at("2026-06-01T09:01:00"),
    )
    for collection in database.collections.values():
        collection.calls.clear()

    updated = persistence.update_goal_progress(
        goal["id"],
        alice["user_id"],
        current=4,
        now=at("2026-06-01T09:02:00"),
    )

    assert updated["participants"]["alice"]["current"] == 4
    goal_update_calls = [call for call in database["goals"].calls if call[0] == "update_one"]
    assert goal_update_calls
    assert not [call for call in database["goals"].calls if call[0] == "replace_one"]
    assert [call for call in database["users_inventory"].calls if call[0] == "update_one"]
    assert database["goals"].documents[goal["id"]]["participants"]["alice"]["current"] == 4


def test_mongodb_native_list_goals_reads_matching_goal_collection_only() -> None:
    database = FakeMongoNativeDatabase()
    persistence = MongoNativePersistence(mongo_database=database)
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    persistence.create_goal("alice", "Run", "daily", 1, [], 10, now=at("2026-06-01T09:01:00"))
    for collection in database.collections.values():
        collection.calls.clear()

    goals = persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-01T10:00:00"))

    assert [goal["description"] for goal in goals] == ["Run"]
    goal_find_calls = [call for call in database["goals"].calls if call[0] == "find"]
    assert goal_find_calls
    assert goal_find_calls[0][1]["participant_user_ids"] == "alice"
    assert not database["users_inventory"].calls



def test_mongodb_native_list_goals_rolls_over_shared_participants() -> None:
    database = FakeMongoNativeDatabase()
    persistence = MongoNativePersistence(mongo_database=database)
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob", at("2026-06-01T09:01:00"))
    invite = persistence.create_friend_invite(
        alice["user_id"],
        alice["email"],
        bob["email"],
        at("2026-06-01T09:02:00"),
    )
    persistence.respond_friend_invite(invite["id"], bob["user_id"], bob["email"], approve=True, now=at("2026-06-01T09:03:00"))
    goal = persistence.create_goal(
        created_by=alice["user_id"],
        description="Steps",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=[bob["user_id"]],
        target=10,
        current=0,
        now=at("2026-06-01T09:04:00"),
    )
    persistence.update_goal_progress(goal["id"], bob["user_id"], current=10, now=at("2026-06-01T10:00:00"))

    goals = persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-02T08:00:00"))

    bob_participant = goals[0]["participants"]["bob"]
    assert bob_participant["current"] == 0
    assert bob_participant["period_start"] == "2026-06-02T00:00:00+02:00"
    assert bob_participant["period_outcomes"]["2026-06-01"] == {
        "completed": True,
        "skipped": False,
        "fulfilled": True,
        "current": 10,
        "target": 10,
        "percent": 100.0,
    }
    stored_bob = database["goals"].documents[goal["id"]]["participants"]["bob"]
    assert stored_bob["current"] == 0
    assert "2026-06-01" in stored_bob["period_outcomes"]


def test_mongodb_native_add_goal_friends_rolls_over_shared_participants() -> None:
    database = FakeMongoNativeDatabase()
    persistence = MongoNativePersistence(mongo_database=database)
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob", at("2026-06-01T09:01:00"))
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie", at("2026-06-01T09:02:00"))
    bob_invite = persistence.create_friend_invite(
        alice["user_id"],
        alice["email"],
        bob["email"],
        at("2026-06-01T09:03:00"),
    )
    persistence.respond_friend_invite(bob_invite["id"], bob["user_id"], bob["email"], approve=True, now=at("2026-06-01T09:04:00"))
    charlie_invite = persistence.create_friend_invite(
        alice["user_id"],
        alice["email"],
        charlie["email"],
        at("2026-06-01T09:05:00"),
    )
    persistence.respond_friend_invite(
        charlie_invite["id"],
        charlie["user_id"],
        charlie["email"],
        approve=True,
        now=at("2026-06-01T09:06:00"),
    )
    goal = persistence.create_goal(
        created_by=alice["user_id"],
        description="Steps",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=[bob["user_id"]],
        target=10,
        current=0,
        now=at("2026-06-01T09:07:00"),
    )
    persistence.update_goal_progress(goal["id"], bob["user_id"], current=10, now=at("2026-06-01T10:00:00"))

    updated = persistence.add_goal_friends(
        goal["id"],
        alice["user_id"],
        [charlie["user_id"]],
        now=at("2026-06-02T08:00:00"),
    )

    bob_participant = updated["participants"]["bob"]
    assert bob_participant["current"] == 0
    assert bob_participant["period_start"] == "2026-06-02T00:00:00+02:00"
    assert bob_participant["period_outcomes"]["2026-06-01"] == {
        "completed": True,
        "skipped": False,
        "fulfilled": True,
        "current": 10,
        "target": 10,
        "percent": 100.0,
    }
    stored_bob = database["goals"].documents[goal["id"]]["participants"]["bob"]
    assert stored_bob["current"] == 0
    assert "2026-06-01" in stored_bob["period_outcomes"]


def test_mongodb_native_add_goal_friends_does_not_write_rollover_when_current() -> None:
    database = FakeMongoNativeDatabase()
    persistence = MongoNativePersistence(mongo_database=database)
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob", at("2026-06-01T09:01:00"))
    invite = persistence.create_friend_invite(
        alice["user_id"],
        alice["email"],
        bob["email"],
        at("2026-06-01T09:02:00"),
    )
    persistence.respond_friend_invite(invite["id"], bob["user_id"], bob["email"], approve=True, now=at("2026-06-01T09:03:00"))
    goal = persistence.create_goal(
        created_by=alice["user_id"],
        description="Steps",
        schedule_class="daily",
        required_periods=1,
        friend_user_ids=[bob["user_id"]],
        target=10,
        current=0,
        now=at("2026-06-01T09:04:00"),
    )
    for collection in database.collections.values():
        collection.calls.clear()

    persistence.add_goal_friends(goal["id"], alice["user_id"], [bob["user_id"]], now=at("2026-06-01T10:00:00"))

    goal_update_calls = [call for call in database["goals"].calls if call[0] == "update_one"]
    assert goal_update_calls == []


def test_mongodb_native_get_user_uses_cache_inside_ttl() -> None:
    database = FakeMongoNativeDatabase()
    persistence = MongoNativePersistence(mongo_database=database, cache_ttl_seconds=5)
    persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    database["users_inventory"].calls.clear()

    assert persistence.get_user("alice")["name"] == "Alice"
    assert persistence.get_user("alice")["name"] == "Alice"

    find_calls = [call for call in database["users_inventory"].calls if call[0] == "find_one"]
    assert len(find_calls) == 1


def test_mongodb_native_cache_can_be_disabled() -> None:
    database = FakeMongoNativeDatabase()
    persistence = MongoNativePersistence(mongo_database=database, cache_ttl_seconds=0)
    persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    database["users_inventory"].calls.clear()

    persistence.get_user("alice")
    persistence.get_user("alice")

    find_calls = [call for call in database["users_inventory"].calls if call[0] == "find_one"]
    assert len(find_calls) == 2


def test_mongodb_native_list_goals_uses_cached_targeted_query() -> None:
    database = FakeMongoNativeDatabase()
    persistence = MongoNativePersistence(mongo_database=database, cache_ttl_seconds=5)
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    persistence.create_goal("alice", "Run", "daily", 1, [], 10, now=at("2026-06-01T09:01:00"))
    for collection in database.collections.values():
        collection.calls.clear()

    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-01T10:00:00"))
    persistence.list_goals_for_user(alice["user_id"], now=at("2026-06-01T10:00:00"))

    goal_find_calls = [call for call in database["goals"].calls if call[0] == "find"]
    assert len(goal_find_calls) == 1
    assert goal_find_calls[0][1]["participant_user_ids"] == "alice"


def test_mongodb_native_write_clears_cache() -> None:
    database = FakeMongoNativeDatabase()
    persistence = MongoNativePersistence(mongo_database=database, cache_ttl_seconds=5)
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice", at("2026-06-01T09:00:00"))
    goal = persistence.create_goal("alice", "Run", "daily", 1, [], 10, current=0, now=at("2026-06-01T09:01:00"))
    persistence.get_user("alice")
    database["users_inventory"].calls.clear()

    persistence.update_goal_progress(goal["id"], alice["user_id"], current=4, now=at("2026-06-01T09:02:00"))
    user = persistence.get_user("alice")

    assert user["last_seen_at"] == "2026-06-01T07:02:00+00:00"
    find_calls = [call for call in database["users_inventory"].calls if call[0] == "find_one"]
    assert find_calls

def test_factory_creates_mongodb_native_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.db.persistence as persistence_module

    created = {}

    class DummyMongoNativePersistence:
        def __init__(
            self,
            uri: str,
            database: str,
            legacy_collection: str,
            cache_ttl_seconds: float,
        ) -> None:
            created["uri"] = uri
            created["database"] = database
            created["legacy_collection"] = legacy_collection
            created["cache_ttl_seconds"] = cache_ttl_seconds

    monkeypatch.setattr(persistence_module, "MongoNativePersistence", DummyMongoNativePersistence)

    persistence = persistence_module.create_persistence(
        "mongodb_native",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="dogether_test",
        mongodb_collection="legacy_store",
        cache_ttl_seconds=2.5,
    )

    assert isinstance(persistence, DummyMongoNativePersistence)
    assert created == {
        "uri": "mongodb://localhost:27017",
        "database": "dogether_test",
        "legacy_collection": "legacy_store",
        "cache_ttl_seconds": 2.5,
    }

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
        "cache_ttl_seconds": 5.0,
    }


def test_persistence_settings_accept_cache_ttl_seconds() -> None:
    settings = persistence_settings({"persistence": {"cache_ttl_seconds": 2.5}})

    assert settings["cache_ttl_seconds"] == 2.5


def test_factory_passes_cache_ttl_to_backends(tmp_path: Path) -> None:
    json_persistence = create_persistence(
        "json",
        json_path=str(tmp_path / "users.json"),
        cache_ttl_seconds=2,
    )
    mongo_persistence = create_persistence(
        "mongodb",
        mongodb_uri="mongodb://localhost:27017",
        cache_ttl_seconds=3,
    )

    assert json_persistence.cache_ttl_seconds == 2
    assert mongo_persistence.cache_ttl_seconds == 3
    mongo_persistence.close()
