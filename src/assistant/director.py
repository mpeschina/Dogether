from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from typing import Any, Mapping

from src.assistant.core import (
    AssistantContext,
    AssistantStory,
    AssistantView,
    EventOutcome,
    SharedStoryStateStore,
)
from src.assistant.state import AssistantMode, AssistantState
from src.assistant.stories.standard import PUSH_PROMPT_EVENT_ID, STANDARD_PUSH_FLOW
from src.assistant.stories.tutorial import ONBOARDING_FLOW, PROFILE_ANALYSIS_FLOW, TOUR_FLOW
from src.db.persistence import Persistence


class AssistantDirector:
    def __init__(
        self,
        persistence: Persistence,
        stories: Mapping[AssistantMode | str, AssistantStory],
        *,
        shared_story_state_store: SharedStoryStateStore | None = None,
    ) -> None:
        self.persistence = persistence
        self.stories = dict(stories)
        self.shared_story_state_store = shared_story_state_store

    def render(self, context: AssistantContext, view: AssistantView) -> AssistantState:
        # A user who explicitly dismisses the assistant must never be advanced
        # into another story by a later condition or mode change.
        if context.state.status == "dismissed":
            return context.state

        effective_context = context
        if (
            effective_context.shared_story_state_store is None
            and self.shared_story_state_store is not None
        ):
            effective_context = replace(
                context,
                shared_story_state_store=self.shared_story_state_store,
            )

        event = self._next_event(effective_context)
        if event is None:
            return context.state

        outcome = event.render(effective_context, view)
        updated_state = apply_event_outcome(context.state, outcome)
        if updated_state == context.state:
            return context.state

        stored_state = self.persistence.save_assistant_state(
            context.user_id,
            updated_state.to_dict(),
            now=context.now,
        )
        normalized_state = AssistantState.from_value(stored_state)
        context.current_user["assistant_state"] = normalized_state.to_dict()
        if outcome.continue_flow:
            rerun = getattr(view, "rerun", None)
            if callable(rerun):
                rerun()
        return normalized_state

    def _next_event(self, context: AssistantContext):
        """Choose one intervention. Stories only advance the work selected here."""
        if context.state.mode is AssistantMode.SPECIAL:
            story = self.stories.get(AssistantMode.SPECIAL)
            return story.next_event(context) if story is not None else None

        # 1. Resume a durable flow before looking for anything new.
        if context.state.flow in {ONBOARDING_FLOW, PROFILE_ANALYSIS_FLOW, TOUR_FLOW}:
            tutorial = self.stories.get("tutorial")
            return tutorial.next_event(context) if tutorial is not None else None
        if context.state.flow == STANDARD_PUSH_FLOW:
            push_story = self.stories.get("push_reminder")
            return push_story.next_event(context) if push_story is not None else None

        # 2. Fresh users are deliberately the only users sent into onboarding.
        if self._is_fully_fresh(context.state):
            tutorial = self.stories.get("tutorial")
            initial_event = getattr(tutorial, "initial_event", None)
            return initial_event() if callable(initial_event) else None

        # 3 and 4 are explicit extension points for future guided events.
        issue_event = self._important_issue_event(context)
        if issue_event is not None:
            return issue_event
        tutorial_event = self._unseen_tutorial_event(context)
        if tutorial_event is not None:
            return tutorial_event

        # 5. Optional push prompting follows meaningful use and durable backoff.
        if self._push_prompt_is_eligible(context):
            push_story = self.stories.get("push_reminder")
            return push_story.next_event(context) if push_story is not None else None

        # 6. The standard story is the non-proactive fallback.
        standard = self.stories.get(AssistantMode.NORMAL)
        return standard.next_event(context) if standard is not None else None

    @staticmethod
    def _is_fully_fresh(state: AssistantState) -> bool:
        return (
            state.status == "new"
            and state.flow is None
            and state.node is None
            and not state.events
            and not state.knowledge
            and not state.sequences
        )

    @staticmethod
    def _important_issue_event(context: AssistantContext):
        """Reserved for product-defined urgent conditions."""
        return None

    @staticmethod
    def _unseen_tutorial_event(context: AssistantContext):
        """Reserved for feature-specific tutorial eligibility."""
        return None

    @staticmethod
    def _push_prompt_is_eligible(context: AssistantContext) -> bool:
        if context.user_state.get("push_enabled", False):
            return False
        prompt = context.state.events.get(PUSH_PROMPT_EVENT_ID, {})
        dismissed = _non_negative_int(prompt.get("dismissed_count"))
        if dismissed >= 3 or prompt.get("awaiting"):
            return False

        completed = _non_negative_int(context.user_state.get("completed_goal_count"))
        if dismissed == 0:
            return completed >= 1

        since_dismissal = completed - _non_negative_int(prompt.get("dismissed_at_completed_goal_count"))
        if dismissed == 1:
            return since_dismissal >= 1
        if since_dismissal < 3:
            return False
        dismissed_at = _parse_datetime(prompt.get("last_dismissed_at"))
        if dismissed_at is None:
            return False
        now = context.now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now >= dismissed_at + timedelta(days=30)


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def apply_event_outcome(state: AssistantState, outcome: EventOutcome) -> AssistantState:
    sequences = copy.deepcopy(state.sequences)
    knowledge = copy.deepcopy(state.knowledge)
    events = copy.deepcopy(state.events)

    for sequence_id in outcome.advance_sequences:
        sequences[sequence_id] = sequences.get(sequence_id, 0) + 1
    knowledge.update(outcome.knowledge_updates)
    for event_id, event_state in outcome.event_updates.items():
        events[event_id] = copy.deepcopy(dict(event_state))
    for event_id in outcome.clear_events:
        events.pop(event_id, None)

    return replace(
        state,
        sequences=sequences,
        knowledge=knowledge,
        events=events,
        flow=outcome.flow if outcome.flow is not None else state.flow,
        node=outcome.node if outcome.node is not None else state.node,
        status=outcome.status if outcome.status is not None else state.status,
    )
