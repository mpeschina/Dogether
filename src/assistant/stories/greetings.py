"""Occasional session-scoped greetings expressed as declarative turns."""
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


GREETINGS_STORY_ID: Final = "greetings"
GREETING_SELECTION_SESSION_KEY: Final = "greetings.selection"
GREETING_PENDING_SESSION_KEY: Final = "greetings.pending"
GREETING_RANDOMIZED_AT_SESSION_KEY: Final = "greetings.randomized_at"
GREETING_SILENT_REPLY_SESSION_KEY: Final = "greetings.silent_reply"
GREETING_INTERVAL: Final = timedelta(hours=1)
# Set to ``None`` to restore normal greeting selection.
DEBUG_GREETING_ID: str | None = None # "waiting_crack"

NORMAL_GREETING_IDS: Final = (
    "tiny_progress",
    "move_something",
    "little_win",
    "make_today_count",
    "another_point",
    "nudge_something",
    "goals_await",
    "goals_noticed",
    "progress_chat",
    "microscopic_victory",
    "oh_human",
    "survived",
    "returned",
    "well_well_well",
    "prophecy",
    "you_again",
    "unexpected_welcome",
    "thinking_about_goals",
    "perfect_timing",
    "sensed_activity",
    "door_unlocked",
    "found_me",
    "click_eventually",
    "council",
    "suspiciously_well",
    "there_you_are",
    "have_a_plan",
    "mission_today",
    "finally",
)
INTERACTIVE_GREETING_IDS: Final = (
    "mood_check",
    "cowboy",
    "suspicion",
    "productivity_check",
    "tiny_victory",
    "secret_club",
    "dangerous_confidence",
)
RARE_GREETING_IDS: Final = ("silent", "waiting_crack", "malfunction")

NORMAL_MESSAGES: Final = {
    "tiny_progress": "Tiny progress time.",
    "move_something": "Let’s move something.",
    "little_win": "One little win?",
    "make_today_count": "Let’s make today count.",
    "another_point": "Another day. Another point.",
    "nudge_something": "Ready to nudge something?",
    "goals_await": "Goals await.",
    "goals_noticed": "Your goals noticed you.",
    "progress_chat": "Progress has entered the chat.",
    "microscopic_victory": "Time for a microscopic victory.",
    "oh_human": "Oh! A human.",
    "survived": "Ah. You survived.",
    "returned": "Interesting. You returned.",
    "well_well_well": "Well, well, well.",
    "prophecy": "The prophecy continues.",
    "you_again": "You again. Excellent.",
    "unexpected_welcome": "Unexpected. But welcome.",
    "thinking_about_goals": "I was just thinking about goals.",
    "perfect_timing": "Perfect timing.",
    "sensed_activity": "I sensed activity.",
    "door_unlocked": "The door was unlocked.",
    "found_me": "You found me.",
    "click_eventually": "I knew you’d click eventually.",
    "council": "The council expected you.",
    "suspiciously_well": "Everything is proceeding suspiciously well.",
    "there_you_are": "There you are.",
    "have_a_plan": "I have a plan.",
    "mission_today": "Okay. Mission for today:",
    "finally": "Finally.",
}
INTERACTIVE_MESSAGES: Final = {
    "mood_check": (
        "Important question. You feel ready?",
        (("ready", "Ready."), ("not_ready", "Absolutely not.")),
        {"ready": "Excellent.", "not_ready": "Understandable."},
    ),
    "cowboy": (
        "Howdy, partner.",
        (("howdy", "Howdy."), ("no_cowboy", "Please don’t.")),
        {"howdy": "That’s the spirit.", "no_cowboy": "Understood. Business mode."},
    ),
    "suspicion": (
        "Are you ready?",
        (("yes", "Yes."), ("for_what", "For what?")),
        {"yes": "Excellent.", "for_what": "No idea."},
    ),
    "productivity_check": (
        "Quick productivity check.",
        (("productive", "Extremely productive."), ("conscious", "Barely conscious.")),
        {"productive": "I knew it.", "conscious": "Still counts."},
    ),
    "tiny_victory": (
        "Can we get one tiny win today?",
        (("yes", "Yes."), ("tiny", "Tiny tiny.")),
        {"yes": "Deal.", "tiny": "Deal."},
    ),
    "secret_club": (
        "Password?",
        (("dogether", "Dogether."), ("forgot", "I forgot.")),
        {"dogether": "Access granted.", "forgot": "Close enough."},
    ),
    "dangerous_confidence": (
        "I have good news.",
        (("tell_me", "Tell me."), ("distrust", "I don’t trust you.")),
        {"tell_me": "Excellent attitude.", "distrust": "Also excellent."},
    ),
}
SILENT_REPLIES: Final = (
    "I was waiting for you to go first.",
    "Excellent. Social protocol completed.",
    "Thank you. I never know who should start.",
    "Good. I didn’t want to make this awkward.",
)
SILENT_GREETING_CHOICES: Final = (
    AssistantChoice("hello", "Hello."),
    AssistantChoice("hi", "Hi."),
    AssistantChoice("hey", "Hey."),
)


