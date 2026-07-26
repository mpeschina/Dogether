"""The deliberately small, NPC-like Dogether onboarding story."""
from __future__ import annotations

from typing import Final

from src.assistant.core import AssistantContext, AssistantEvent, AssistantView, EventOutcome
from src.assistant.state import AssistantCategory


ONBOARDING_FLOW: Final = "onboarding"
PROFILE_ANALYSIS_FLOW: Final = "onboarding_analysis"
TOUR_FLOW: Final = "tour"
STANDARD_FLOW: Final = "standard"

WELCOME_NODE: Final = "onboarding_intro"
# These are durable resume points, not generic screen names.  For example a
# user who leaves to create a goal returns to ``goals.offer_create``.
FRIENDS_NODE: Final = "friends.offer_invite"
GOALS_NODE: Final = "goals.offer_create"
PUSH_NODE: Final = "push.offer_enable"
ANALYSIS_COMPLETE_NODE: Final = "analysis.complete"
TOUR_NODE: Final = "tour"
READY_NODE: Final = "ready"

FRIENDS_EVENT_ID: Final = "friends_check"
GOALS_EVENT_ID: Final = "goals_check"
PUSH_EVENT_ID: Final = "push_check"
ASSISTANT_DISMISSED_KEY: Final = "assistant.dismissed"  # legacy compatibility


def _pending(flow: str, node: str, *, continue_flow: bool = False) -> EventOutcome:
    return EventOutcome.pending(flow=flow, node=node, status="paused", continue_flow=continue_flow)


def _event_outcome(event_id: str, outcome: str, next_node: str, *, continue_flow: bool = True) -> EventOutcome:
    """Record a check's reusable outcome without exposing its UI to the parent."""
    return EventOutcome.pending(
        event_updates={event_id: {"outcome": outcome}},
        flow=PROFILE_ANALYSIS_FLOW,
        node=next_node,
        status="active",
        continue_flow=continue_flow,
    )


class WelcomeEvent(AssistantEvent):
    event_id = "onboarding_intro"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        choice = view.selected_choice(self.event_id, "Analyse my profile", "Give me a tour", "I'm good")
        if choice is not None:
            return self._choose(choice, view)

        view.say("Hi, welcome!")
        view.typing_indicator(1.2)
        view.say("Great to have you here.")
        view.typing_indicator(1.5)
        view.say("Want some help?")
        choice = view.choices(self.event_id, "", "Analyse my profile", "Give me a tour", "I'm good")
        return _pending(ONBOARDING_FLOW, WELCOME_NODE) if choice is None else self._choose(choice, view)

    def _choose(self, choice: str, view: AssistantView) -> EventOutcome:
        if choice == "Analyse my profile":
            return EventOutcome.pending(flow=PROFILE_ANALYSIS_FLOW, node=FRIENDS_NODE, status="active", continue_flow=True)
        if choice == "Give me a tour":
            return EventOutcome.pending(flow=TOUR_FLOW, node=TOUR_NODE, status="active", continue_flow=True)
        view.say("Fair enough.")
        view.typing_indicator(1.2)
        view.say("Have fun in there. 👋")
        view.assistant_leave()
        return EventOutcome.complete(flow=STANDARD_FLOW, node=READY_NODE, status="declined")


class ResumeEvent(AssistantEvent):
    event_id = "onboarding_resume"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        choice = view.selected_choice(self.event_id, "Yes", "Start over")
        if choice is None:
            view.say("Hey, you're back.")
            view.typing_indicator(1.2)
            choice = view.choices(self.event_id, "Continue where we stopped?", "Yes", "Start over")
        if choice is None:
            return EventOutcome()
        if choice == "Start over":
            return EventOutcome.pending(flow=ONBOARDING_FLOW, node=WELCOME_NODE, status="active", continue_flow=True)
        view.say("Perfect.")
        return EventOutcome.pending(flow=context.state.flow, node=context.state.node, status="active", continue_flow=True)


