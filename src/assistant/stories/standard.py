"""The default, user-directed assistant experience."""
from __future__ import annotations

from typing import Final

from src.assistant.core import AssistantContext, AssistantEvent, AssistantView, EventOutcome
from src.assistant.state import AssistantCategory
from src.assistant.stories.tutorial import (
    CheckFriendsEvent,
    CheckGoalsEvent,
    CheckPushEvent,
    FRIENDS_NODE,
    GOALS_NODE,
    PUSH_NODE,
    READY_NODE,
    STANDARD_FLOW,
)


STANDARD_STORY_ID: Final = "standard"
STANDARD_MENU_EVENT_ID: Final = "standard.tutorial_menu"
STANDARD_TUTORIAL_FLOW: Final = "standard.tutorial"
STANDARD_PUSH_FLOW: Final = "standard.push_reminder"
STANDARD_PUSH_NODE: Final = "push.offer_enable"
PUSH_PROMPT_EVENT_ID: Final = "standard.push_prompt"

TUTORIAL_OPTIONS: Final = (
    ("How do I add friends?", "tutorial.friends.seen", FRIENDS_NODE),
    ("How do I create a goal?", "tutorial.goals.seen", GOALS_NODE),
    ("How do notifications work?", "tutorial.notifications.seen", PUSH_NODE),
    ("How do I track progress?", "tutorial.progress.seen", None),
)


class StandardMenuEvent(AssistantEvent):
    """A deliberately small fallback; it does not decide when to interrupt."""

    event_id = STANDARD_MENU_EVENT_ID
    category = AssistantCategory.STANDARD

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        options = tuple(label for label, _, _ in TUTORIAL_OPTIONS)
        choice = view.selected_choice(self.event_id, *options)
        if choice is None:
            view.say("Hello")
            choice = view.choices(self.event_id, "Tutorials", *options)
        if choice is None:
            return EventOutcome()

        _, knowledge_key, tutorial_node = next(
            item for item in TUTORIAL_OPTIONS if item[0] == choice
        )
        if tutorial_node is not None:
            return EventOutcome.pending(
                knowledge_updates={knowledge_key: True},
                flow=STANDARD_TUTORIAL_FLOW,
                node=tutorial_node,
                status="active",
                continue_flow=True,
            )

        view.say("That tutorial is coming soon.")
        return EventOutcome.pending(knowledge_updates={knowledge_key: True})


class StandardTutorialEvent(AssistantEvent):
    """Run one reusable onboarding check without advancing onboarding."""

    category = AssistantCategory.TUTORIAL

    def __init__(self, node: str, event: AssistantEvent) -> None:
        self.node = node
        self.event = event
        self.event_id = event.event_id

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        outcome = self.event.render(context, view)
        if outcome.status == "paused":
            return EventOutcome.pending(
                event_updates=outcome.event_updates,
                knowledge_updates=outcome.knowledge_updates,
                flow=STANDARD_TUTORIAL_FLOW,
                node=self.node,
                status="paused",
                continue_flow=outcome.continue_flow,
            )
        return EventOutcome.complete(
            event_updates=outcome.event_updates,
            knowledge_updates=outcome.knowledge_updates,
            clear_events=outcome.clear_events,
            flow=STANDARD_FLOW,
            node=READY_NODE,
            status="completed",
        )


class StandardStory:
    """Owns the default menu and its standalone tutorials."""

    story_id = STANDARD_STORY_ID

    def __init__(self) -> None:
        self._menu = StandardMenuEvent()
        self._tutorials = {
            FRIENDS_NODE: StandardTutorialEvent(FRIENDS_NODE, CheckFriendsEvent()),
            GOALS_NODE: StandardTutorialEvent(GOALS_NODE, CheckGoalsEvent()),
            PUSH_NODE: StandardTutorialEvent(PUSH_NODE, CheckPushEvent()),
        }

    def next_event(self, context: AssistantContext) -> AssistantEvent:
        if context.state.flow == STANDARD_TUTORIAL_FLOW:
            return self._tutorials.get(context.state.node or "", self._menu)
        return self._menu
