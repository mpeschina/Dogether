from datetime import datetime, timezone

from src.assistant.core import AssistantContext, AssistantSelection
from src.assistant.state import AssistantState, WEEKLY_STAR_EVENT_ID
from src.assistant.stories.star_tutorial import (
    STAR_TUTORIAL_CHECK_SCENE,
    STAR_TUTORIAL_FINISH_SCENE,
    STAR_TUTORIAL_INTRO_SCENE,
    star_tutorial_turn,
)
from src.assistant.stories.standard import STANDARD_HELP_SCENE, standard_help_turn
from src.assistant.stories.weekly_summary import (
    STAR_AWARD_SCENE,
    WEEKLY_STAR_REWARD_UNLOCKED_KNOWLEDGE_KEY,
    WEEKLY_SUMMARY_STORY_ID,
    WeeklySummaryStory,
)


def _context(state: AssistantState | None = None) -> AssistantContext:
    return AssistantContext(
        user_id="alice",
        current_user={},
        state=state or AssistantState(),
        session_state={},
        current_page_key="assistant",
        now=datetime(2026, 7, 27, tzinfo=timezone.utc),
        user_state={"goals": []},
    )


def test_star_tutorial_uses_the_supplied_dialogue_and_returns_to_its_caller() -> None:
    context = _context()
    intro = star_tutorial_turn(context, "owner", STAR_TUTORIAL_INTRO_SCENE, None, return_scene="return")
    assert [line.text for line in intro.lines] == [
        "Sure, I can explain you the STARs",
        "The STARS are not just decoration",
        "They are a measurement",
    ]
    assert [choice.label for choice in intro.choices] == ["(ok, and measurement of what)"]

    check = star_tutorial_turn(
        context, "owner", STAR_TUTORIAL_INTRO_SCENE,
        AssistantSelection("owner", STAR_TUTORIAL_INTRO_SCENE, "measurement", ""),
        return_scene="return",
    )
    assert check.state_scene == STAR_TUTORIAL_CHECK_SCENE

    waiting = star_tutorial_turn(context, "owner", STAR_TUTORIAL_CHECK_SCENE, None, return_scene="return")
    assert waiting.lines[-1].text == ""
    assert waiting.lines[-1].typing_delay == 5

    finish = star_tutorial_turn(
        context, "owner", STAR_TUTORIAL_CHECK_SCENE,
        AssistantSelection("owner", STAR_TUTORIAL_CHECK_SCENE, "faster", ""),
        return_scene="return",
    )
    assert finish.state_scene == STAR_TUTORIAL_FINISH_SCENE
    complete = star_tutorial_turn(
        context, "owner", STAR_TUTORIAL_FINISH_SCENE,
        AssistantSelection("owner", STAR_TUTORIAL_FINISH_SCENE, "thanks", ""),
        return_scene="return",
    )
    assert complete.state_scene == "return"
    assert complete.continue_flow


def test_help_only_offers_star_explanation_after_a_weekly_reward() -> None:
    locked = standard_help_turn(profile_analysis_completed=False)
    unlocked = standard_help_turn(
        profile_analysis_completed=False, stars_explanation_unlocked=True
    )
    assert "stars" not in [choice.id for choice in locked.choices]
    assert "stars" in [choice.id for choice in unlocked.choices]


def test_weekly_star_explanation_acknowledges_the_reward_before_entering_tutorial() -> None:
    state = AssistantState(
        story=WEEKLY_SUMMARY_STORY_ID,
        scene=STAR_AWARD_SCENE,
        status="active",
        events={
            "weekly_summary.selection": {"start": "2026-07-20", "partial": False},
            WEEKLY_STAR_EVENT_ID: {"evaluated_week": "2026-07-20", "awarded": True},
        },
        knowledge={WEEKLY_STAR_REWARD_UNLOCKED_KNOWLEDGE_KEY: True},
    )
    turn = WeeklySummaryStory().advance(
        _context(state),
        STAR_AWARD_SCENE,
        AssistantSelection(WEEKLY_SUMMARY_STORY_ID, STAR_AWARD_SCENE, "explain_stars", "What are STARs?"),
    )
    assert turn.state_scene == STAR_TUTORIAL_INTRO_SCENE
    assert turn.event_updates[WEEKLY_STAR_EVENT_ID]["acknowledged"] is True