class GreetingsStory(AssistantStory):
    story_id = GREETINGS_STORY_ID

    def __init__(self, _menu_story: object | None = None, *, random_source: Any = random) -> None:
        self._random_source = random_source

    def entry_scene(self, context: AssistantContext) -> str:
        if DEBUG_GREETING_ID is not None:
            return DEBUG_GREETING_ID

        session = context.session_state
        pending = session.get(GREETING_PENDING_SESSION_KEY)
        if isinstance(pending, str):
            return pending

        if not self._randomized_greeting_is_due(context):
            return "default"

        greeting_id = self._choose_greeting_id()
        session[GREETING_SELECTION_SESSION_KEY] = greeting_id
        session[GREETING_RANDOMIZED_AT_SESSION_KEY] = _now(context).isoformat()
        if greeting_id in INTERACTIVE_GREETING_IDS or greeting_id in RARE_GREETING_IDS:
            session[GREETING_PENDING_SESSION_KEY] = greeting_id
        if greeting_id == "silent":
            session[GREETING_SILENT_REPLY_SESSION_KEY] = self._random_source.choice(SILENT_REPLIES)
        return greeting_id

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        greeting_id = DEBUG_GREETING_ID or scene_id or self.entry_scene(context)
        if greeting_id in INTERACTIVE_GREETING_IDS:
            return self._interactive_turn(context, greeting_id, selection)
        if greeting_id == "silent":
            return self._silent_turn(context, selection)
        if greeting_id == "waiting_crack":
            return self._waiting_crack_turn(context, selection)
        if greeting_id == "malfunction":
            context.session_state.pop(GREETING_PENDING_SESSION_KEY, None)
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=greeting_id,
                lines=(
                    AssistantLine("Initializing motivational systems…", typing_delay=0),
                    AssistantLine("Motivation not found.", typing_delay=0),
                    AssistantLine("We’ll improvise.", typing_delay=0),
                ),
                continue_flow=True,
            )

        if greeting_id == "finally":
            lines = (AssistantLine(NORMAL_MESSAGES[greeting_id], typing_delay=0),)
        else:
            message = "Hello" if greeting_id == "default" else NORMAL_MESSAGES[greeting_id]
            lines = (AssistantLine(message),)
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=greeting_id,
            lines=lines,
            continue_flow=True,
        )

    def _interactive_turn(
        self,
        context: AssistantContext,
        greeting_id: str,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        intro, raw_choices, responses = INTERACTIVE_MESSAGES[greeting_id]
        if selection is None:
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=greeting_id,
                lines=(AssistantLine(intro),),
                choices=tuple(AssistantChoice(id=choice_id, label=label) for choice_id, label in raw_choices),
            )
        context.session_state.pop(GREETING_PENDING_SESSION_KEY, None)
        response = responses.get(selection.choice_id, next(iter(responses.values())))
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=greeting_id,
            lines=(AssistantLine(response),),
            continue_flow=True,
        )

    def _silent_turn(
        self, context: AssistantContext, selection: AssistantSelection | None
    ) -> AssistantTurn:
        if selection is None:
            return AssistantTurn(
                story_id=self.story_id,
                scene_id="silent",
                choices=SILENT_GREETING_CHOICES,
            )
        context.session_state.pop(GREETING_PENDING_SESSION_KEY, None)
        reply = context.session_state.pop(
            GREETING_SILENT_REPLY_SESSION_KEY, SILENT_REPLIES[0]
        )
        return AssistantTurn(
            story_id=self.story_id,
            scene_id="silent",
            lines=(AssistantLine("Oh! Hello."), AssistantLine(str(reply), typing_delay=0)),
            continue_flow=True,
        )

    def _waiting_crack_turn(
        self, context: AssistantContext, selection: AssistantSelection | None
    ) -> AssistantTurn:
        if selection is None:
            return AssistantTurn(
                story_id=self.story_id,
                scene_id="waiting_crack",
                lines=(
                    AssistantLine("", wait_before=1, typing_delay=2.5, wait_after=2),
                    AssistantLine("", typing_delay=0.5, wait_after=1),
                    AssistantLine("", typing_delay=2),
                    AssistantLine("Are we both waiting for the other person?"),
                ),
                choices=(AssistantChoice("apparently", "Apparently."),),
            )
        context.session_state.pop(GREETING_PENDING_SESSION_KEY, None)
        return AssistantTurn(
            story_id=self.story_id,
            scene_id="waiting_crack",
            lines=(AssistantLine("Okay. Hello."),),
            continue_flow=True,
        )

    def _choose_greeting_id(self) -> str:
        roll = self._random_source.random()
        if roll < 0.6:
            return self._random_source.choice(NORMAL_GREETING_IDS)
        if roll < 0.9:
            return self._random_source.choice(INTERACTIVE_GREETING_IDS)
        return self._random_source.choice(RARE_GREETING_IDS)

    @staticmethod
    def _randomized_greeting_is_due(context: AssistantContext) -> bool:
        selected_at = _parse_timestamp(
            context.session_state.get(GREETING_RANDOMIZED_AT_SESSION_KEY)
        )
        return selected_at is None or _now(context) >= selected_at + GREETING_INTERVAL


def _now(context: AssistantContext) -> datetime:
    now = context.now or datetime.now(timezone.utc)
    return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp
