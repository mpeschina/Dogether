from datetime import datetime, timezone

from src.assistant.core import AssistantCard, AssistantContext, AssistantLine, AssistantSelection
from src.assistant.state import AssistantState
from src.assistant.stories.weekly_summary import (
    SELECT_SCENE,
    SUMMARY_SCENE,
    WEEKLY_SUMMARY_STORY_ID,
    WeeklySummaryStory,
    _analyse,
)


def _context(now: datetime) -> AssistantContext:
    outcomes = {
        f"2026-07-{day:02d}": {"fulfilled": day != 22, "skipped": False}
        for day in range(20, 31)
    }
    return AssistantContext(
        user_id="alice",
        current_user={},
        state=AssistantState(),
        session_state={},
        current_page_key="help",
        now=now,
        user_state={
            "goals": [
                {
                    "description": "Walking",
                    "participants": {"alice": {"period_outcomes": outcomes}},
                }
            ]
        },
    )


def test_monday_automatically_analyses_last_week() -> None:
    turn = WeeklySummaryStory().advance(
        _context(datetime(2026, 7, 27, tzinfo=timezone.utc)), SELECT_SCENE, None
    )

    assert turn.scene_id == SUMMARY_SCENE
    assert turn.lines[0].text == "Let’s look at last week."
    assert turn.cards[0].title == "WEEKLY COMPLETION"
    assert turn.event_updates["weekly_summary.selection"]["partial"] is False


def test_thursday_offers_this_or_last_week_and_marks_current_week_partial() -> None:
    story = WeeklySummaryStory()
    context = _context(datetime(2026, 7, 30, tzinfo=timezone.utc))
    prompt = story.advance(context, SELECT_SCENE, None)
    turn = story.advance(
        context,
        SELECT_SCENE,
        AssistantSelection(WEEKLY_SUMMARY_STORY_ID, SELECT_SCENE, "this", "This week"),
    )

    assert [choice.label for choice in prompt.choices] == ["This week", "Last week"]
    assert turn.lines[0].text == "This week is still moving."
    assert turn.cards[0].title == "COMPLETION SO FAR"


def test_week_selection_uses_the_apps_local_weekday() -> None:
    story = WeeklySummaryStory()
    # Wednesday in UTC, but already Thursday in the app's Europe/Berlin zone.
    context = _context(datetime(2026, 7, 29, 22, 30, tzinfo=timezone.utc))

    prompt = story.advance(context, SELECT_SCENE, None)

    assert prompt.scene_id == SELECT_SCENE
    assert [choice.label for choice in prompt.choices] == ["This week", "Last week"]


def test_completed_summary_groups_analysis_and_keeps_cards_adjacent() -> None:
    turn = WeeklySummaryStory().advance(
        _context(datetime(2026, 7, 27, tzinfo=timezone.utc)), SELECT_SCENE, None
    )

    assert [type(item) for item in turn.content[:5]] == [
        AssistantLine,
        AssistantLine,
        AssistantLine,
        AssistantCard,
        AssistantLine,
    ]
    assert turn.content[2].text == "First, the big picture."
    assert turn.content[3].title == "WEEKLY COMPLETION"
    assert not turn.content[4].text.startswith("**")
    assert "\n" in turn.content[-1].text
    assert len(turn.lines) <= 12


def test_allowance_skip_preserves_daily_streak_without_claiming_completion() -> None:
    outcomes = {
        f"2026-07-{day:02d}": {"fulfilled": True, "completed": day != 22, "skipped": day == 22}
        for day in range(20, 27)
    }
    context = AssistantContext(
        user_id="alice", current_user={}, state=AssistantState(), session_state={}, current_page_key="help",
        now=datetime(2026, 7, 27, tzinfo=timezone.utc),
        user_state={"goals": [{"description": "Exercise", "schedule_class": "daily_x_per_week", "participants": {"alice": {"period_outcomes": outcomes}}}]},
    )

    streak = _analyse(context, datetime(2026, 7, 20, tzinfo=timezone.utc).date(), False).goals[0].streak

    assert streak.value == 7
    assert streak.unit == "days"
    assert streak.valid_skips == 1
    assert "×" in streak.symbols


