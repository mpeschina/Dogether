"""Contracts implemented by trigger-based Assistant stories."""
from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from datetime import timedelta
from enum import IntEnum
from typing import Literal

from src.assistant.core import AssistantContext, AssistantStory


TriggerConsumption = Literal["start", "completion"]


class StoryImportance(IntEnum):
    """Broad ordering and flood-control class for trigger-based stories."""

    FUN = 1
    INFORMATIONAL = 2
    IMPORTANT = 3


@dataclass(frozen=True)
class StoryTriggerPolicy:
    """Static selection limits owned by one trigger-based story."""

    importance: StoryImportance
    priority: int = 0
    max_repetitions: int | None = None
    cooldown: timedelta | None = None
    min_since_any_story: timedelta | None = None
    min_since_triggered_story: timedelta | None = None
    event_id: str | None = None
    consume_trigger_on: TriggerConsumption = "start"

    def __post_init__(self) -> None:
        if self.max_repetitions is not None and self.max_repetitions < 1:
            raise ValueError("Maximum repetitions must be positive or None.")
        if self.consume_trigger_on not in {"start", "completion"}:
            raise ValueError("Trigger consumption must happen on start or completion.")
        for value in (
            self.cooldown,
            self.min_since_any_story,
            self.min_since_triggered_story,
        ):
            if value is not None and value < timedelta(0):
                raise ValueError("Story timing limits cannot be negative.")


class TriggeredAssistantStory(AssistantStory):
    """Assistant story that opts into central trigger-based selection."""

    trigger_policy: StoryTriggerPolicy

    @abstractmethod
    def is_triggered(self, context: AssistantContext) -> bool:
        """Return whether this story's functional trigger is currently active."""
