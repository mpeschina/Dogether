from datetime import datetime, timezone

from src.assistant.core import AssistantContext, AssistantSelection
from src.assistant.state import AssistantState, WEEKLY_STAR_EVENT_ID
from src.assistant.stories.star_tutorial import (
    STAR_TUTORIAL_CHECK_SCENE,
    STAR_TUTORIAL_FINISH_SCENE,
    STAR_TUTORIAL_INTRO_SCENE,
    star_tutorial_turn,
)
from src.assistant.director import apply_turn
from src.assistant.stories.standard import (
    STANDARD_ADVANCED_SCENE,
    STANDARD_HELP_SCENE,
    StandardStory,
    standard_help_turn,
)
from src.assistant.stories.tutorial import PROFILE_ANALYSIS_KNOWLEDGE_KEY, STANDARD_STORY_ID
from src.assistant.stories.weekly_summary import (
    STAR_AWARD_SCENE,
    STAR_TUTORIAL_RETURN_SCENE,
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


def test_star_tutorial_progresses_and_returns_to_its_caller() -> None:
    context = _context()
    intro = star_tutorial_turn(context, "owner", STAR_TUTORIAL_INTRO_SCENE, None, return_scene="return")
    assert intro.choices[0].id == "measurement"

    check = star_tutorial_turn(
        context, "owner", STAR_TUTORIAL_INTRO_SCENE,
        AssistantSelection("owner", STAR_TUTORIAL_INTRO_SCENE, "measurement", ""),
        return_scene="return",
    )
    assert check.state_scene == STAR_TUTORIAL_CHECK_SCENE

    waiting = star_tutorial_turn(context, "owner", STAR_TUTORIAL_CHECK_SCENE, None, return_scene="return")
    assert waiting.lines[-1].text == ""

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


def test_help_does_not_offer_a_standalone_star_explanation() -> None:
    locked = standard_help_turn(profile_analysis_completed=False)
    unlocked = standard_help_turn(profile_analysis_completed=False, stars=1)
    assert "stars" not in [choice.id for choice in locked.choices]
    assert "stars" not in [choice.id for choice in unlocked.choices]


def test_advanced_tutorial_menu_requires_a_star() -> None:
    locked = standard_help_turn(profile_analysis_completed=True)
    unlocked = standard_help_turn(profile_analysis_completed=True, stars=1)

    assert "advanced" not in [choice.id for choice in locked.choices]
    assert [choice.label for choice in unlocked.choices][-1] == "Whats the advanced stuff here?"


def test_advanced_tutorial_menu_routes_choices_and_returns_from_star_tutorial() -> None:
    story = StandardStory()
    state = AssistantState(
        stars=1,
        story=STANDARD_STORY_ID,
        scene=STANDARD_HELP_SCENE,
        status="active",
        knowledge={PROFILE_ANALYSIS_KNOWLEDGE_KEY: True},
    )
    context = _context(state)

    submenu = story.advance(
        context,
        STANDARD_HELP_SCENE,
        AssistantSelection(STANDARD_STORY_ID, STANDARD_HELP_SCENE, "advanced", ""),
    )
    assert submenu.state_scene == STANDARD_ADVANCED_SCENE
    assert len(submenu.lines) == 1
    assert [choice.label for choice in submenu.choices] == [
        "Explain STARs to me", "*****", "", "I meant even more advanced!"
    ]

    unavailable = story.advance(
        context,
        STANDARD_ADVANCED_SCENE,
        AssistantSelection(STANDARD_STORY_ID, STANDARD_ADVANCED_SCENE, "advanced_unavailable_one", ""),
    )
    assert unavailable.lines[0].text == "Not available under current circumstances"
    assert unavailable.state_scene == STANDARD_ADVANCED_SCENE
    empty_choice = story.advance(
        context,
        STANDARD_ADVANCED_SCENE,
        AssistantSelection(STANDARD_STORY_ID, STANDARD_ADVANCED_SCENE, "advanced_unavailable_two", ""),
    )
    assert empty_choice.lines
    assert empty_choice.state_scene == STANDARD_ADVANCED_SCENE
    more = story.advance(
        context,
        STANDARD_ADVANCED_SCENE,
        AssistantSelection(STANDARD_STORY_ID, STANDARD_ADVANCED_SCENE, "advanced_more", ""),
    )
    assert more.lines[0].text == "Nothing to see here"
    assert more.state_scene == STANDARD_ADVANCED_SCENE

    start = story.advance(
        context,
        STANDARD_ADVANCED_SCENE,
        AssistantSelection(STANDARD_STORY_ID, STANDARD_ADVANCED_SCENE, "advanced_stars", ""),
    )
    star_state = apply_turn(state, start)
    complete = story.advance(
        _context(star_state),
        STAR_TUTORIAL_FINISH_SCENE,
        AssistantSelection(STANDARD_STORY_ID, STAR_TUTORIAL_FINISH_SCENE, "thanks", ""),
    )
    assert complete.state_scene == STANDARD_ADVANCED_SCENE
    assert complete.clear_events
    assert complete.lines[0].text == "Always at your service"
    assert complete.assistant_leaves is True
    assert complete.continue_flow is False


def test_weekly_star_explanation_returns_to_the_open_weekly_report() -> None:
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
    tutorial = WeeklySummaryStory().advance(
        _context(apply_turn(state, turn)),
        STAR_TUTORIAL_INTRO_SCENE,
        None,
    )

    assert turn.state_story == WEEKLY_SUMMARY_STORY_ID
    assert turn.state_scene == STAR_TUTORIAL_INTRO_SCENE
    assert turn.event_updates[WEEKLY_STAR_EVENT_ID]["acknowledged"] is True
    assert tutorial.choices[0].id == "measurement"

    completed_tutorial = star_tutorial_turn(
        _context(),
        WEEKLY_SUMMARY_STORY_ID,
        STAR_TUTORIAL_FINISH_SCENE,
        AssistantSelection(WEEKLY_SUMMARY_STORY_ID, STAR_TUTORIAL_FINISH_SCENE, "thanks", ""),
        return_scene=STAR_TUTORIAL_RETURN_SCENE,
    )
    assert completed_tutorial.state_scene == STAR_TUTORIAL_RETURN_SCENE

    return_state = apply_turn(apply_turn(state, turn), completed_tutorial)
    return_context = _context(return_state)
    return_context.user_state["goals"] = [
        {
            "description": "Walking",
            "participants": {
                "alice": {
                    "period_outcomes": {
                        f"2026-07-{day:02d}": {"fulfilled": True, "skipped": False}
                        for day in range(20, 27)
                    }
                }
            },
        }
    ]
    returned_report = WeeklySummaryStory().advance(return_context, None, None)
    continued_state = apply_turn(return_state, returned_report)

    assert returned_report.scene_id == "weekly.summary"
    assert continued_state.story == WEEKLY_SUMMARY_STORY_ID
    assert continued_state.status == "active"
