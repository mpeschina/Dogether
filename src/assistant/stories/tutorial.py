from __future__ import annotations

from typing import Final

from src.assistant.core import AssistantContext, AssistantEvent, AssistantView, EventOutcome
from src.assistant.state import AssistantCategory


TUTORIAL_SEQUENCE_ID: Final = "initial_tutorial"
APP_INTRO_SEEN_KEY: Final = "tutorial.app_intro.seen"


class AppIntroductionEvent:
    event_id = "tutorial.app_intro"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        view.say("Welcome to Dogether!")
        view.say(
            "Dogether helps you create goals, track your progress, "
            "and reach them together with friends."
        )
        view.say(
            "Use Goals to update progress, Friends to connect, "
            "and Manage Goals to create or change goals."
        )
        view.say("I'll be here on the Help page whenever you need guidance.")
        return EventOutcome.complete(
            advance_sequence=TUTORIAL_SEQUENCE_ID,
            knowledge_updates={APP_INTRO_SEEN_KEY: True},
        )


class AssistantReadyEvent:
    event_id = "standard.ready"
    category = AssistantCategory.STANDARD

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        view.status("Assistant ready — come back whenever you need help.")
        return EventOutcome()


class InitialTutorialStory:
    story_id = "initial_tutorial"

    def __init__(self) -> None:
        self._introduction = AppIntroductionEvent()
        self._ready = AssistantReadyEvent()

    def next_event(self, context: AssistantContext) -> AssistantEvent:
        tutorial_complete = (
            context.state.sequences.get(TUTORIAL_SEQUENCE_ID, 0) >= 1
            or context.state.knowledge.get(APP_INTRO_SEEN_KEY, False)
        )
        return self._ready if tutorial_complete else self._introduction
