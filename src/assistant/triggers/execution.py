"""Persistent execution accounting for Assistant story triggers."""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timezone

from src.assistant.core import StoryExecutionOutcome
from src.assistant.state import (
    AssistantState,
    StoryActivityState,
    StoryExecutionState,
)
from src.assistant.triggers.models import TriggeredAssistantStory


class TriggerStoryExecutionTracker:
    """Apply start, outcome, activity, and event-consumption updates."""

    def record_start(
        self,
        state: AssistantState,
        story: TriggeredAssistantStory,
        now: datetime,
    ) -> AssistantState:
        now = _normalise_datetime(now)
        executions = copy.deepcopy(state.story_executions)
        previous = executions.get(story.story_id, StoryExecutionState())
        executions[story.story_id] = replace(
            previous,
            starts=previous.starts + 1,
            last_started_at=now.isoformat(),
            pending_event_id=story.trigger_policy.event_id,
        )
        updated = replace(state, story_executions=executions)
        updated = self.record_global_start(
            updated,
            story.story_id,
            story.trigger_policy.importance.name.lower(),
            now,
        )
        if (
            story.trigger_policy.event_id
            and story.trigger_policy.consume_trigger_on == "start"
        ):
            updated = self._consume_trigger_event(
                updated, story.trigger_policy.event_id, story.story_id, now
            )
        return updated

    def record_outcome(
        self,
        state: AssistantState,
        story: TriggeredAssistantStory,
        outcome: StoryExecutionOutcome,
        now: datetime,
    ) -> AssistantState:
        now = _normalise_datetime(now)
        executions = copy.deepcopy(state.story_executions)
        previous = executions.get(story.story_id, StoryExecutionState())
        if outcome == "completed":
            executions[story.story_id] = replace(
                previous,
                completions=previous.completions + 1,
                last_completed_at=now.isoformat(),
                pending_event_id=None,
            )
        else:
            executions[story.story_id] = replace(
                previous,
                last_dismissed_at=now.isoformat(),
            )
        updated = replace(state, story_executions=executions)
        if (
            outcome == "completed"
            and previous.pending_event_id
            and story.trigger_policy.consume_trigger_on == "completion"
        ):
            updated = self._consume_trigger_event(
                updated, previous.pending_event_id, story.story_id, now
            )
        return updated

    @staticmethod
    def record_global_start(
        state: AssistantState,
        story_id: str,
        story_type: str,
        now: datetime,
    ) -> AssistantState:
        now = _normalise_datetime(now)
        activity = state.story_activity
        return replace(
            state,
            story_activity=StoryActivityState(
                last_story_id=story_id,
                last_story_type=story_type,
                last_story_started_at=now.isoformat(),
                last_fun_started_at=(
                    now.isoformat()
                    if story_type == "fun"
                    else activity.last_fun_started_at
                ),
                last_important_started_at=(
                    now.isoformat()
                    if story_type == "important"
                    else activity.last_important_started_at
                ),
            ),
        )

    @staticmethod
    def _consume_trigger_event(
        state: AssistantState,
        event_id: str,
        story_id: str,
        now: datetime,
    ) -> AssistantState:
        events = copy.deepcopy(state.events)
        event = dict(events.get(event_id, {}))
        event.update({"consumed_at": now.isoformat(), "consumed_by": story_id})
        events[event_id] = event
        return replace(state, events=events)


def _normalise_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
