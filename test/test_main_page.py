from src.pages.main_page import (
    participant_name_with_progress_html,
    participant_progress_label,
    ordered_active_participant_ids,
)


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


def test_participant_progress_label_uses_compact_current_target() -> None:
    assert participant_progress_label(0, 10, False) == "0/10"


def test_participant_name_with_progress_keeps_progress_inline_and_escaped() -> None:
    html = participant_name_with_progress_html("Ada <L>", "0/10")

    assert "Ada &lt;L&gt;" in html
    assert "0/10" in html
    assert "white-space:nowrap" in html
