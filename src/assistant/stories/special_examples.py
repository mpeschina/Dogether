from __future__ import annotations

from typing import Final

from src.assistant.core import AssistantContext, AssistantEvent, AssistantView, EventOutcome
from src.assistant.state import AssistantCategory


SPECIAL_SEQUENCE_ID: Final = "special_examples"
HELP_PAGE_KEY: Final = "help"
BUTTON_TEST_EVENT_ID: Final = "special.button_test"
CLICK_CHALLENGE_EVENT_ID: Final = "special.click_challenge"

STATUS_CLICK_COUNT: Final = 10
PROGRESS_BAR_CLICK_COUNT: Final = 40
PROGRESS_BAR_COUNT: Final = 3


class WelcomeExampleEvent(AssistantEvent):
    event_id = "special.welcome"
    category = AssistantCategory.JOKE

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        view.say("Hey, welcome to our app!")
        view.wait(1)
        view.typing_indicator(4)
        view.wait(2)
        view.typing_indicator(3)
        view.say("Ok, I just let you time to arrive and organize yourself.")
        view.wait(1)
        view.assistant_leave()
        return EventOutcome.complete(advance_sequence=SPECIAL_SEQUENCE_ID)


class ButtonTestExampleEvent(AssistantEvent):
    event_id = BUTTON_TEST_EVENT_ID
    category = AssistantCategory.JOKE

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        view.say("Would you like to help us test the buttons? Pick a number below.")
        selected_choice = view.choices(self.event_id, "Choose a number", "1", "2", "3")
        if selected_choice is None:
            return EventOutcome.pending(event_updates={self.event_id: {"active": True}})

        view.say(f"Thanks — you selected {selected_choice}.")
        view.assistant_leave()
        return EventOutcome.complete(
            advance_sequence=SPECIAL_SEQUENCE_ID,
            clear_events=(self.event_id,),
        )


class ClickChallengeExampleEvent(AssistantEvent):
    event_id = CLICK_CHALLENGE_EVENT_ID
    category = AssistantCategory.JOKE

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        stored_event = context.state.events.get(self.event_id, {})
        clicks = _non_negative_int(stored_event.get("clicks", 0))
        if view.send_control(self.event_id):
            clicks += 1

        if clicks <= STATUS_CLICK_COUNT:
            if clicks:
                view.status(f"{clicks}x")
            return EventOutcome.pending(
                event_updates={self.event_id: {"active": True, "clicks": clicks}}
            )

        progress_clicks = clicks - STATUS_CLICK_COUNT
        _render_progress_bars(view, progress_clicks)
        if progress_clicks < PROGRESS_BAR_CLICK_COUNT * PROGRESS_BAR_COUNT:
            return EventOutcome.pending(
                event_updates={self.event_id: {"active": True, "clicks": clicks}}
            )

        view.say("Come on.")
        view.typing_indicator(4)
        view.say("I AM NOT HERE!")
        view.assistant_leave()
        return EventOutcome.complete(
            advance_sequence=SPECIAL_SEQUENCE_ID,
            clear_events=(self.event_id,),
        )


class SpecialExampleStory:
    story_id = "special_examples"

    def __init__(self) -> None:
        self._events: tuple[AssistantEvent, ...] = (
            WelcomeExampleEvent(),
            ButtonTestExampleEvent(),
            ClickChallengeExampleEvent(),
        )

    def next_event(self, context: AssistantContext) -> AssistantEvent | None:
        position = context.state.sequences.get(SPECIAL_SEQUENCE_ID, 0)
        if position < 0 or position >= len(self._events):
            return None

        event = self._events[position]
        if position == 0:
            return event

        event_state = context.state.events.get(event.event_id, {})
        if context.previous_page_key != HELP_PAGE_KEY or event_state.get("active") is True:
            return event
        return None


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _render_progress_bars(view: AssistantView, progress_clicks: int) -> None:
    bar_count = min(
        PROGRESS_BAR_COUNT,
        (progress_clicks + PROGRESS_BAR_CLICK_COUNT - 1) // PROGRESS_BAR_CLICK_COUNT,
    )
    for index in range(bar_count):
        bar_clicks = min(
            PROGRESS_BAR_CLICK_COUNT,
            max(0, progress_clicks - index * PROGRESS_BAR_CLICK_COUNT),
        )
        view.progress(
            bar_clicks / PROGRESS_BAR_CLICK_COUNT,
            text=f"{bar_clicks} / {PROGRESS_BAR_CLICK_COUNT}",
        )
