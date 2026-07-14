from src.db.json_persistence import JsonPersistence
from src.friends.alerts import pending_friend_request_alert_items
from src.pages.friends_page import _friend_name_with_email
from src.friends.suggestions import friend_suggestion_candidates, manual_friend_suggestion_options


def _friend(persistence: JsonPersistence, first: dict, second: dict) -> None:
    invite = persistence.create_friend_invite(first["user_id"], first["email"], second["email"])
    persistence.respond_friend_invite(invite["id"], second["user_id"], second["email"], approve=True)


def test_manual_friend_suggestion_options_include_unconnected_friends(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)

    friends, options = manual_friend_suggestion_options(persistence, "alice")

    assert [friend["user_id"] for friend in friends] == ["bob", "charlie"]
    assert options == {"bob": [charlie], "charlie": [bob]}


def test_manual_friend_suggestion_options_exclude_existing_friendship(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    _friend(persistence, bob, charlie)

    _friends, options = manual_friend_suggestion_options(persistence, "alice")

    assert options == {"bob": [], "charlie": []}


def test_manual_friend_suggestion_options_exclude_pending_suggestions(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    persistence.create_friend_suggestion("alice", ["bob", "charlie"])

    _friends, options = manual_friend_suggestion_options(persistence, "alice")

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

    _friends, options = manual_friend_suggestion_options(persistence, "alice")

    assert options == {"bob": [], "charlie": []}


def test_manual_friend_suggestion_options_require_two_friends(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    _friend(persistence, alice, bob)

    friends, options = manual_friend_suggestion_options(persistence, "alice")

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

    candidates = friend_suggestion_candidates(persistence, "alice")

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

    candidates = friend_suggestion_candidates(persistence, "alice")

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

    assert friend_suggestion_candidates(persistence, "alice") == []


def test_dismissed_pairs_do_not_hide_manual_friend_suggestion_options(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    persistence.dismiss_friend_suggestion_pair("alice", "charlie", "bob")

    _friends, options = manual_friend_suggestion_options(persistence, "alice")

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

    assert friend_suggestion_candidates(persistence, "alice") == []


def test_friend_suggestion_candidates_exclude_pending_and_declined_suggestions(tmp_path) -> None:
    persistence = JsonPersistence(tmp_path / "users.json")
    alice = persistence.upsert_user("alice", "alice@example.com", "Alice")
    bob = persistence.upsert_user("bob", "bob@example.com", "Bob")
    charlie = persistence.upsert_user("charlie", "charlie@example.com", "Charlie")
    _friend(persistence, alice, bob)
    _friend(persistence, alice, charlie)
    goal = persistence.create_goal("alice", "Read", "daily", 1, ["bob", "charlie"], 10)
    suggestion = persistence.create_friend_suggestion("alice", ["bob", "charlie"], source_goal_id=goal["id"])

    assert friend_suggestion_candidates(persistence, "alice") == []

    persistence.respond_friend_suggestion(suggestion["id"], "bob", approve=False)

    assert friend_suggestion_candidates(persistence, "alice") == []


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

