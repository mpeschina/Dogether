import scripts.migration_personal_highlights as migration
from scripts.migration_personal_highlights import planned_personal_highlight_updates


class _Collection:
    def __init__(self, documents):
        self.documents = documents
        self.update_calls = []

    def find(self, query, projection=None):
        del projection
        if query == {"archived_at": None}:
            return [document for document in self.documents if document.get("archived_at") is None]
        return list(self.documents)

    def update_one(self, query, update):
        self.update_calls.append((query, update))


class _Client:
    def __init__(self, database):
        self.database = database
        self.closed = False

    def __getitem__(self, name):
        assert name == "dogether"
        return self.database

    def close(self):
        self.closed = True


def test_planned_personal_highlights_use_largest_current_or_historical_numeric_value() -> None:
    users = [{"_id": "alice", "personal_bests": {}}]
    goals = [
        {
            "id": "steps",
            "archived_at": None,
            "participants": {
                "alice": {
                    "target": 10,
                    "current": 12,
                    "period_start": "2026-06-03T00:00:00+02:00",
                    "period_outcomes": {
                        "2026-06-01": {"target": 10, "current": 20},
                        "2026-06-02": {"target": 10, "current": 15},
                    },
                }
            },
        }
    ]

    assert planned_personal_highlight_updates(goals, users) == {
        "alice": {
            "steps": {
                "repetitions": 20,
                "achieved_at": "2026-06-01T00:00:00+02:00",
            }
        }
    }


def test_planned_personal_highlights_skip_binary_zero_departed_and_unknown_users() -> None:
    users = [{"_id": "alice", "personal_bests": {}}]
    goals = [
        {
            "id": "mixed",
            "archived_at": None,
            "participants": {
                "alice": {"target": 1, "current": 8, "period_start": "2026-06-01T00:00:00+02:00"},
                "bob": {"target": 5, "current": 9, "period_start": "2026-06-01T00:00:00+02:00"},
                "carol": {
                    "target": 5,
                    "current": 9,
                    "period_start": "2026-06-01T00:00:00+02:00",
                    "left_at": "2026-06-01T12:00:00+02:00",
                },
            },
        }
    ]

    assert planned_personal_highlight_updates(goals, users) == {}


def test_planned_personal_highlights_only_replace_strictly_higher_existing_records() -> None:
    goals = [
        {
            "id": "run",
            "participants": {
                "alice": {"target": 5, "current": 12, "period_start": "2026-06-02T00:00:00+02:00"},
                "bob": {"target": 5, "current": 12, "period_start": "2026-06-02T00:00:00+02:00"},
            },
        }
    ]
    users = [
        {"_id": "alice", "personal_bests": {"run": {"repetitions": 12, "achieved_at": "2026-06-01T00:00:00+02:00"}}},
        {"_id": "bob", "personal_bests": {"run": {"repetitions": 11, "achieved_at": "2026-06-01T00:00:00+02:00"}}},
    ]

    assert planned_personal_highlight_updates(goals, users) == {
        "bob": {
            "run": {
                "repetitions": 12,
                "achieved_at": "2026-06-02T00:00:00+02:00",
            }
        }
    }


def test_migration_is_dry_run_by_default_and_writes_with_apply(tmp_path, monkeypatch, capsys) -> None:
    secrets_path = tmp_path / "secrets.toml"
    secrets_path.write_text(
        "[persistence]\nbackend = 'mongodb_native'\nmongodb_uri = 'mongodb://example'\nmongodb_database = 'dogether'\n"
    )
    users = _Collection([{"_id": "alice", "personal_bests": {}}])
    goals = _Collection(
        [
            {
                "id": "run",
                "archived_at": None,
                "participants": {
                    "alice": {"target": 5, "current": 9, "period_start": "2026-06-01T00:00:00+02:00"}
                },
            }
        ]
    )
    client = _Client({"users_inventory": users, "goals": goals})
    monkeypatch.setattr(migration, "MongoClient", lambda uri: client)

    assert migration.main(["--secrets-path", str(secrets_path)]) == 0
    assert goals.update_calls == []
    assert "Dry run: no changes written" in capsys.readouterr().out

    assert migration.main(["--secrets-path", str(secrets_path), "--apply"]) == 0
    assert users.update_calls == [
        (
            {"_id": "alice"},
            {
                "$set": {
                    "personal_bests.run": {
                        "repetitions": 9,
                        "achieved_at": "2026-06-01T00:00:00+02:00",
                    }
                }
            },
        )
    ]
    assert client.closed is True