def test_weekly_streak_uses_weeks_and_open_week_does_not_extend_it() -> None:
    outcomes = {
        "2026-07-06": {"fulfilled": True},
        "2026-07-13": {"fulfilled": True},
        "2026-07-20": {"fulfilled": True},
    }
    context = AssistantContext(
        user_id="alice", current_user={}, state=AssistantState(), session_state={}, current_page_key="help",
        now=datetime(2026, 7, 30, tzinfo=timezone.utc),
        user_state={"goals": [{"description": "Reading", "schedule_class": "weekly", "participants": {"alice": {"period_outcomes": outcomes, "period_start": "2026-07-27", "current": 1, "target": 1}}}]},
    )

    streak = _analyse(context, datetime(2026, 7, 27, tzinfo=timezone.utc).date(), True).goals[0].streak

    assert streak.value == 3
    assert streak.unit == "weeks"


def test_streak_break_and_restart_are_detected_inside_selected_week() -> None:
    outcomes = {
        **{f"2026-07-{day:02d}": {"fulfilled": True} for day in range(13, 23)},
        "2026-07-23": {"fulfilled": False, "skipped": False},
        "2026-07-24": {"fulfilled": True},
        "2026-07-25": {"fulfilled": True},
        "2026-07-26": {"fulfilled": True},
    }
    context = AssistantContext(
        user_id="alice", current_user={}, state=AssistantState(), session_state={}, current_page_key="help",
        now=datetime(2026, 7, 27, tzinfo=timezone.utc),
        user_state={"goals": [{"description": "Jogging", "participants": {"alice": {"period_outcomes": outcomes}}}]},
    )

    streak = _analyse(context, datetime(2026, 7, 20, tzinfo=timezone.utc).date(), False).goals[0].streak

    assert (streak.ended, streak.ended_value, streak.restarted, streak.restart_delay, streak.value) == (True, 10, True, 1, 3)


def test_valid_allowance_is_excused_without_being_counted_as_completion() -> None:
    outcomes = {
        "2026-07-20": {
            "completed": True,
            "fulfilled": True,
            "skipped": False,
            "current": 10,
            "target": 10,
        },
        "2026-07-21": {
            "completed": False,
            "fulfilled": True,
            "skipped": True,
            "current": 0,
            "target": 10,
        },
        "2026-07-22": {
            "completed": False,
            "fulfilled": False,
            "skipped": True,
            "current": 0,
            "target": 10,
        },
    }
    context = AssistantContext(
        user_id="alice",
        current_user={},
        state=AssistantState(),
        session_state={},
        current_page_key="help",
        now=datetime(2026, 7, 27, tzinfo=timezone.utc),
        user_state={
            "goals": [
                {
                    "description": "Exercise",
                    "schedule_class": "daily_x_per_week",
                    "participants": {"alice": {"period_outcomes": outcomes}},
                }
            ]
        },
    )

    result = _analyse(context, datetime(2026, 7, 20, tzinfo=timezone.utc).date(), False)

    assert (result.fulfilled, result.active, result.skipped, result.rate) == (1, 2, 1, 50)
    assert result.daily[1][1:] == (0, 0)
    assert result.daily[2][1:] == (1, 0)


def test_near_miss_is_selected_as_a_helpful_focus_insight() -> None:
    outcomes = {
        f"2026-07-{day:02d}": {
            "completed": day != 22,
            "fulfilled": day != 22,
            "skipped": False,
            "current": 9 if day == 22 else 10,
            "target": 10,
            "percent": 90 if day == 22 else 100,
        }
        for day in range(20, 27)
    }
    context = AssistantContext(
        user_id="alice",
        current_user={},
        state=AssistantState(),
        session_state={},
        current_page_key="help",
        now=datetime(2026, 7, 27, tzinfo=timezone.utc),
        user_state={
            "goals": [
                {
                    "description": "Reading",
                    "participants": {"alice": {"period_outcomes": outcomes}},
                }
            ]
        },
    )

    turn = WeeklySummaryStory().advance(context, SELECT_SCENE, None)

    near_miss = next(card for card in turn.cards if card.title == "NEAR MISS")
    assert near_miss.value == "Reading"
    assert near_miss.progress == 90
    assert "1 short" in next(
        line.text for line in turn.lines if "binary score" in line.text
    )


