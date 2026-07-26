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
FRIENDS_EXPLANATION_NODE: Final = "friends.explain"
GOALS_NODE: Final = "goals.offer_create"
GOALS_EXPLANATION_NODE: Final = "goals.explain"
PUSH_NODE: Final = "push.offer_enable"
PUSH_EXPLANATION_NODE: Final = "push.explain"
ANALYSIS_COMPLETE_NODE: Final = "analysis.complete"
TOUR_NODE: Final = "tour"
READY_NODE: Final = "ready"

FRIENDS_EVENT_ID: Final = "friends_check"
GOALS_EVENT_ID: Final = "goals_check"
PUSH_EVENT_ID: Final = "push_check"
ASSISTANT_DISMISSED_KEY: Final = "assistant.dismissed"  # legacy compatibility
GOALS_EXPLANATION_STEP_KEY: Final = "assistant.goals_explanation_step"
FRIENDS_EXPLANATION_STEP_KEY: Final = "assistant.friends_explanation_step"
PUSH_EXPLANATION_STEP_KEY: Final = "assistant.push_explanation_step"


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
            view.say("Continue where we stopped?")
            choice = view.choices(self.event_id, "", "Yes", "Start over")
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

        choice = view.selected_choice(self.event_id, "Invite a friend", "Explain the Friendlist to me", "Later")
        if choice is None:
            view.say("First: your people.")
            view.typing_indicator(1.2)
            view.say("It's quiet in here.")
            choice = view.choices(self.event_id, "Invite someone?", "Invite a friend", "Explain the Friendlist to me", "Later")
        if choice is None:
            return _pending(PROFILE_ANALYSIS_FLOW, FRIENDS_NODE)
        if choice == "Invite a friend":
            return self._await_invite(context, view)
        if choice == "Explain the Friendlist to me":
            return EventOutcome.pending(
                flow=PROFILE_ANALYSIS_FLOW,
                node=FRIENDS_EXPLANATION_NODE,
                status="active",
                continue_flow=True,
            )
        return _event_outcome(self.event_id, "skipped", GOALS_NODE)

    def _await_invite(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        view.go_to("friends")
        return EventOutcome.pending(
            event_updates={self.event_id: {"outcome": "interrupted", "awaiting": "invite"}},
            flow=PROFILE_ANALYSIS_FLOW, node=FRIENDS_NODE, status="paused", continue_flow=True,
        )


class FriendlistExplanationStepEvent(AssistantEvent):
    """The optional, transient Friendlist explanation conversation."""
    event_id = "friends_explanation"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        current_step = str(context.session_state.get(FRIENDS_EXPLANATION_STEP_KEY, "intro"))
        choice_event_id = f"{self.event_id}.{current_step}"
        if current_step == "intro":
            choice = view.selected_choice(choice_event_id, "How do I add friends?", "Got it")
            if choice is None:
                view.typing_indicator()
                view.say("Sure, I'll explain it to you:")
                view.typing_indicator()
                view.say("Friends unlock shared goals.")
                choice = view.choices(choice_event_id, "", "How do I add friends?", "Got it")
                if choice is None:
                    return _pending(PROFILE_ANALYSIS_FLOW, FRIENDS_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state[FRIENDS_EXPLANATION_STEP_KEY] = "options"
            return self.render(context, view)

        if current_step == "options":
            choice = view.selected_choice(choice_event_id, "How does the link work?", "Makes sense")
            if choice is None:
                view.typing_indicator()
                view.say("You have two options to add friends here.")
                view.typing_indicator()
                view.say("Invite them by email.")
                view.typing_indicator()
                view.say("Or share your invite link.")
                choice = view.choices(choice_event_id, "", "How does the link work?", "Makes sense")
                if choice is None:
                    return _pending(PROFILE_ANALYSIS_FLOW, FRIENDS_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state[FRIENDS_EXPLANATION_STEP_KEY] = "link"
            return self.render(context, view)

        if current_step == "link":
            choice = view.selected_choice(choice_event_id, "Create a Link for me", "Show me the Friends Page", "Got it")
            if choice is None:
                view.typing_indicator()
                view.say("Your link belongs to you.")
                view.say("Someone opens it.")
                view.typing_indicator(3)
                view.say("You get a friend invite that you can accept or deny. Only Friends can share goals.")
                view.typing_indicator()
                view.say("And it is at the heart of the app to work on a shared goal together with your friends.")
                choice = view.choices(choice_event_id, "", "Create a Link for me", "Show me the Friends Page", "Got it")
                if choice is None:
                    return _pending(PROFILE_ANALYSIS_FLOW, FRIENDS_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()

            context.session_state.pop(FRIENDS_EXPLANATION_STEP_KEY, None)
            if choice == "Create a Link for me":
                if context.create_friend_share_link is None:
                    view.typing_indicator()
                    view.status("I couldn't create a link right now.")
                    return EventOutcome()
                view.typing_indicator()
                view.say(f"Here’s your invite link:\n\n{context.create_friend_share_link()}")
                context.session_state[FRIENDS_EXPLANATION_STEP_KEY] = "goodbye"
                return self.render(context, view)
            if choice == "Show me the Friends Page":
                view.go_to("friends")
                return EventOutcome.pending(flow=PROFILE_ANALYSIS_FLOW, node=FRIENDS_NODE, status="paused", continue_flow=True)

            context.session_state[FRIENDS_EXPLANATION_STEP_KEY] = "goodbye"
            return self.render(context, view)

        if current_step == "goodbye":
            choice = view.selected_choice(choice_event_id, "Ciao, thanks for the explanation")
            if choice is None:
                choice = view.choices(choice_event_id, "", "Ciao, thanks for the explanation")
            if choice is None:
                return _pending(PROFILE_ANALYSIS_FLOW, FRIENDS_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state.pop(FRIENDS_EXPLANATION_STEP_KEY, None)
            view.assistant_leave()
            return EventOutcome.complete(flow=STANDARD_FLOW, node=READY_NODE, status="completed")

        context.session_state.pop(FRIENDS_EXPLANATION_STEP_KEY, None)
        return EventOutcome.pending(flow=PROFILE_ANALYSIS_FLOW, node=FRIENDS_EXPLANATION_NODE, status="active", continue_flow=True)


class CheckGoalsEvent(AssistantEvent):
    """Reusable goals check; it does not assume that more goals are better."""
    event_id = GOALS_EVENT_ID
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        count = int(context.user_state.get("goal_count", 0))
        prior = context.state.events.get(self.event_id, {})
        if count == 0:
            choice = view.selected_choice(self.event_id, "Create a goal", "Explain Goals to me", "Later")
            if choice is None:
                view.typing_indicator()
                view.say("Next: goals.")
                view.typing_indicator()
                view.say("You don't have one yet.")
                view.typing_indicator()
                view.say("Let's make that useful.")
                choice = view.choices(self.event_id, "", "Create a goal", "Explain Goals to me", "Later")
            if choice is None:
                return _pending(PROFILE_ANALYSIS_FLOW, GOALS_NODE)
            if choice == "Create a goal":
                view.go_to("manage_goals")
                return EventOutcome.pending(
                    event_updates={self.event_id: {"outcome": "interrupted", "awaiting": "create"}},
                    flow=PROFILE_ANALYSIS_FLOW, node=GOALS_NODE, status="paused", continue_flow=True,
                )
            if choice == "Explain Goals to me":
                return EventOutcome.pending(
                    flow=PROFILE_ANALYSIS_FLOW,
                    node=GOALS_EXPLANATION_NODE,
                    status="active",
                    continue_flow=True,
                )
            return _event_outcome(self.event_id, "skipped", PUSH_NODE)
        if prior.get("awaiting") == "create":
            view.typing_indicator()
            view.say("There we go. ✓")
        elif count == 1:
            view.typing_indicator()
            view.say("You have one goal.")
            view.typing_indicator()
            view.say("Perfect place to start. ✓")
        else:
            view.typing_indicator()
            view.say("Goals are looking busy.")
            view.typing_indicator()
            view.say("I like it. ✓")
        return _event_outcome(self.event_id, "completed" if prior.get("awaiting") else "not_needed", PUSH_NODE)


class GoalExplanationStepEvent(AssistantEvent):
    """The optional, transient goals explanation conversation."""
    event_id = "goals_explanation"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        current_step = str(context.session_state.get(GOALS_EXPLANATION_STEP_KEY, "intro"))
        choice_event_id = f"{self.event_id}.{current_step}"
        if current_step == "intro":
            choice = view.selected_choice(choice_event_id, "How do goals work?", "Got it")
            if choice is not None:
                current_step = "how_goals_work"
                context.session_state[GOALS_EXPLANATION_STEP_KEY] = current_step
                choice_event_id = f"{self.event_id}.{current_step}"
            else:
                view.say("Sure.")
                view.typing_indicator()
                view.say("Goals are the heart of Dogether.")
                view.typing_indicator()
                view.say("You work on them every day.")
                view.typing_indicator()
                view.say("And your friends help you stay on track.")
                choice = view.choices(choice_event_id, "", "How do goals work?", "Got it")
                if choice is None:
                    return _pending(PROFILE_ANALYSIS_FLOW, GOALS_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
                current_step = "how_goals_work"
                context.session_state[GOALS_EXPLANATION_STEP_KEY] = current_step
                choice_event_id = f"{self.event_id}.{current_step}"

        if current_step == "how_goals_work":
            choice = view.selected_choice(choice_event_id, "Makes sense", "What about progress?")
            if choice is not None:
                context.session_state[GOALS_EXPLANATION_STEP_KEY] = "progress"
                return self.render(context, view)
            view.typing_indicator()
            view.say("Every goal has participants.")
            view.typing_indicator()
            view.say("Anyone can invite friends.")
            view.typing_indicator()
            view.say("But you only see your friends.")
            view.typing_indicator()
            view.say("There may be others too.")
            choice = view.choices(choice_event_id, "", "Makes sense", "What about progress?")
            if choice is None:
                return _pending(PROFILE_ANALYSIS_FLOW, GOALS_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state[GOALS_EXPLANATION_STEP_KEY] = "progress"
            return self.render(context, view)

        if current_step == "progress":
            choice = view.selected_choice(choice_event_id, "Nice", "What do friends do?")
            if choice is not None:
                context.session_state[GOALS_EXPLANATION_STEP_KEY] = "friends"
                return self.render(context, view)
            view.typing_indicator()
            view.say("Everyone tracks their own progress.")
            view.typing_indicator()
            view.say("And everyone can have their own maximum.")
            view.typing_indicator()
            view.say("So the goal stays personal.")
            choice = view.choices(choice_event_id, "", "Nice", "What do friends do?")
            if choice is None:
                return _pending(PROFILE_ANALYSIS_FLOW, GOALS_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state[GOALS_EXPLANATION_STEP_KEY] = "friends"
            return self.render(context, view)

        if current_step == "friends":
            choice = view.selected_choice(choice_event_id, "And then?")
            if choice is not None:
                context.session_state[GOALS_EXPLANATION_STEP_KEY] = "reactions"
                return self.render(context, view)
            view.typing_indicator()
            view.say("This is where it gets fun.")
            view.typing_indicator()
            view.say("When a friend completes the goal…")
            view.typing_indicator()
            view.say("You can get a notification.")
            choice = view.choices(choice_event_id, "", "And then?")
            if choice is None:
                return _pending(PROFILE_ANALYSIS_FLOW, GOALS_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state[GOALS_EXPLANATION_STEP_KEY] = "reactions"
            return self.render(context, view)

        if current_step == "reactions":
            choice = view.selected_choice(choice_event_id, "Got it")
            if choice is not None:
                context.session_state[GOALS_EXPLANATION_STEP_KEY] = "finish"
                return self.render(context, view)
            view.typing_indicator()
            view.say("Send them a reaction.")
            view.typing_indicator()
            view.say("A little celebration.")
            view.typing_indicator()
            view.say("Or some friendly pressure.")
            choice = view.choices(choice_event_id, "", "Got it")
            if choice is None:
                return _pending(PROFILE_ANALYSIS_FLOW, GOALS_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state[GOALS_EXPLANATION_STEP_KEY] = "finish"
            return self.render(context, view)

        choice = view.selected_choice(choice_event_id, "Create a goal", "Cool, thank you for the explanation.")
        if choice is None:
            view.typing_indicator()
            view.say("That’s basically goals.")
            choice = view.choices(choice_event_id, "", "Create a goal", "Cool, thank you for the explanation.")
            if choice is None:
                return _pending(PROFILE_ANALYSIS_FLOW, GOALS_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
        context.session_state.pop(GOALS_EXPLANATION_STEP_KEY, None)
        if choice == "Cool, thank you for the explanation.":
            view.say("Ciao.")
            view.assistant_leave()
            return EventOutcome.complete(flow=STANDARD_FLOW, node=READY_NODE, status="completed")
        if choice == "Create a goal":
            view.go_to("manage_goals")
            return EventOutcome.pending(
                event_updates={GOALS_EVENT_ID: {"outcome": "interrupted", "awaiting": "create"}},
                flow=PROFILE_ANALYSIS_FLOW, node=GOALS_NODE, status="paused", continue_flow=True,
            )
        return EventOutcome.pending(flow=PROFILE_ANALYSIS_FLOW, node=GOALS_NODE, status="active", continue_flow=True)


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
        choice = view.selected_choice(self.event_id, "Enable notifications", "Explain notifications to me", "Not now")
        if choice is None:
            view.say("One last thing.")
            view.typing_indicator()
            view.say("I can nudge you.")
            view.typing_indicator()
            view.say("But I need permission.")
            choice = view.choices(self.event_id, "", "Enable notifications", "Explain notifications to me", "Not now")
        if choice is None:
            return _pending(PROFILE_ANALYSIS_FLOW, PUSH_NODE)
        if choice == "Enable notifications":
            view.go_to("push_notifications")
            return EventOutcome.pending(
                event_updates={self.event_id: {"outcome": "interrupted", "awaiting": "enable"}},
                flow=PROFILE_ANALYSIS_FLOW, node=PUSH_NODE, status="paused", continue_flow=True,
            )
        if choice == "Explain notifications to me":
            return EventOutcome.pending(
                flow=PROFILE_ANALYSIS_FLOW,
                node=PUSH_EXPLANATION_NODE,
                status="active",
                continue_flow=True,
            )
        return _event_outcome(self.event_id, "skipped", ANALYSIS_COMPLETE_NODE)


class NotificationExplanationStepEvent(AssistantEvent):
    """The optional, transient notification explanation conversation."""
    event_id = "notifications_explanation"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        current_step = str(context.session_state.get(PUSH_EXPLANATION_STEP_KEY, "intro"))
        choice_event_id = f"{self.event_id}.{current_step}"

        if current_step == "intro":
            choice = view.selected_choice(choice_event_id, "Why do they matter?", "Got it")
            if choice is None:
                view.say("Sure.")
                view.typing_indicator()
                view.say("Notifications are an integral part. They keep shared goals moving.")
                choice = view.choices(choice_event_id, "", "Why do they matter?", "Got it")
                if choice is None:
                    return _pending(PROFILE_ANALYSIS_FLOW, PUSH_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state[PUSH_EXPLANATION_STEP_KEY] = "shared_goals"
            return self.render(context, view)

        if current_step == "shared_goals":
            choice = view.selected_choice(choice_event_id, "How do I enable them?", "Makes sense")
            if choice is None:
                view.typing_indicator()
                view.say("Friends can finish a shared goal.")
                view.typing_indicator()
                view.say("You can celebrate right away.")
                view.typing_indicator()
                view.say("They can react when you finish too.")
                choice = view.choices(choice_event_id, "", "How do I enable them?", "Makes sense")
                if choice is None:
                    return _pending(PROFILE_ANALYSIS_FLOW, PUSH_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state[PUSH_EXPLANATION_STEP_KEY] = "mobile_installation"
            return self.render(context, view)

        if current_step == "mobile_installation":
            choice = view.selected_choice(choice_event_id, "Why install it?", "Got it")
            if choice is None:
                view.typing_indicator()
                view.say("Desktop is straightforward.")
                view.typing_indicator()
                view.say("On iPhone and Android, install Dogether to your Home Screen first.")
                choice = view.choices(choice_event_id, "", "Why install it?", "Got it")
                if choice is None:
                    return _pending(PROFILE_ANALYSIS_FLOW, PUSH_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state[PUSH_EXPLANATION_STEP_KEY] = "os_consent"
            return self.render(context, view)

        if current_step == "os_consent":
            choice = view.selected_choice(choice_event_id, "What can I control?", "Makes sense")
            if choice is None:
                view.typing_indicator()
                view.say("The installed app can ask your phone for permission.")
                view.typing_indicator(3)
                view.say("Your operating system shows the consent prompt. Only you can approve it.")
                choice = view.choices(choice_event_id, "", "What can I control?", "Makes sense")
                if choice is None:
                    return _pending(PROFILE_ANALYSIS_FLOW, PUSH_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state[PUSH_EXPLANATION_STEP_KEY] = "goal_controls"
            return self.render(context, view)

        if current_step == "goal_controls":
            choice = view.selected_choice(choice_event_id, "Which settings?", "Got it")
            if choice is None:
                view.typing_indicator()
                view.say("Notifications are not all-or-nothing.")
                view.typing_indicator()
                view.say("Each goal has its own settings.")
                choice = view.choices(choice_event_id, "", "Which settings?", "Got it")
                if choice is None:
                    return _pending(PROFILE_ANALYSIS_FLOW, PUSH_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state[PUSH_EXPLANATION_STEP_KEY] = "available_settings"
            return self.render(context, view)

        if current_step == "available_settings":
            choice = view.selected_choice(choice_event_id, "Where are those controls?", "Makes sense")
            if choice is None:
                view.typing_indicator(3.5)
                view.say("Choose alerts when friends complete it and cap completion alerts per day. Also, choose alerts for reactions.")
                choice = view.choices(choice_event_id, "", "Where are those controls?", "Makes sense")
                if choice is None:
                    return _pending(PROFILE_ANALYSIS_FLOW, PUSH_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()
            context.session_state[PUSH_EXPLANATION_STEP_KEY] = "finish"
            return self.render(context, view)

        if current_step == "finish":
            options = ("Enable notifications", "Show me Manage Goals", "Cool, thank you for the explanation.")
            choice = view.selected_choice(choice_event_id, *options)
            if choice is None:
                view.typing_indicator()
                view.say("They live on Manage Goals.")
                view.typing_indicator()
                view.say("Open a goal.")
                view.typing_indicator()
                view.say("Adjust what works for you.")
                choice = view.choices(choice_event_id, "", *options)
                if choice is None:
                    return _pending(PROFILE_ANALYSIS_FLOW, PUSH_EXPLANATION_NODE) if context.state.flow == PROFILE_ANALYSIS_FLOW else EventOutcome()

            context.session_state.pop(PUSH_EXPLANATION_STEP_KEY, None)
            if choice == "Enable notifications":
                view.go_to("push_notifications")
                return EventOutcome.pending(
                    event_updates={PUSH_EVENT_ID: {"outcome": "interrupted", "awaiting": "enable"}},
                    flow=PROFILE_ANALYSIS_FLOW, node=PUSH_NODE, status="paused", continue_flow=True,
                )
            if choice == "Show me Manage Goals":
                view.go_to("manage_goals")
                return EventOutcome.pending(
                    flow=PROFILE_ANALYSIS_FLOW, node=PUSH_NODE, status="paused", continue_flow=True,
                )
            view.typing_indicator()
            view.say("Ciao.")
            view.assistant_leave()
            return EventOutcome.complete(flow=STANDARD_FLOW, node=READY_NODE, status="completed")

        context.session_state.pop(PUSH_EXPLANATION_STEP_KEY, None)
        return EventOutcome.pending(
            flow=PROFILE_ANALYSIS_FLOW,
            node=PUSH_EXPLANATION_NODE,
            status="active",
            continue_flow=True,
        )


class AnalysisCompleteEvent(AssistantEvent):
    event_id = "analysis_complete"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        choice = view.selected_choice(self.event_id, "Thanks!")
        if choice is None:
            view.say("That's it.")
            view.typing_indicator()
            view.say("You're ready. ✓")
            view.typing_indicator()
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
        self._events = {
            FRIENDS_NODE: CheckFriendsEvent(),
            FRIENDS_EXPLANATION_NODE: FriendlistExplanationStepEvent(),
            GOALS_NODE: CheckGoalsEvent(),
            GOALS_EXPLANATION_NODE: GoalExplanationStepEvent(),
            PUSH_NODE: CheckPushEvent(),
            PUSH_EXPLANATION_NODE: NotificationExplanationStepEvent(),
            ANALYSIS_COMPLETE_NODE: AnalysisCompleteEvent(),
        }

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        return self._events.get(context.state.node or FRIENDS_NODE, self._events[FRIENDS_NODE]).render(context, view)


class TourEvent(AssistantEvent):
    event_id = "tour"
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        choice = view.selected_choice(self.event_id, "Got it")
        if choice is None:
            view.say("Sure.")
            view.typing_indicator()
            view.say("Dogether is simple.")
            view.typing_indicator()
            view.say("Pick something worth doing.")
            view.typing_indicator()
            view.say("Bring someone along.")
            view.typing_indicator()
            view.say("Keep each other moving.")
            view.typing_indicator()
            view.say("That's basically it.")
            view.typing_indicator()
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

    def initial_event(self) -> AssistantEvent:
        """Return onboarding's entry scene after the director selects this flow."""
        return self._welcome

    def next_event(self, context: AssistantContext) -> AssistantEvent | None:
        state = context.state
        if state.status == "paused" and state.flow not in (None, STANDARD_FLOW) and context.previous_page_key != "help":
            return self._resume
        if state.flow == ONBOARDING_FLOW:
            return self._welcome
        if state.flow == PROFILE_ANALYSIS_FLOW:
            return self._profile_analysis
        if state.flow == TOUR_FLOW:
            return self._tour
        return None
