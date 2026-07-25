from __future__ import annotations

import time
from collections.abc import MutableMapping
from typing import Final

import streamlit as st

from src.assistant.streaming import response_generator


HELP_STORY_STATE_KEY: Final = "help_assistant_story_state"
HELP_PAGE_KEY: Final = "help"

WELCOME_PENDING: Final = "welcome_pending"
WELCOME_COMPLETED: Final = "welcome_completed"
BUTTON_TEST_ACTIVE: Final = "button_test_active"
BUTTON_TEST_COMPLETED: Final = "button_test_completed"
THIRD_EVENT_ACTIVE: Final = "third_event_active"
THIRD_EVENT_COMPLETED: Final = "third_event_completed"
THIRD_EVENT_CLICKS_KEY: Final = "help_assistant_third_event_clicks"

STATUS_CLICK_COUNT: Final = 10
PROGRESS_BAR_CLICK_COUNT: Final = 40
PROGRESS_BAR_COUNT: Final = 3


def event_for_help_visit(
    session_state: MutableMapping[str, object], *, previous_page_key: str | None
) -> str | None:
    """Choose the next session-only Help event."""

    state = session_state.get(HELP_STORY_STATE_KEY)
    if state is None:
        session_state[HELP_STORY_STATE_KEY] = WELCOME_PENDING
        return "welcome"
    if state == WELCOME_PENDING:
        return "welcome"
    if state == WELCOME_COMPLETED and previous_page_key != HELP_PAGE_KEY:
        session_state[HELP_STORY_STATE_KEY] = BUTTON_TEST_ACTIVE
        return "button_test"
    if state == BUTTON_TEST_ACTIVE:
        return "button_test"
    if state == BUTTON_TEST_COMPLETED and previous_page_key != HELP_PAGE_KEY:
        session_state[HELP_STORY_STATE_KEY] = THIRD_EVENT_ACTIVE
        return "third_event"
    if state == THIRD_EVENT_ACTIVE:
        return "third_event"
    return None


def welcome_event() -> None:
    """Render the initial welcome scene in the order it should be experienced."""

    say("Hey, welcome to our app!")
    wait(1)
    typing_indicator(4)
    wait(2)
    typing_indicator(3)
    say("Ok, I just let you time to arrive and organize yourself.")
    wait(2)
    assistant_leave()


def complete_welcome_event(session_state: MutableMapping[str, object]) -> None:
    if session_state.get(HELP_STORY_STATE_KEY) == WELCOME_PENDING:
        session_state[HELP_STORY_STATE_KEY] = WELCOME_COMPLETED


def button_test_event(session_state: MutableMapping[str, object]) -> None:
    """Render the return-visit button test and finish it after one choice."""

    say("Would you like to help us test the buttons? Pick a number below.")
    selected_choice = choices("Choose a number", "1", "2", "3")
    if selected_choice is None:
        return

    session_state[HELP_STORY_STATE_KEY] = BUTTON_TEST_COMPLETED
    say(f"Thanks — you selected {selected_choice}.")
    assistant_leave()


def third_event(session_state: MutableMapping[str, object]) -> None:
    """Run the empty-input click challenge shown after the button test."""

    if _send_control_clicked():
        session_state[THIRD_EVENT_CLICKS_KEY] = int(session_state.get(THIRD_EVENT_CLICKS_KEY, 0)) + 1

    clicks = int(session_state.get(THIRD_EVENT_CLICKS_KEY, 0))
    if clicks <= STATUS_CLICK_COUNT:
        if clicks:
            st.markdown(f"<div class='assistant-status'>{clicks}x</div>", unsafe_allow_html=True)
        return

    progress_clicks = clicks - STATUS_CLICK_COUNT
    _render_progress_bars(progress_clicks)
    if progress_clicks < PROGRESS_BAR_CLICK_COUNT * PROGRESS_BAR_COUNT:
        return

    session_state[HELP_STORY_STATE_KEY] = THIRD_EVENT_COMPLETED
    say("Come on.")
    typing_indicator(4)
    say("I AM NOT HERE!")
    assistant_leave()


def say(message: str) -> None:
    with st.chat_message("assistant", avatar="✨"):
        st.write_stream(response_generator(message))


def typing_indicator(duration_seconds: float) -> None:
    placeholder = st.empty()
    placeholder.markdown(
        "<div class='assistant-typing' aria-label='Assistant is typing'>"
        "<span></span><span></span><span></span></div>",
        unsafe_allow_html=True,
    )
    time.sleep(duration_seconds)
    placeholder.empty()


def wait(duration_seconds: float) -> None:
    """Pause a story flow without rendering another chat element."""

    if duration_seconds < 0:
        raise ValueError("Wait duration must not be negative.")
    time.sleep(duration_seconds)


def assistant_leave() -> None:
    st.markdown("<div class='assistant-status'>Assistant left the chat</div>", unsafe_allow_html=True)


def choices(label: str, *options: str) -> str | None:
    st.markdown(f"<div class='assistant-choice-label'>{label}</div>", unsafe_allow_html=True)
    columns = st.columns(len(options))
    for column, option in zip(columns, options):
        if column.button(option, key=f"help_assistant_choice_{option}", use_container_width=True):
            return option
    return None


def _send_control_clicked() -> bool:
    """Render an enabled, text-optional Send control for the third event."""

    with st.form("help_assistant_third_event_form", clear_on_submit=True):
        st.text_input("Message the assistant", label_visibility="collapsed", placeholder="Message the assistant")
        return st.form_submit_button("Send", use_container_width=True)


def _render_progress_bars(progress_clicks: int) -> None:
    bar_count = min(
        PROGRESS_BAR_COUNT,
        (progress_clicks + PROGRESS_BAR_CLICK_COUNT - 1) // PROGRESS_BAR_CLICK_COUNT,
    )
    for index in range(bar_count):
        bar_clicks = min(
            PROGRESS_BAR_CLICK_COUNT,
            max(0, progress_clicks - index * PROGRESS_BAR_CLICK_COUNT),
        )
        st.progress(bar_clicks / PROGRESS_BAR_CLICK_COUNT, text=f"{bar_clicks} / {PROGRESS_BAR_CLICK_COUNT}")
