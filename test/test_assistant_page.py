from src.assistant.state import AssistantState
from src.assistant.stories.tutorial import TUTORIAL_STORY_ID
from src.pages.assistant_page import _show_disabled_chat_interface


def test_disabled_chat_interface_is_hidden_for_regular_stories_with_stars() -> None:
    state = AssistantState(stars=1, story="standard", scene="ready", status="completed")

    assert not _show_disabled_chat_interface(state)


def test_disabled_chat_interface_is_shown_for_accounts_without_stars() -> None:
    state = AssistantState(stars=0, story="standard", scene="ready", status="completed")

    assert _show_disabled_chat_interface(state)


def test_disabled_chat_interface_is_shown_for_initial_tutorial_story() -> None:
    state = AssistantState(stars=3, story=TUTORIAL_STORY_ID, status="active")

    assert _show_disabled_chat_interface(state)


def test_disabled_chat_interface_is_hidden_for_other_tutorial_stories_with_stars() -> None:
    state = AssistantState(
        stars=3,
        story="personal_highlight_tutorial",
        status="active",
    )

    assert not _show_disabled_chat_interface(state)
