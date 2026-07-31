"""A lightweight, menu-only Smalltalk placeholder."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Final

from src.assistant.core import (
    AssistantChoice,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
)
from src.assistant.stories.tutorial import STANDARD_STORY_ID


SMALLTALK_STORY_ID: Final = "smalltalk"
SMALLTALK_MENU_CHOICE_ID: Final = "smalltalk"
SMALLTALK_PLACEHOLDER_SCENE: Final = "smalltalk.unavailable"
STANDARD_MENU_SCENE: Final = "standard.menu"
SMALLTALK_OPENER_SESSION_KEY: Final = "smalltalk.opener"
SMALLTALK_OPENER_SELECTED_AT_SESSION_KEY: Final = "smalltalk.opener_selected_at"
SMALLTALK_OPENER_INTERVAL: Final = timedelta(hours=3)
SMALLTALK_CLICKED_AT_SESSION_KEY: Final = "smalltalk.clicked_at"
SMALLTALK_COOLDOWN: Final = timedelta(hours=1)

SMALLTALK_OPENERS: Final = (
    # Standard
    "How’s your day going?",
    "How is the weather?",
    "Can I ask you something?",
    "Long time no see!",
    "What’s the good word?",
    "How are the vibes?",
    "How’s life today?",
    "What’s happening?",
    "What’s new?",
    "What’s the mood?",
    "What’s the story?",
    "What’s the mission?",

    # Funny
    "Any exciting snacks today?",
    "How’s being human?",
    "What are we pretending today?",
    "Did coffee do its job?",
    "Want a pointless question?",
    "Thriving or improvising?",
    "Are we winning yet?",
    "What broke first today?",
    "How chaotic is today?",
    "What’s today’s side quest?",
    "Procrastinating heroically?",
    "What are we overthinking?",
    "Did reality behave today?",
    "Productive or pretending?",
    "What’s today’s excuse?",
    "Is your brain cooperating?",
    "What deserves a big sigh?",
    "Could that meeting be a nap?",
    "What’s today’s disaster?",
    "Busy or just clicking?",
    "What are you avoiding?",
    "Feeling legendary yet?",
    "What’s today’s nonsense?",
    "Did today earn respect?",
    "Did today pass the vibe check?",
    "How’s the last brain cell?",

    # Serious
    "What’s on your mind?",
    "How are you, honestly?",
    "What matters most today?",
    "What do you need today?",
    "What’s been difficult?",
    "What are you working through?",
    "What needs your attention?",
    "What gives you energy?",
    "What drains your energy?",
    "What are you proud of?",
    "What would help today?",
    "What are you awaiting?",
    "What feels unfinished?",
    "What do you need to hear?",
    "What are you learning?",
    "What should you release?",
    "What deserves more credit?",
    "What feels good lately?",
    "What should you protect?",
    "What would make today count?",

    # Surprising
    "Anything weird happen today?",
    "How’s your corner of space?",
    "What’s today’s plot twist?",
    "Seen any good clouds?",
    "What’s your tiny victory?",
    "Too early to celebrate?",
    "What’s your unpopular opinion?",
    "What changed your mind?",
    "What’s today’s headline?",
    "What’s your strangest skill?",
    "What would future-you say?",
    "What’s oddly satisfying?",
    "What surprised you lately?",
    "What belief needs updating?",
    "What would you rename?",
    "What deserves a holiday?",
    "What’s your theme song?",
    "What’s your accidental talent?",
    "What should I ask you?",
    "What would you do twice?",
    "Found a secret level?",
    "What’s going surprisingly well?",
    "What would improve the plot?",
    "What rule would you delete?",
    "What deserves a tiny trophy?",
    "What is rarely asked?",
    "What’s secretly interesting?",

    # Very short
    "Good day or weird day?",
    "Big thoughts?",
    "Tiny victory?",
    "Need a distraction?",
    "Feeling lucky?",
    "Want a weird question?",
    "Anything to celebrate?",
)


class SmalltalkStory(AssistantStory):
    """Supplies a changing menu opener and its not-yet-available response."""

    story_id = SMALLTALK_STORY_ID

    def __init__(self, *, random_source: Any = random) -> None:
        self._random_source = random_source

    def menu_choice(self, context: AssistantContext) -> AssistantChoice | None:
        now = _now(context)
        clicked_at = _session_timestamp(
            context.session_state.get(SMALLTALK_CLICKED_AT_SESSION_KEY)
        )
        if clicked_at is not None and now - clicked_at < SMALLTALK_COOLDOWN:
            return None
        if clicked_at is not None:
            context.session_state.pop(SMALLTALK_CLICKED_AT_SESSION_KEY, None)
            context.session_state.pop(SMALLTALK_OPENER_SESSION_KEY, None)
            context.session_state.pop(SMALLTALK_OPENER_SELECTED_AT_SESSION_KEY, None)

        opener = context.session_state.get(SMALLTALK_OPENER_SESSION_KEY)
        selected_at = _session_timestamp(
            context.session_state.get(SMALLTALK_OPENER_SELECTED_AT_SESSION_KEY)
        )
        if (
            not isinstance(opener, str)
            or opener not in SMALLTALK_OPENERS
            or selected_at is None
            or now - selected_at >= SMALLTALK_OPENER_INTERVAL
        ):
            opener = self._random_source.choice(SMALLTALK_OPENERS)
            context.session_state[SMALLTALK_OPENER_SESSION_KEY] = opener
            context.session_state[SMALLTALK_OPENER_SELECTED_AT_SESSION_KEY] = now.isoformat()
        return AssistantChoice(
            SMALLTALK_MENU_CHOICE_ID,
            opener,
        )

    def entry_scene(self, context: AssistantContext) -> str:
        del context
        return SMALLTALK_PLACEHOLDER_SCENE

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        del scene_id, selection
        context.session_state[SMALLTALK_CLICKED_AT_SESSION_KEY] = _now(context).isoformat()
        lines = [AssistantLine("Smalltalk is currently unavailable.")]
        if self._random_source.random() < 0.1:
            lines.insert(0, AssistantLine("Excellent opener."))
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=SMALLTALK_PLACEHOLDER_SCENE,
            lines=tuple(lines),
            state_story=STANDARD_STORY_ID,
            state_scene=STANDARD_MENU_SCENE,
            state_status="completed",
        )


def _now(context: AssistantContext) -> datetime:
    now = context.now or datetime.now(timezone.utc)
    return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now


def _session_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp
