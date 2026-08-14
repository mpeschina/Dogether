from src.db.json_persistence import JsonPersistence
from src.friends.alerts import pending_friend_request_alert_items
from src.pages.friends_page import (
    _dismiss_all_friend_suggestion_candidates,
    _has_stars,
    _friend_name_with_email,
    _ranked_friends,
    _star_count,
)
from src.friends.suggestions import (
    friend_suggestion_candidates,
    load_friend_suggestion_data,
    manual_friend_suggestion_options,
)


def _friend(persistence: JsonPersistence, first: dict, second: dict) -> None:
    invite = persistence.create_friend_invite(first["user_id"], first["email"], second["email"])
    persistence.respond_friend_invite(invite["id"], second["user_id"], second["email"], approve=True)


def _suggestion_data(persistence: JsonPersistence, user_id: str):
    return load_friend_suggestion_data(persistence, user_id)


class CountingSuggestionPersistence(JsonPersistence):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.friend_list_calls = 0
        self.bulk_friendship_calls = 0
        self.bulk_suggestion_calls = 0

    def list_friends(self, user_id: str) -> list[dict]:
        self.friend_list_calls += 1
        return super().list_friends(user_id)

    def list_active_friendships_for_users(self, user_ids: list[str]) -> list[dict]:
        self.bulk_friendship_calls += 1
        return super().list_active_friendships_for_users(user_ids)

    def list_friend_suggestions_for_users(self, user_ids: list[str]) -> list[dict]:
        self.bulk_suggestion_calls += 1
        return super().list_friend_suggestions_for_users(user_ids)

    def list_friend_suggestions_for_pair(self, first_user_id: str, second_user_id: str) -> list[dict]:
        raise AssertionError("Suggestion calculations must use the preloaded snapshot.")


def test_star_count_normalizes_missing_and_invalid_assistant_state() -> None:
    assert _star_count({"user_id": "missing"}) == 0
    assert _star_count({"user_id": "invalid", "assistant_state": {"schema_version": 5, "stars": "invalid"}}) == 0
    assert _star_count({"user_id": "earned", "assistant_state": {"schema_version": 5, "stars": 4}}) == 4


def test_ranked_friends_order_by_stars_then_profile_identity() -> None:
    friends = [
        {"user_id": "zara", "name": "Zara", "email": "zara@example.com", "assistant_state": {"schema_version": 5, "stars": 1}},
        {"user_id": "bob", "name": "Bob", "email": "bob@example.com", "assistant_state": {"schema_version": 5, "stars": 3}},
        {"user_id": "alex", "name": "Alex", "email": "alex@example.com", "assistant_state": {"schema_version": 5, "stars": 1}},
        {"user_id": "unknown", "name": "Unknown", "email": "unknown@example.com"},
    ]

    ranked = _ranked_friends(friends)

    assert [friend["user_id"] for friend in ranked] == ["bob", "alex", "zara", "unknown"]
    assert _star_count(ranked[-1]) == 0


def test_friend_star_display_is_gated_by_current_user_progress() -> None:
    no_stars = {"user_id": "new-user", "assistant_state": {"schema_version": 5, "stars": 0}}
    earned_stars = {"user_id": "earned-user", "assistant_state": {"schema_version": 5, "stars": 1}}

    assert not _has_stars(no_stars)
    assert _has_stars(earned_stars)


def test_manual_friend_suggestion_options_include_unconnected_friends(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)

    friends, options = manual_friend_suggestion_options(_suggestion_data(persistence, "alice"))

    assert [friend["user_id"] for friend in friends] == ["bob", "charlie"]
    assert options == {"bob": [charlie], "charlie": [bob]}


def test_suggestion_calculations_use_one_bulk_relationship_and_suggestion_read(tmp_path) -> None:
    persistence = CountingSuggestionPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    persistence.create_goal("alice", "Read", "daily", 1, ["bob", "charlie"], 10)
    persistence.friend_list_calls = 0

    data = _suggestion_data(persistence, "alice")
    candidates = friend_suggestion_candidates(data)
    _friends, options = manual_friend_suggestion_options(data)

    assert persistence.friend_list_calls == 1
    assert persistence.bulk_friendship_calls == 1
    assert persistence.bulk_suggestion_calls == 1
    assert candidates[0]["first_user"] == bob
    assert options == {"bob": [charlie], "charlie": [bob]}


def test_manual_friend_suggestion_options_exclude_existing_friendship(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    _friend(persistence, bob, charlie)

    _friends, options = manual_friend_suggestion_options(_suggestion_data(persistence, "alice"))

    assert options == {"bob": [], "charlie": []}


def test_manual_friend_suggestion_options_exclude_pending_suggestions(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    persistence.create_friend_suggestion("alice", ["bob", "charlie"])

    _friends, options = manual_friend_suggestion_options(_suggestion_data(persistence, "alice"))

    assert options == {"bob": [], "charlie": []}


def test_manual_friend_suggestion_options_exclude_declined_manual_suggestions(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    suggestion = persistence.create_friend_suggestion("alice", ["bob", "charlie"])
    persistence.respond_friend_suggestion(suggestion["id"], "bob", approve=False)

    _friends, options = manual_friend_suggestion_options(_suggestion_data(persistence, "alice"))

    assert options == {"bob": [], "charlie": []}


def test_manual_friend_suggestion_options_require_two_friends(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    _friend(persistence, alice, bob)

    friends, options = manual_friend_suggestion_options(_suggestion_data(persistence, "alice"))

    assert friends == [bob]
    assert options == {}


def test_friend_suggestion_candidates_find_non_friend_goal_participants(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    goal = persistence.create_goal("alice", "Read", "daily", 1, ["bob", "charlie"], 10)

    candidates = friend_suggestion_candidates(_suggestion_data(persistence, "alice"))

    assert candidates == [
        {
            "goal_id": goal["id"],
            "goal_description": "Read",
            "first_user": bob,
            "second_user": charlie,
        }
    ]


def test_friend_suggestion_candidates_show_pair_once_across_multiple_goals(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    first_goal = persistence.create_goal("alice", "Pushups", "daily", 1, ["bob", "charlie"], 10)
    persistence.create_goal("alice", "Pullups", "daily", 1, ["charlie", "bob"], 10)

    candidates = friend_suggestion_candidates(_suggestion_data(persistence, "alice"))

    assert candidates == [
        {
            "goal_id": first_goal["id"],
            "goal_description": "Pushups",
            "first_user": bob,
            "second_user": charlie,
        }
    ]


def test_friend_suggestion_candidates_exclude_dismissed_pairs(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    persistence.create_goal("alice", "Read", "daily", 1, ["bob", "charlie"], 10)
    persistence.dismiss_friend_suggestion_pair("alice", "charlie", "bob")

    assert friend_suggestion_candidates(_suggestion_data(persistence, "alice")) == []


def test_dismissed_pairs_do_not_hide_manual_friend_suggestion_options(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    persistence.dismiss_friend_suggestion_pair("alice", "charlie", "bob")

    _friends, options = manual_friend_suggestion_options(_suggestion_data(persistence, "alice"))

    assert options == {"bob": [charlie], "charlie": [bob]}


def test_friend_suggestion_candidates_exclude_existing_friendship(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    _friend(persistence, bob, charlie)
    persistence.create_goal("alice", "Read", "daily", 1, ["bob", "charlie"], 10)

    assert friend_suggestion_candidates(_suggestion_data(persistence, "alice")) == []


def test_friend_suggestion_candidates_exclude_pending_and_declined_suggestions(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    goal = persistence.create_goal("alice", "Read", "daily", 1, ["bob", "charlie"], 10)
    suggestion = persistence.create_friend_suggestion("alice", ["bob", "charlie"], source_goal_id=goal["id"])

    assert friend_suggestion_candidates(_suggestion_data(persistence, "alice")) == []

    persistence.respond_friend_suggestion(suggestion["id"], "bob", approve=False)

    assert friend_suggestion_candidates(_suggestion_data(persistence, "alice")) == []


def test_pending_friend_request_alert_items_include_suggestions(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    invite = persistence.create_friend_invite(alice["user_id"], alice["email"], bob["email"])
    suggestion = persistence.create_friend_suggestion(
        alice["user_id"],
        [bob["user_id"], charlie["user_id"]],
    )

    assert pending_friend_request_alert_items(persistence, bob["email"], bob["user_id"]) == [
        ("invite", invite["id"]),
        ("suggestion", suggestion["id"]),
    ]


def test_friend_name_with_email_can_include_compact_note() -> None:
    label = _friend_name_with_email(
        {"user_id": "mareike", "name": "Mareike Mandtler", "email": "mandtler.m@outlook.de"},
        note="suggested by Sören Rinne",
    )

    assert label == "Mareike Mandtler (mandtler.m@outlook.de, suggested by Sören Rinne)"


def test_dismiss_all_friend_suggestion_candidates_hides_every_displayed_pair() -> None:
    class RecordingPersistence:
        def __init__(self) -> None:
            self.dismissed_pairs: list[tuple[str, str, str]] = []

        def dismiss_friend_suggestion_pair(
            self,
            user_id: str,
            first_friend_id: str,
            second_friend_id: str,
            now=None,
        ) -> dict:
            self.dismissed_pairs.append((user_id, first_friend_id, second_friend_id))
            return {}

    candidates = [
        {"first_user": {"user_id": "bob"}, "second_user": {"user_id": "charlie"}},
        {"first_user": {"user_id": "dana"}, "second_user": {"user_id": "eli"}},
    ]
    persistence = RecordingPersistence()

    _dismiss_all_friend_suggestion_candidates(candidates, persistence, "alice", now=None)

    assert persistence.dismissed_pairs == [
        ("alice", "bob", "charlie"),
        ("alice", "dana", "eli"),
    ]
