from __future__ import annotations

from src.assistant.events import (
    BUTTON_TEST_ACTIVE,
    HELP_STORY_STATE_KEY,
    event_for_help_visit,
)


def test_first_help_visit_plays_welcome_then_return_plays_button_test() -> None:
    state: dict[str, object] = {}

    assert event_for_help_visit(state, previous_page_key="goals") == "welcome"
    state[HELP_STORY_STATE_KEY] = "welcome_completed"

    assert event_for_help_visit(state, previous_page_key="friends") == "button_test"
    assert state[HELP_STORY_STATE_KEY] == BUTTON_TEST_ACTIVE


def test_refresh_starts_a_new_session_with_the_welcome_event() -> None:
    assert event_for_help_visit({}, previous_page_key=None) == "welcome"
