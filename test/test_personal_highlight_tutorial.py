from datetime import datetime, timezone

from src.assistant.core import AssistantContext, AssistantSelection
from src.assistant.director import AssistantDirector, apply_turn
from src.assistant.state import AssistantState
from src.assistant.stories import default_stories
from src.assistant.stories.personal_highlight_tutorial import (
    FIRST_WEEKLY_SUMMARY_VIEWED_ON_KEY,
    PERSONAL_HIGHLIGHT_TUTORIAL_EVENT_ID,
    PERSONAL_HIGHLIGHT_TUTORIAL_SCENE,
    PERSONAL_HIGHLIGHT_TUTORIAL_STORY_ID,
    PersonalHighlightTutorialStory,
    personal_highlight_tutorial_pending,
    personal_highlight_tutorial_toast_key,
    personal_highlights_unlocked,
    record_first_weekly_summary_view,
)
import src.assistant.stories.personal_highlight_tutorial as personal_highlight_tutorial
from src.assistant.stories.tutorial import READY_NODE, STANDARD_STORY_ID
from src.pages.account_page import personal_highlights_visible


def _now(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _context(state: AssistantState, now: datetime) -> AssistantContext:
    return AssistantContext(
        user_id="alice",
        current_user={},
        state=state,
        session_state={},
        current_page_key="assistant",
        now=now,
    )


def test_first_weekly_summary_view_is_recorded_once() -> None:
    first = record_first_weekly_summary_view(AssistantState(), _now("2026-08-03T10:00:00"))
    state = AssistantState(events=first)

    assert first[PERSONAL_HIGHLIGHT_TUTORIAL_EVENT_ID][FIRST_WEEKLY_SUMMARY_VIEWED_ON_KEY] == "2026-08-03"
    assert record_first_weekly_summary_view(state, _now("2026-08-08T10:00:00")) == {}


def test_personal_highlight_unlock_waits_until_the_second_later_calendar_date() -> None:
    state = AssistantState(events={PERSONAL_HIGHLIGHT_TUTORIAL_EVENT_ID: {FIRST_WEEKLY_SUMMARY_VIEWED_ON_KEY: "2026-08-03"}})

    assert not personal_highlight_tutorial_pending(state, _now("2026-08-04T21:59:00"))
    assert personal_highlight_tutorial_pending(state, _now("2026-08-04T22:00:00"))
    assert personal_highlight_tutorial_toast_key("alice", state, _now("2026-08-04T22:00:00"))


def test_debug_override_requires_a_debug_profile_and_still_respects_the_one_time_unlock(monkeypatch) -> None:
    monkeypatch.setattr(personal_highlight_tutorial, "DEBUG_PERSONAL_HIGHLIGHT_TUTORIAL_ALWAYS_ELIGIBLE", True)
    state = AssistantState()

    assert not personal_highlight_tutorial_pending(state, _now("2026-08-01T10:00:00"), {"debug_info": False})
    assert personal_highlight_tutorial_pending(state, _now("2026-08-01T10:00:00"), {"debug_info": True})
    unlocked = AssistantState(events={PERSONAL_HIGHLIGHT_TUTORIAL_EVENT_ID: {"tutorial_started_at": "2026-08-01T10:00:00+00:00"}})
    assert not personal_highlight_tutorial_pending(unlocked, _now("2026-08-01T10:00:00"), {"debug_info": True})


def test_tutorial_start_unlocks_highlights_before_a_button_is_selected() -> None:
    state = AssistantState(events={PERSONAL_HIGHLIGHT_TUTORIAL_EVENT_ID: {FIRST_WEEKLY_SUMMARY_VIEWED_ON_KEY: "2026-08-03"}})
    context = _context(state, _now("2026-08-05T10:00:00"))
    story = PersonalHighlightTutorialStory()

    opening = story.advance(context, None, None)
    assert opening is not None
    assert [choice.id for choice in opening.choices] == ["open_account", "exit"]
    unlocked_state = apply_turn(state, opening)
    assert personal_highlights_unlocked(unlocked_state)
    assert personal_highlights_visible({"assistant_state": unlocked_state.to_dict()})
    assert personal_highlight_tutorial_toast_key("alice", unlocked_state, context.now) is None


def test_tutorial_buttons_open_account_or_exit() -> None:
    story = PersonalHighlightTutorialStory()
    context = _context(AssistantState(), _now("2026-08-05T10:00:00"))

    account = story.advance(context, PERSONAL_HIGHLIGHT_TUTORIAL_SCENE, AssistantSelection(PERSONAL_HIGHLIGHT_TUTORIAL_STORY_ID, PERSONAL_HIGHLIGHT_TUTORIAL_SCENE, "open_account", ""))
    exit_turn = story.advance(context, PERSONAL_HIGHLIGHT_TUTORIAL_SCENE, AssistantSelection(PERSONAL_HIGHLIGHT_TUTORIAL_STORY_ID, PERSONAL_HIGHLIGHT_TUTORIAL_SCENE, "exit", ""))

    assert account is not None and account.destination == "account"
    assert exit_turn is not None and exit_turn.assistant_leaves
    assert account.state_story == exit_turn.state_story == STANDARD_STORY_ID
    assert account.state_scene == exit_turn.state_scene == READY_NODE


def test_director_selects_the_pending_personal_highlight_tutorial() -> None:
    state = AssistantState(
        story=STANDARD_STORY_ID,
        scene=READY_NODE,
        status="completed",
        events={PERSONAL_HIGHLIGHT_TUTORIAL_EVENT_ID: {FIRST_WEEKLY_SUMMARY_VIEWED_ON_KEY: "2026-08-03"}},
    )
    director = AssistantDirector(object(), default_stories())

    story = director.story_dispatch(_context(state, _now("2026-08-05T10:00:00")), None)

    assert story is not None and story.story_id == PERSONAL_HIGHLIGHT_TUTORIAL_STORY_ID
