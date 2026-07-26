"""The everyday Dogether assistant story.

Each event is deliberately written as a small, readable scene.  The director
persists the flow/node returned by the scene; it never needs a chat transcript.
"""
from __future__ import annotations

from typing import Final

from src.assistant.core import AssistantContext, AssistantEvent, AssistantView, EventOutcome
from src.assistant.state import AssistantCategory


ONBOARDING_FLOW: Final = "onboarding"
PROFILE_ANALYSIS_FLOW: Final = "profile_analysis"
TOUR_FLOW: Final = "tour"
STANDARD_FLOW: Final = "standard"

WELCOME_NODE: Final = "welcome"
FRIENDS_NODE: Final = "friends"
GOALS_NODE: Final = "goals"
PUSH_NODE: Final = "push_notifications"
TOUR_NODE: Final = "tour"
READY_NODE: Final = "ready"

PUSH_PROMPTED_KEY: Final = "assistant.push_prompted"
ASSISTANT_DISMISSED_KEY: Final = "assistant.dismissed"


def _paused(flow: str, node: str) -> EventOutcome:
    return EventOutcome.pending(flow=flow, node=node, status="paused")


class WelcomeEvent(AssistantEvent):
    event_id = "onboarding.welcome"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        view.say("Hey. I'm here if you need me.")
        view.typing_indicator(0.45)
        view.say("What would you like to do?")
        choice = view.choices(
            self.event_id,
            "",
            "Analyse my profile",
            "Give me a tour",
            "I'm good",
        )
        if choice is None:
            return _paused(ONBOARDING_FLOW, WELCOME_NODE)
        if choice == "Analyse my profile":
            view.say("Good choice.")
            return EventOutcome.pending(
                flow=PROFILE_ANALYSIS_FLOW, node=FRIENDS_NODE, status="active", continue_flow=True
            )
        if choice == "Give me a tour":
            view.say("Nice.")
            return EventOutcome.pending(flow=TOUR_FLOW, node=TOUR_NODE, status="active", continue_flow=True)

        view.say("All right.")
        view.say("I'll leave you to it.")
        view.assistant_leave()
        return EventOutcome.complete(
            flow=STANDARD_FLOW,
            node=READY_NODE,
            status="dismissed",
            knowledge_updates={
                ASSISTANT_DISMISSED_KEY: True,
                PUSH_PROMPTED_KEY: True,
            },
        )


class ResumeEvent(AssistantEvent):
    event_id = "onboarding.resume"
    category = AssistantCategory.STANDARD

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        view.say("Hey, you're back.")
        choice = view.choices(self.event_id, "Continue where we stopped?", "Continue", "Start over")
        if choice is None:
            return EventOutcome()
        if choice == "Start over":
            return EventOutcome.pending(flow=ONBOARDING_FLOW, node=WELCOME_NODE, status="active", continue_flow=True)
        return EventOutcome.pending(
            flow=context.state.flow,
            node=context.state.node,
            status="active",
            continue_flow=True,
        )


class ProfileAnalysisEvent(AssistantEvent):
    event_id = "profile_analysis"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        node = context.state.node or FRIENDS_NODE

        if node == FRIENDS_NODE:
            if context.user_state.get("has_friends", False):
                view.say("Friends look good.")
                node = GOALS_NODE
            else:
                view.say("No friends yet.")
                choice = view.choices(self.event_id, "Want to add one?", "Add a friend", "Later")
                if choice is None:
                    return _paused(PROFILE_ANALYSIS_FLOW, FRIENDS_NODE)
                if choice == "Add a friend":
                    view.say("Open Friends when you're ready.")
                return EventOutcome.pending(flow=PROFILE_ANALYSIS_FLOW, node=GOALS_NODE, status="active", continue_flow=True)

        if node == GOALS_NODE:
            if context.user_state.get("has_goals", False):
                view.say("Goals look good.")
                node = PUSH_NODE
            else:
                view.say("No goals yet.")
                choice = view.choices(self.event_id, "Want to create one?", "Create goal", "Later")
                if choice is None:
                    return _paused(PROFILE_ANALYSIS_FLOW, GOALS_NODE)
                if choice == "Create goal":
                    view.say("Open Manage Goals when you're ready.")
                return EventOutcome.pending(flow=PROFILE_ANALYSIS_FLOW, node=PUSH_NODE, status="active", continue_flow=True)

        if context.user_state.get("push_enabled", False):
            view.say("Push notifications are set.")
            view.say("You're all set.")
            view.assistant_leave()
            return EventOutcome.complete(flow=STANDARD_FLOW, node=READY_NODE, status="completed")

        view.say("One thing is missing.")
        view.say("Push notifications aren't set up.")
        choice = view.choices(self.event_id, "Want to set them up?", "Set up push", "Later")
        if choice is None:
            return _paused(PROFILE_ANALYSIS_FLOW, PUSH_NODE)
        if choice == "Set up push":
            view.say("Open Push Notifications when you're ready.")
        else:
            view.say("No problem.")
        view.assistant_leave()
        return EventOutcome.complete(
            flow=STANDARD_FLOW,
            node=READY_NODE,
            status="completed",
            knowledge_updates={PUSH_PROMPTED_KEY: True},
        )


class TourEvent(AssistantEvent):
    event_id = "tour"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        view.say("Dogether keeps shared goals simple.")
        view.typing_indicator(0.35)
        view.say("Goals is where you track progress.")
        view.say("Friends is where you bring people in.")
        view.say("That's the tour.")
        view.assistant_leave()
        return EventOutcome.complete(flow=STANDARD_FLOW, node=READY_NODE, status="completed")


class AssistantReadyEvent(AssistantEvent):
    event_id = "standard.ready"
    category = AssistantCategory.STANDARD

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        view.status("Assistant ready")
        return EventOutcome()


class PushSetupReminderEvent(AssistantEvent):
    event_id = "standard.push_setup_reminder"
    category = AssistantCategory.STANDARD

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        view.say("One thing is missing.")
        choice = view.choices(self.event_id, "Set up push notifications?", "Set up push", "Later")
        if choice == "Set up push":
            view.say("Open Push Notifications when you're ready.")
        elif choice == "Later":
            view.say("No problem.")
        return EventOutcome.pending(knowledge_updates={PUSH_PROMPTED_KEY: True})


class InitialTutorialStory:
    """Choose one event per render; paused flows always take precedence."""

    story_id = "dogether_assistant"

    def __init__(self) -> None:
        self._welcome = WelcomeEvent()
        self._resume = ResumeEvent()
        self._profile_analysis = ProfileAnalysisEvent()
        self._tour = TourEvent()
        self._ready = AssistantReadyEvent()
        self._push_reminder = PushSetupReminderEvent()

    def next_event(self, context: AssistantContext) -> AssistantEvent | None:
        state = context.state
        if state.status == "dismissed" or state.knowledge.get(ASSISTANT_DISMISSED_KEY, False):
            return None
        if state.status == "paused" and state.flow not in (None, STANDARD_FLOW):
            return self._resume
        if state.flow in (None, ONBOARDING_FLOW):
            return self._welcome
        if state.flow == PROFILE_ANALYSIS_FLOW:
            return self._profile_analysis
        if state.flow == TOUR_FLOW:
            return self._tour
        if (
            not context.user_state.get("push_enabled", False)
            and not state.knowledge.get(PUSH_PROMPTED_KEY, False)
        ):
            return self._push_reminder
        # Standard mode is deliberately quiet after its one eligible event.
        return self._ready if context.current_page_key == "help" else None
