from pathlib import Path

import pytest

from src.db.persistence import JsonPersistence, create_persistence, persistence_settings


def test_unknown_user_gets_default_state(tmp_path: Path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")

    assert persistence.get_user("new-user") == {"count": 0, "text": ""}


def test_states_are_saved_per_user(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    persistence = JsonPersistence(path)
    persistence.save_user("alice", {"count": 3, "text": "hello"})
    persistence.save_user("bob", {"count": 8, "text": "world"})

    reloaded = JsonPersistence(path)

    assert reloaded.get_user("alice") == {"count": 3, "text": "hello"}
    assert reloaded.get_user("bob") == {"count": 8, "text": "world"}


def test_factory_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="Unsupported persistence backend"):
        create_persistence("sql")


def test_persistence_settings_come_from_secrets() -> None:
    assert persistence_settings({"persistence": {"json_path": "custom/users.json"}}) == {
        "backend": "json",
        "json_path": "custom/users.json",
        "mongodb_uri": "",
        "mongodb_database": "dogether",
        "mongodb_collection": "users",
    }