class CheckFriendsEvent(AssistantEvent):
    """Reusable friends check; its result is independent of the parent flow."""
    event_id = FRIENDS_EVENT_ID
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        count = int(context.user_state.get("friend_count", 0))
        prior = context.state.events.get(self.event_id, {})
        if count >= 2:
            view.say("Friends look good. ✓")
            return _event_outcome(self.event_id, "not_needed", GOALS_NODE)
        if count == 1:
            if prior.get("awaiting") == "invite":
                view.say("Nice.")
                view.typing_indicator(1.2)
                view.say("Company acquired. ✓")
            else:
                view.say("You already found someone.")
                view.say("Good start.")
                choice = view.choices(self.event_id, "Want another?", "Invite someone", "I'm good")
                if choice is None:
                    return _pending(PROFILE_ANALYSIS_FLOW, FRIENDS_NODE)
                if choice == "Invite someone":
                    return self._await_invite(context, view)
            return _event_outcome(self.event_id, "completed", GOALS_NODE)

        choice = view.selected_choice(self.event_id, "Invite a friend", "Later")
        if choice is None:
            view.say("First: your people.")
            view.typing_indicator(1.2)
            view.say("It's quiet in here.")
            choice = view.choices(self.event_id, "Invite someone?", "Invite a friend", "Later")
        if choice is None:
            return _pending(PROFILE_ANALYSIS_FLOW, FRIENDS_NODE)
        if choice == "Invite a friend":
            return self._await_invite(context, view)
        return _event_outcome(self.event_id, "skipped", GOALS_NODE)

    def _await_invite(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        view.go_to("friends")
        return EventOutcome.pending(
            event_updates={self.event_id: {"outcome": "interrupted", "awaiting": "invite"}},
            flow=PROFILE_ANALYSIS_FLOW, node=FRIENDS_NODE, status="paused", continue_flow=True,
        )


class CheckGoalsEvent(AssistantEvent):
    """Reusable goals check; it does not assume that more goals are better."""
    event_id = GOALS_EVENT_ID
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        count = int(context.user_state.get("goal_count", 0))
        prior = context.state.events.get(self.event_id, {})
        if count == 0:
            choice = view.selected_choice(self.event_id, "Create a goal", "Later")
            if choice is None:
                view.say("Next: goals.")
                view.typing_indicator(1.2)
                view.say("You don't have one yet.")
                view.say("Let's make that useful.")
                choice = view.choices(self.event_id, "", "Create a goal", "Later")
            if choice is None:
                return _pending(PROFILE_ANALYSIS_FLOW, GOALS_NODE)
            if choice == "Create a goal":
                view.go_to("manage_goals")
                return EventOutcome.pending(
                    event_updates={self.event_id: {"outcome": "interrupted", "awaiting": "create"}},
                    flow=PROFILE_ANALYSIS_FLOW, node=GOALS_NODE, status="paused", continue_flow=True,
                )
            return _event_outcome(self.event_id, "skipped", PUSH_NODE)
        if prior.get("awaiting") == "create":
            view.say("There we go. ✓")
        elif count == 1:
            view.say("You have one goal.")
            view.say("Perfect place to start. ✓")
        else:
            view.say("Goals are looking busy.")
            view.say("I like it. ✓")
        return _event_outcome(self.event_id, "completed" if prior.get("awaiting") else "not_needed", PUSH_NODE)


class CheckPushEvent(AssistantEvent):
    event_id = PUSH_EVENT_ID
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        enabled = bool(context.user_state.get("push_enabled", False))
        prior = context.state.events.get(self.event_id, {})
        if enabled:
            if prior.get("awaiting") == "enable":
                view.say("Perfect. ✓")
                view.say("I'll be gentle.")
                outcome = "completed"
            else:
                view.say("Notifications are ready. ✓")
                outcome = "not_needed"
            return _event_outcome(self.event_id, outcome, ANALYSIS_COMPLETE_NODE)
        choice = view.selected_choice(self.event_id, "Enable notifications", "Not now")
        if choice is None:
            view.say("One last thing.")
            view.typing_indicator(1.2)
            view.say("I can nudge you.")
            view.say("But I need permission.")
            choice = view.choices(self.event_id, "", "Enable notifications", "Not now")
        if choice is None:
            return _pending(PROFILE_ANALYSIS_FLOW, PUSH_NODE)
        if choice == "Enable notifications":
            view.go_to("push_notifications")
            return EventOutcome.pending(
                event_updates={self.event_id: {"outcome": "interrupted", "awaiting": "enable"}},
                flow=PROFILE_ANALYSIS_FLOW, node=PUSH_NODE, status="paused", continue_flow=True,
            )
        return _event_outcome(self.event_id, "skipped", ANALYSIS_COMPLETE_NODE)


class AnalysisCompleteEvent(AssistantEvent):
    event_id = "analysis_complete"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        choice = view.selected_choice(self.event_id, "Thanks!")
        if choice is None:
            view.say("That's it.")
            view.typing_indicator(1.2)
            view.say("You're ready. ✓")
            view.typing_indicator(1.2)
            view.say("I'll get out of your way.")
            choice = view.choices(self.event_id, "", "Thanks!")
        if choice is None:
            return _pending(PROFILE_ANALYSIS_FLOW, ANALYSIS_COMPLETE_NODE)
        view.assistant_leave()
        return EventOutcome.complete(flow=STANDARD_FLOW, node=READY_NODE, status="completed")


class ProfileAnalysisEvent(AssistantEvent):
    """Parent coordinator. It only dispatches checks; it owns no check UI."""
    event_id = "profile_analysis"
    category = AssistantCategory.TUTORIAL

    def __init__(self) -> None:
        self._events = {FRIENDS_NODE: CheckFriendsEvent(), GOALS_NODE: CheckGoalsEvent(), PUSH_NODE: CheckPushEvent(), ANALYSIS_COMPLETE_NODE: AnalysisCompleteEvent()}

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        return self._events.get(context.state.node or FRIENDS_NODE, self._events[FRIENDS_NODE]).render(context, view)


class TourEvent(AssistantEvent):
    event_id = "tour"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        choice = view.selected_choice(self.event_id, "Got it")
        if choice is None:
            view.say("Sure.")
            view.typing_indicator(1.2)
            view.say("Dogether is simple.")
            view.typing_indicator(1.2)
            view.say("Pick something worth doing.")
            view.typing_indicator(1.2)
            view.say("Bring someone along.")
            view.typing_indicator(1.2)
            view.say("Keep each other moving.")
            view.typing_indicator(1.2)
            view.say("That's basically it.")
            view.say("You'll figure out the rest.")
            choice = view.choices(self.event_id, "", "Got it")
        if choice is None:
            return _pending(TOUR_FLOW, TOUR_NODE)
        view.say("Enjoy. 👋")
        view.assistant_leave()
        return EventOutcome.complete(flow=STANDARD_FLOW, node=READY_NODE, status="completed")


class AssistantReadyEvent(AssistantEvent):
    event_id = "standard.ready"
    category = AssistantCategory.STANDARD
    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        return EventOutcome()


class PushSetupReminderEvent(AssistantReadyEvent):
    """Retained as an import-compatible no-op; onboarding owns the push prompt."""
    event_id = "standard.push_setup_reminder"


class InitialTutorialStory:
    story_id = "dogether_assistant"

    def __init__(self) -> None:
        self._welcome, self._resume = WelcomeEvent(), ResumeEvent()
        self._profile_analysis, self._tour = ProfileAnalysisEvent(), TourEvent()

    def next_event(self, context: AssistantContext) -> AssistantEvent | None:
        state = context.state
        if state.status in {"dismissed", "declined", "completed"}:
            return None
        if state.status == "paused" and state.flow not in (None, STANDARD_FLOW) and context.previous_page_key != "help":
            return self._resume
        if state.flow in (None, ONBOARDING_FLOW):
            return self._welcome
        if state.flow == PROFILE_ANALYSIS_FLOW:
            return self._profile_analysis
        if state.flow == TOUR_FLOW:
            return self._tour
        return None
