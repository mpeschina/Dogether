from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.push.storage import JsonPushStorage, MongoPushStorage

BERLIN = ZoneInfo("Europe/Berlin")


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=BERLIN)


def subscription(endpoint: str = "https://push.example/one") -> dict:
    return {
        "endpoint": endpoint,
        "keys": {
            "p256dh": "p256dh-key",
            "auth": "auth-key",
        },
    }


class FakeMongoCollection:
    def __init__(self) -> None:
        self.documents = {}

    def find_one(self, query: dict) -> dict | None:
        document = self.documents.get(query["_id"])
        return dict(document) if document else None

    def replace_one(self, query: dict, replacement: dict, upsert: bool = False) -> None:
        assert upsert is True
        self.documents[query["_id"]] = dict(replacement)

    def delete_one(self, query: dict) -> None:
        self.documents.pop(query["_id"], None)

    def find(self, query: dict):
        return [dict(document) for document in self.documents.values() if document.get("user_id") == query["user_id"]]


def test_json_push_storage_saves_updates_and_deletes_by_endpoint(tmp_path: Path) -> None:
    storage = JsonPushStorage(tmp_path / "push_subscriptions.json")

    first = storage.save_subscription(
        "alice",
        "Alice@Example.com",
        subscription(),
        user_agent="first-agent",
        now=at("2026-06-01T09:00:00"),
    )
    second = storage.save_subscription(
        "alice",
        "alice@example.com",
        subscription(),
        user_agent="second-agent",
        now=at("2026-06-01T10:00:00"),
    )

    assert first["created_at"] == second["created_at"]
    assert second["updated_at"] != first["updated_at"]
    assert second["user_email"] == "alice@example.com"
    assert second["user_agent"] == "second-agent"
    assert len(storage.subscriptions_for_user("alice")) == 1

    storage.delete_subscription("https://push.example/one")

    assert storage.subscriptions_for_user("alice") == []


def test_json_push_storage_allows_multiple_endpoints_per_user(tmp_path: Path) -> None:
    storage = JsonPushStorage(tmp_path / "push_subscriptions.json")

    storage.save_subscription("alice", "alice@example.com", subscription("https://push.example/one"))
    storage.save_subscription("alice", "alice@example.com", subscription("https://push.example/two"))
    storage.save_subscription("bob", "bob@example.com", subscription("https://push.example/three"))

    endpoints = {record["endpoint"] for record in storage.subscriptions_for_user("alice")}

    assert endpoints == {"https://push.example/one", "https://push.example/two"}


def test_json_push_storage_rejects_invalid_subscription(tmp_path: Path) -> None:
    storage = JsonPushStorage(tmp_path / "push_subscriptions.json")

    with pytest.raises(ValueError, match="missing endpoint"):
        storage.save_subscription("alice", "alice@example.com", {"keys": {"p256dh": "x", "auth": "y"}})

    with pytest.raises(ValueError, match="missing keys"):
        storage.save_subscription("alice", "alice@example.com", {"endpoint": "https://push.example/one"})


def test_mongo_push_storage_uses_endpoint_as_document_id() -> None:
    collection = FakeMongoCollection()
    storage = MongoPushStorage(mongo_collection=collection)

    storage.save_subscription("alice", "alice@example.com", subscription("https://push.example/one"))
    storage.save_subscription("alice", "alice@example.com", subscription("https://push.example/two"))

    assert set(collection.documents) == {"https://push.example/one", "https://push.example/two"}
    assert len(storage.subscriptions_for_user("alice")) == 2

    storage.delete_subscription("https://push.example/one")

    assert set(collection.documents) == {"https://push.example/two"}
