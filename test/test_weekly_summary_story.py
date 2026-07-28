from datetime import datetime, timezone

from src.assistant.core import AssistantCard, AssistantContext, AssistantLine, AssistantSelection
from src.assistant.state import AssistantState
from src.assistant.stories.weekly_summary import (
    SELECT_SCENE,
    SUMMARY_SCENE,
    WEEKLY_SUMMARY_STORY_ID,
    WeeklySummaryStory,
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
    assert turn.content[4].text.startswith("**")
    assert "\n" in turn.content[-1].text
    assert len(turn.lines) <= 12
