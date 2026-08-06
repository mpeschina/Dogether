"""Candidate filtering and ranking for trigger-based Assistant stories."""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from src.assistant.core import AssistantContext
from src.assistant.state import StoryExecutionState
from src.assistant.triggers.models import StoryImportance, TriggeredAssistantStory


OPTIONAL_STORY_STARTED_THIS_VISIT_KEY = "assistant.optional_story_started_this_visit"


@dataclass(frozen=True)
class StorySelectionConfig:
    max_optional_stories_per_visit: int = 1
    fun_story_cooldown: timedelta = timedelta(hours=4)
    important_fun_block: timedelta = timedelta(hours=4)

    def __post_init__(self) -> None:
        if self.max_optional_stories_per_visit < 0:
            raise ValueError("The per-visit story limit cannot be negative.")
        if self.fun_story_cooldown < timedelta(0):
            raise ValueError("The fun-story cooldown cannot be negative.")
        if self.important_fun_block < timedelta(0):
            raise ValueError("The important-story block cannot be negative.")


class TriggerStorySelector:
    """Select one allowed trigger story according to centralized policy."""

    def __init__(
        self,
        stories: Mapping[str, TriggeredAssistantStory],
        *,
        config: StorySelectionConfig = StorySelectionConfig(),
        random_source: Any = random,
    ) -> None:
        self.stories = dict(stories)
        self.config = config
        self.random_source = random_source

    def select(self, context: AssistantContext) -> TriggeredAssistantStory | None:
        candidates: list[TriggeredAssistantStory] = []
        for story in self.stories.values():
            if story.is_triggered(context) and self._allowed(context, story):
                candidates.append(story)
        if not candidates:
            return None

        highest_importance = max(
            candidate.trigger_policy.importance for candidate in candidates
        )
        candidates = [
            candidate
            for candidate in candidates
            if candidate.trigger_policy.importance is highest_importance
        ]
        highest_priority = max(candidate.trigger_policy.priority for candidate in candidates)
        candidates = [
            candidate
            for candidate in candidates
            if candidate.trigger_policy.priority == highest_priority
        ]
        candidates.sort(key=lambda candidate: candidate.story_id)
        if highest_importance is StoryImportance.FUN and len(candidates) > 1:
            return self.random_source.choice(candidates)
        return candidates[0]

    def _allowed(
        self,
        context: AssistantContext,
        story: TriggeredAssistantStory,
    ) -> bool:
        policy = story.trigger_policy
        execution = context.state.story_executions.get(
            story.story_id, StoryExecutionState()
        )
        now = context_now(context)

        if (
            policy.max_repetitions is not None
            and execution.starts >= policy.max_repetitions
        ):
            return False
        if not spacing_satisfied(now, execution.last_started_at, policy.cooldown):
            return False

        activity = context.state.story_activity
        if not spacing_satisfied(
            now, activity.last_story_started_at, policy.min_since_any_story
        ):
            return False
        if not spacing_satisfied(
            now, activity.last_fun_started_at, policy.min_since_fun_story
        ):
            return False

        if policy.importance is StoryImportance.IMPORTANT:
            return True
        visit_count = context.session_state.get(
            OPTIONAL_STORY_STARTED_THIS_VISIT_KEY, 0
        )
        visit_count = max(0, visit_count) if isinstance(visit_count, int) else 1
        if visit_count >= self.config.max_optional_stories_per_visit:
            return False
        if policy.importance is not StoryImportance.FUN:
            return True
        if not spacing_satisfied(
            now,
            activity.last_fun_started_at,
            self.config.fun_story_cooldown,
        ):
            return False
        return spacing_satisfied(
            now,
            activity.last_important_started_at,
            self.config.important_fun_block,
        )


def context_now(context: AssistantContext) -> datetime:
    now = context.now or datetime.now(timezone.utc)
    return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now


def spacing_satisfied(
    now: datetime,
    timestamp: str | None,
    minimum: timedelta | None,
) -> bool:
    if minimum is None or timestamp is None:
        return True
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return now >= parsed + minimum