def test_substantial_daily_goal_outranks_a_perfect_weekly_one_off() -> None:
    daily = {
        f"2026-07-{day:02d}": {"completed": day != 22, "fulfilled": day != 22}
        for day in range(20, 27)
    }
    context = AssistantContext(
        user_id="alice",
        current_user={},
        state=AssistantState(),
        session_state={},
        current_page_key="help",
        now=datetime(2026, 7, 27, tzinfo=timezone.utc),
        user_state={
            "goals": [
                {
                    "description": "Walking",
                    "schedule_class": "daily",
                    "participants": {"alice": {"period_outcomes": daily}},
                },
                {
                    "description": "Weekly planning",
                    "schedule_class": "weekly",
                    "participants": {
                        "alice": {
                            "period_outcomes": {
                                "2026-07-20": {"completed": True, "fulfilled": True}
                            }
                        }
                    },
                },
            ]
        },
    )

    turn = WeeklySummaryStory().advance(context, SELECT_SCENE, None)

    strongest = next(card for card in turn.cards if card.title == "STRONGEST GOAL")
    assert strongest.value == "Walking"


def test_week_result_exposes_perfect_and_progress_days() -> None:
    outcomes = {
        "2026-07-20": {"completed": True, "fulfilled": True, "current": 10, "target": 10},
        "2026-07-21": {"completed": False, "fulfilled": False, "current": 8, "target": 10},
        "2026-07-22": {"completed": False, "fulfilled": False, "current": 0, "target": 10},
    }
    context = AssistantContext(
        user_id="alice",
        current_user={},
        state=AssistantState(),
        session_state={},
        current_page_key="help",
        now=datetime(2026, 7, 27, tzinfo=timezone.utc),
        user_state={
            "goals": [
                {
                    "description": "Walking",
                    "participants": {"alice": {"period_outcomes": outcomes}},
                }
            ]
        },
    )

    result = _analyse(context, datetime(2026, 7, 20, tzinfo=timezone.utc).date(), False)

    assert result.perfect_days == 1
    assert result.active_days == 2


def test_week_comparison_keeps_goals_that_were_only_active_last_week() -> None:
    context = AssistantContext(
        user_id="alice",
        current_user={},
        state=AssistantState(),
        session_state={},
        current_page_key="help",
        now=datetime(2026, 7, 27, tzinfo=timezone.utc),
        user_state={
            "goals": [
                {
                    "description": "Previous goal",
                    "participants": {
                        "alice": {
                            "period_outcomes": {
                                "2026-07-13": {"completed": True, "fulfilled": True},
                                "2026-07-14": {"completed": False, "fulfilled": False},
                            }
                        }
                    },
                },
                {
                    "description": "Current goal",
                    "participants": {
                        "alice": {
                            "period_outcomes": {
                                "2026-07-20": {"completed": True, "fulfilled": True},
                            }
                        }
                    },
                },
            ]
        },
    )

    result = _analyse(context, datetime(2026, 7, 20, tzinfo=timezone.utc).date(), False)

    assert result.previous_active == 2
    assert result.previous_rate == 50


def test_weekly_period_is_not_mislabelled_as_monday_activity() -> None:
    context = AssistantContext(
        user_id="alice",
        current_user={},
        state=AssistantState(),
        session_state={},
        current_page_key="help",
        now=datetime(2026, 7, 27, tzinfo=timezone.utc),
        user_state={
            "goals": [
                {
                    "description": "Weekly planning",
                    "schedule_class": "weekly",
                    "participants": {
                        "alice": {
                            "period_outcomes": {
                                "2026-07-20": {"completed": True, "fulfilled": True},
                            }
                        }
                    },
                }
            ]
        },
    )

    result = _analyse(context, datetime(2026, 7, 20, tzinfo=timezone.utc).date(), False)

    assert result.fulfilled == 1
    assert all(active == 0 for _, active, _ in result.daily)
