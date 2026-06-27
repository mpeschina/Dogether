from src.pages.main_page import ordered_active_participant_ids


def test_ordered_active_participant_ids_pins_current_user_first() -> None:
    goal = {
        "participant_user_ids": ["alice", "bob", "charlie"],
        "participants": {
            "alice": {"left_at": None},
            "bob": {"left_at": None},
            "charlie": {"left_at": None},
        },
    }

    assert ordered_active_participant_ids(goal, "bob") == ["bob", "alice", "charlie"]


def test_ordered_active_participant_ids_filters_left_participants() -> None:
    goal = {
        "participant_user_ids": ["alice", "bob", "charlie"],
        "participants": {
            "alice": {"left_at": None},
            "bob": {"left_at": "2026-06-01T10:00:00+00:00"},
            "charlie": {"left_at": None},
        },
    }

    assert ordered_active_participant_ids(goal, "alice") == ["alice", "charlie"]


def test_ordered_active_participant_ids_includes_active_participants_missing_from_order() -> None:
    goal = {
        "participant_user_ids": ["alice"],
        "participants": {
            "alice": {"left_at": None},
            "bob": {"left_at": None},
            "charlie": {"left_at": None},
        },
    }

    assert ordered_active_participant_ids(goal, "charlie") == ["charlie", "alice", "bob"]
