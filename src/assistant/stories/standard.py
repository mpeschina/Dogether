"""The default, user-directed assistant experience."""
from __future__ import annotations

from typing import Final

from src.assistant.core import AssistantContext, AssistantEvent, AssistantView, EventOutcome
from src.assistant.state import AssistantCategory


STANDARD_STORY_ID: Final = "standard"
STANDARD_MENU_EVENT_ID: Final = "standard.tutorial_menu"
STANDARD_PUSH_FLOW: Final = "standard.push_reminder"
STANDARD_PUSH_NODE: Final = "push.offer_enable"
PUSH_PROMPT_EVENT_ID: Final = "standard.push_prompt"

TUTORIAL_OPTIONS: Final = (
    ("How do I add friends?", "tutorial.friends.seen"),
    ("How do I create a goal?", "tutorial.goals.seen"),
    ("How do notifications work?", "tutorial.notifications.seen"),
    ("How do I track progress?", "tutorial.progress.seen"),
)


class StandardMenuEvent(AssistantEvent):
    """A deliberately small fallback; it does not decide when to interrupt."""

    event_id = STANDARD_MENU_EVENT_ID
    category = AssistantCategory.STANDARD

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        options = tuple(label for label, _ in TUTORIAL_OPTIONS)
        choice = view.selected_choice(self.event_id, *options)
        if choice is None:
            view.say("Hello")
            choice = view.choices(self.event_id, "Tutorials", *options)
        if choice is None:
            return EventOutcome()

        _, knowledge_key = next(item for item in TUTORIAL_OPTIONS if item[0] == choice)
        view.say("That tutorial is coming soon.")
        return EventOutcome.pending(knowledge_updates={knowledge_key: True})


class StandardStory:
    """Owns only the standard fallback screen."""

    story_id = STANDARD_STORY_ID

    def __init__(self) -> None:
        self._menu = StandardMenuEvent()

    def next_event(self, context: AssistantContext) -> AssistantEvent:
        return self._menu
