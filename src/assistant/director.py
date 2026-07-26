from __future__ import annotations

import copy
from dataclasses import replace
from typing import Mapping

from src.assistant.core import (
    AssistantContext,
    AssistantStory,
    AssistantView,
    EventOutcome,
    SharedStoryStateStore,
)
from src.assistant.state import AssistantMode, AssistantState
from src.db.persistence import Persistence


class AssistantDirector:
    def __init__(
        self,
        persistence: Persistence,
        stories: Mapping[AssistantMode, AssistantStory],
        *,
        shared_story_state_store: SharedStoryStateStore | None = None,
    ) -> None:
        self.persistence = persistence
        self.stories = dict(stories)
        self.shared_story_state_store = shared_story_state_store

    def render(self, context: AssistantContext, view: AssistantView) -> AssistantState:
        story = self.stories.get(context.state.mode)
        if story is None:
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

        event = story.next_event(effective_context)
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
        return normalized_state


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
    )
