from datetime import datetime
from zoneinfo import ZoneInfo

from src.pages.correct_inputs_page import editable_period_starts, period_label

BERLIN = ZoneInfo("Europe/Berlin")


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=BERLIN)


def test_editable_period_starts_returns_last_completed_daily_periods_after_goal_creation() -> None:
    goal = {
        "created_at": at("2026-06-01T12:00:00").astimezone(ZoneInfo("UTC")).isoformat(),
        "schedule_class": "daily",
        "required_periods": 1,
    }

    starts = editable_period_starts(goal, now=at("2026-06-04T10:00:00"), lookback_periods=14)

    assert [start.date().isoformat() for start in starts] == ["2026-06-03", "2026-06-02", "2026-06-01"]


def test_period_label_formats_weekly_period_range() -> None:
    goal = {"schedule_class": "weekly", "required_periods": 1}

    assert period_label(goal, at("2026-06-01T00:00:00")) == "Week of 2026-06-01 to 2026-06-07"
