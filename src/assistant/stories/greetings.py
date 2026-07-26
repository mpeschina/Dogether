"""Session-scoped greetings composed from small, independent render functions."""
from __future__ import annotations

import random
from datetime import date, datetime
from typing import Any, Callable, Final

from src.assistant.core import AssistantContext, AssistantEvent, AssistantView, EventOutcome
from src.assistant.state import AssistantCategory


GREETINGS_STORY_ID: Final = "greetings"
GREETING_INTERACTION_EVENT_ID: Final = "greetings.interaction"
GREETING_DATE_SESSION_KEY: Final = "greetings.date"
GREETING_SELECTION_SESSION_KEY: Final = "greetings.selection"
GREETING_PENDING_SESSION_KEY: Final = "greetings.pending"

NORMAL_GREETING_IDS: Final = ("hello", "date", "good_to_see_you", "goal_getter", "tiny_win")
INTERACTIVE_GREETING_IDS: Final = ("cowboy", "spark", "tiny_step")

GreetingRenderer = Callable[[AssistantContext, AssistantView, AssistantEvent], EventOutcome]


def render_default_greeting(context: AssistantContext, view: AssistantView, menu_event: AssistantEvent) -> EventOutcome:
    view.say("Hello")
    return menu_event.render(context, view)


def render_hello(context: AssistantContext, view: AssistantView, menu_event: AssistantEvent) -> EventOutcome:
    view.say("Hello my friend.")
    return menu_event.render(context, view)


def render_date_greeting(context: AssistantContext, view: AssistantView, menu_event: AssistantEvent) -> EventOutcome:
    today = _today(context)
    view.say(f"Hello, today is {today.strftime('%B')} {today.day}.")
    return menu_event.render(context, view)


def render_good_to_see_you(context: AssistantContext, view: AssistantView, menu_event: AssistantEvent) -> EventOutcome:
    view.say("Good to see you.")
    return menu_event.render(context, view)


def render_goal_getter(context: AssistantContext, view: AssistantView, menu_event: AssistantEvent) -> EventOutcome:
    view.say("Hello, goal getter.")
    return menu_event.render(context, view)


def render_tiny_win(context: AssistantContext, view: AssistantView, menu_event: AssistantEvent) -> EventOutcome:
    view.say("Ready for a tiny win?")
    return menu_event.render(context, view)


def render_cowboy(context: AssistantContext, view: AssistantView, menu_event: AssistantEvent) -> EventOutcome:
    choice = view.selected_choice(GREETING_INTERACTION_EVENT_ID, "Are you a Cowboy today?")
    if choice is None:
        view.say("Howdy my friend!")
        choice = view.choices(GREETING_INTERACTION_EVENT_ID, "", "Are you a Cowboy today?")
    if choice is None:
        return EventOutcome()

    context.session_state.pop(GREETING_PENDING_SESSION_KEY, None)
    view.say("I am just in a good mood. How can I help you?")
    return menu_event.render(context, view)


def render_spark(context: AssistantContext, view: AssistantView, menu_event: AssistantEvent) -> EventOutcome:
    choice = view.selected_choice(GREETING_INTERACTION_EVENT_ID, "Is today a good day?")
    if choice is None:
        view.say("I brought a little sparkle.")
        choice = view.choices(GREETING_INTERACTION_EVENT_ID, "", "Is today a good day?")
    if choice is None:
        return EventOutcome()

    context.session_state.pop(GREETING_PENDING_SESSION_KEY, None)
    view.say("Excellent. Let's make it count.")
    return menu_event.render(context, view)


def render_tiny_step(context: AssistantContext, view: AssistantView, menu_event: AssistantEvent) -> EventOutcome:
    choice = view.selected_choice(GREETING_INTERACTION_EVENT_ID, "Want to make one?")
    if choice is None:
        view.say("A tiny step still counts.")
        choice = view.choices(GREETING_INTERACTION_EVENT_ID, "", "Want to make one?")
    if choice is None:
        return EventOutcome()

    context.session_state.pop(GREETING_PENDING_SESSION_KEY, None)
    view.say("That is the spirit. I am cheering for you.")
    return menu_event.render(context, view)


GREETING_RENDERERS: Final[dict[str, GreetingRenderer]] = {
    "hello": render_hello,
    "date": render_date_greeting,
    "good_to_see_you": render_good_to_see_you,
    "goal_getter": render_goal_getter,
    "tiny_win": render_tiny_win,
    "cowboy": render_cowboy,
    "spark": render_spark,
    "tiny_step": render_tiny_step,
}

class GreetingEvent(AssistantEvent):
    """Small adapter that lets a selected function participate in the story engine."""

    category = AssistantCategory.STANDARD

    def __init__(self, greeting_id: str | None, menu_event: AssistantEvent) -> None:
        self.greeting_id = greeting_id
        self.menu_event = menu_event
        self.event_id = GREETING_INTERACTION_EVENT_ID if greeting_id in INTERACTIVE_GREETING_IDS else "greetings.message"

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        renderer = GREETING_RENDERERS.get(self.greeting_id or "", render_default_greeting)
        return renderer(context, view, self.menu_event)


class GreetingsStory:
    """Choose one greeting per session-day, then use a plain fallback."""

    story_id = GREETINGS_STORY_ID

    def __init__(self, menu_event: AssistantEvent, *, random_source: Any = random) -> None:
        self._menu_event = menu_event
        self._random_source = random_source

    def next_event(self, context: AssistantContext) -> AssistantEvent:
        today = _today(context)
        session_state = context.session_state
        if session_state.get(GREETING_DATE_SESSION_KEY) != today.isoformat():
            session_state[GREETING_DATE_SESSION_KEY] = today.isoformat()
            session_state.pop(GREETING_SELECTION_SESSION_KEY, None)
            session_state.pop(GREETING_PENDING_SESSION_KEY, None)
            greeting_id = self._choose_greeting_id()
            session_state[GREETING_SELECTION_SESSION_KEY] = greeting_id
            if greeting_id in INTERACTIVE_GREETING_IDS:
                session_state[GREETING_PENDING_SESSION_KEY] = greeting_id
            return GreetingEvent(greeting_id, self._menu_event)

        pending_id = session_state.get(GREETING_PENDING_SESSION_KEY)
        if isinstance(pending_id, str) and pending_id in INTERACTIVE_GREETING_IDS:
            return GreetingEvent(pending_id, self._menu_event)
        session_state.pop(GREETING_PENDING_SESSION_KEY, None)
        return GreetingEvent(None, self._menu_event)

    def _choose_greeting_id(self) -> str:
        greeting_ids = NORMAL_GREETING_IDS if self._random_source.random() < 0.8 else INTERACTIVE_GREETING_IDS
        return self._random_source.choice(greeting_ids)


def _today(context: AssistantContext) -> date:
    now = context.now or datetime.now()
    return now.date()
