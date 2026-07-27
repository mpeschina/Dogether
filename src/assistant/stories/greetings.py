"""Session-scoped greetings expressed as declarative conversation turns."""
from __future__ import annotations

import random
from datetime import date, datetime
from typing import Any, Final

from src.assistant.core import (
    AssistantChoice,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
)


GREETINGS_STORY_ID: Final = "greetings"
GREETING_INTERACTION_EVENT_ID: Final = "greetings.interaction"
GREETING_DATE_SESSION_KEY: Final = "greetings.date"
GREETING_SELECTION_SESSION_KEY: Final = "greetings.selection"
GREETING_PENDING_SESSION_KEY: Final = "greetings.pending"

NORMAL_GREETING_IDS: Final = ("hello", "date", "good_to_see_you", "goal_getter", "tiny_win")
INTERACTIVE_GREETING_IDS: Final = ("cowboy", "spark", "tiny_step")

NORMAL_MESSAGES: Final = {
    "hello": "Hello my friend.",
    "good_to_see_you": "Good to see you.",
    "goal_getter": "Hello, goal getter.",
    "tiny_win": "Ready for a tiny win?",
}
INTERACTIVE_MESSAGES: Final = {
    "cowboy": ("Howdy my friend!", "Are you a Cowboy today?", "I am just in a good mood. How can I help you?"),
    "spark": ("I brought a little sparkle.", "Is today a good day?", "Excellent. Let's make it count."),
    "tiny_step": ("A tiny step still counts.", "Want to make one?", "That is the spirit. I am cheering for you."),
}


class GreetingsStory(AssistantStory):
    story_id = GREETINGS_STORY_ID

    def __init__(self, _menu_story: object | None = None, *, random_source: Any = random) -> None:
        self._random_source = random_source

    def entry_scene(self, context: AssistantContext) -> str:
        today = _today(context).isoformat()
        session = context.session_state
        if session.get(GREETING_DATE_SESSION_KEY) != today:
            session[GREETING_DATE_SESSION_KEY] = today
            session.pop(GREETING_SELECTION_SESSION_KEY, None)
            session.pop(GREETING_PENDING_SESSION_KEY, None)
            greeting_id = self._choose_greeting_id()
            session[GREETING_SELECTION_SESSION_KEY] = greeting_id
            if greeting_id in INTERACTIVE_GREETING_IDS:
                session[GREETING_PENDING_SESSION_KEY] = greeting_id
            return greeting_id

        pending = session.get(GREETING_PENDING_SESSION_KEY)
        if isinstance(pending, str) and pending in INTERACTIVE_GREETING_IDS:
            return pending
        return "default"

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        greeting_id = scene_id or self.entry_scene(context)
        if greeting_id in INTERACTIVE_GREETING_IDS:
            intro, choice_label, response = INTERACTIVE_MESSAGES[greeting_id]
            if selection is None:
                return AssistantTurn(
                    story_id=self.story_id,
                    scene_id=greeting_id,
                    lines=(AssistantLine(intro),),
                    choices=(AssistantChoice(id="continue", label=choice_label),),
                )
            context.session_state.pop(GREETING_PENDING_SESSION_KEY, None)
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=greeting_id,
                lines=(AssistantLine(response),),
                continue_flow=True,
            )

        if greeting_id == "date":
            today = _today(context)
            message = f"Hello, today is {today.strftime('%B')} {today.day}."
        elif greeting_id == "default":
            message = "Hello"
        else:
            message = NORMAL_MESSAGES.get(greeting_id, "Hello")
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=greeting_id,
            lines=(AssistantLine(message),),
            continue_flow=True,
        )

    def _choose_greeting_id(self) -> str:
        choices = NORMAL_GREETING_IDS if self._random_source.random() < 0.8 else INTERACTIVE_GREETING_IDS
        return self._random_source.choice(choices)


def _today(context: AssistantContext) -> date:
    now = context.now or datetime.now()
    return now.date()
