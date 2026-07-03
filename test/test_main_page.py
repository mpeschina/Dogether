from datetime import datetime

from src.pages.main_page import (
    MINI_ACTIVITY_COLORS,
    compact_goal_activity_html,
    participant_name_with_progress_html,
    participant_progress_label,
    ordered_active_participant_ids,
    truncate_participant_name,
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
    assert "participant-progress-row" in html


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _goal(schedule_class: str, required_periods: int = 1, participant: dict | None = None) -> dict:
    return {
        "id": "goal_1",
        "schedule_class": schedule_class,
        "required_periods": required_periods,
        "participants": {
            "alice": participant
            or {
                "current": 0,
                "target": 10,
                "skipped": False,
                "period_outcomes": {},
            }
        },
    }


def test_truncate_participant_name_keeps_twenty_five_characters() -> None:
    assert truncate_participant_name("Ada Lovelace") == "Ada Lovelace"
    assert truncate_participant_name("ABCDEFGHIJKLMNOPQRSTUVWXYZ") == "ABCDEFGHIJKLMNOPQRSTUV..."


def test_participant_name_with_progress_truncates_and_escapes_name() -> None:
    html = participant_name_with_progress_html("ABCDEFGHIJKLMNOPQRSTUVWX<danger>", "1/2")

    assert "ABCDEFGHIJKLMNOPQRSTUV..." in html
    assert "title='ABCDEFGHIJKLMNOPQRSTUVWX&lt;danger&gt;'" in html
    assert "<danger>" not in html


def test_compact_goal_activity_renders_daily_current_week_seven_dots() -> None:
    participant = {"current": 0, "target": 10, "skipped": False, "period_outcomes": {}}
    html = compact_goal_activity_html(
        _goal("daily", participant=participant),
        participant,
        now=_at("2026-06-03T12:00:00"),
    )

    assert html.count("class='mini-activity-dot'") == 7
    assert "2026-06-01" in html
    assert "2026-06-07" in html


def test_compact_goal_activity_renders_daily_skipped_unfulfilled_as_grey() -> None:
    participant = {
        "current": 0,
        "target": 10,
        "skipped": False,
        "period_outcomes": {"2026-06-02": {"completed": False, "skipped": True, "fulfilled": False}},
    }
    html = compact_goal_activity_html(
        _goal("daily", participant=participant),
        participant,
        now=_at("2026-06-03T12:00:00"),
    )

    assert f"background:{MINI_ACTIVITY_COLORS[0]}" in html
    assert f"background:{MINI_ACTIVITY_COLORS[4]}" not in html


def test_compact_goal_activity_daily_x_per_week_surplus_miss_stays_green_until_allowance_exceeded() -> None:
    participant = {
        "current": 0,
        "target": 10,
        "skipped": True,
        "period_outcomes": {
            "2026-06-01": {"completed": False, "skipped": True, "fulfilled": True},
            "2026-06-02": {"completed": False, "skipped": True, "fulfilled": True},
        },
    }
    goal = _goal("daily_x_per_week", required_periods=5, participant=participant)
    html = compact_goal_activity_html(goal, participant, now=_at("2026-06-03T12:00:00"))

    assert html.count(f"background:{MINI_ACTIVITY_COLORS[4]}") == 2
    assert html.count(f"background:{MINI_ACTIVITY_COLORS[0]}") == 5

    goal["required_periods"] = 4
    html = compact_goal_activity_html(goal, participant, now=_at("2026-06-03T12:00:00"))

    assert html.count(f"background:{MINI_ACTIVITY_COLORS[4]}") == 3


def test_compact_goal_activity_renders_weekly_current_month_dots() -> None:
    participant = {"current": 0, "target": 10, "skipped": False, "period_outcomes": {}}
    html = compact_goal_activity_html(
        _goal("weekly", participant=participant),
        participant,
        now=_at("2026-06-15T12:00:00"),
    )

    assert html.count("class='mini-activity-dot'") == 5
    assert "2026-06-01" in html
    assert "2026-06-29" in html


def test_compact_goal_activity_uses_period_outcomes_from_current_goal_only() -> None:
    first_participant = {
        "current": 0,
        "target": 10,
        "skipped": False,
        "period_outcomes": {"2026-06-01": {"completed": True, "fulfilled": True}},
    }
    second_participant = {"current": 0, "target": 10, "skipped": False, "period_outcomes": {}}

    first_html = compact_goal_activity_html(
        _goal("daily", participant=first_participant),
        first_participant,
        now=_at("2026-06-03T12:00:00"),
    )
    second_html = compact_goal_activity_html(
        _goal("daily", participant=second_participant),
        second_participant,
        now=_at("2026-06-03T12:00:00"),
    )

    assert f"background:{MINI_ACTIVITY_COLORS[4]}" in first_html
    assert f"background:{MINI_ACTIVITY_COLORS[4]}" not in second_html
