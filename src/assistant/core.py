from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol

from src.assistant.state import AssistantCategory, AssistantState


class SharedStoryStateStore(Protocol):
    """Extension point for future state shared by narrative participants."""

    def load(self, story_instance_id: str) -> Mapping[str, Any] | None: ...

    def save(self, story_instance_id: str, state: Mapping[str, Any]) -> None: ...


@dataclass(frozen=True)
class AssistantContext:
    user_id: str
    current_user: MutableMapping[str, Any]
    state: AssistantState
    session_state: MutableMapping[str, object]
    current_page_key: str
    previous_page_key: str | None = None
    now: datetime | None = None
    shared_story_state_store: SharedStoryStateStore | None = None


@dataclass(frozen=True)
class EventOutcome:
    completed: bool = False
    advance_sequences: tuple[str, ...] = ()
    knowledge_updates: Mapping[str, bool] = field(default_factory=dict)
    event_updates: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    clear_events: tuple[str, ...] = ()

    @classmethod
    def pending(
        cls,
        *,
        event_updates: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> "EventOutcome":
        return cls(event_updates=event_updates or {})

    @classmethod
    def complete(
        cls,
        *,
        advance_sequence: str | None = None,
        knowledge_updates: Mapping[str, bool] | None = None,
        event_updates: Mapping[str, Mapping[str, Any]] | None = None,
        clear_events: tuple[str, ...] = (),
    ) -> "EventOutcome":
        return cls(
            completed=True,
            advance_sequences=(advance_sequence,) if advance_sequence else (),
            knowledge_updates=knowledge_updates or {},
            event_updates=event_updates or {},
            clear_events=clear_events,
        )


class AssistantView(Protocol):
    input_rendered: bool

    def say(self, message: str) -> None: ...

    def typing_indicator(self, duration_seconds: float) -> None: ...

    def wait(self, duration_seconds: float) -> None: ...

    def assistant_leave(self) -> None: ...

    def status(self, message: str) -> None: ...

    def choices(self, event_id: str, label: str, *options: str) -> str | None: ...

    def send_control(self, event_id: str) -> bool: ...

    def progress(self, value: float, text: str) -> None: ...


class AssistantEvent(Protocol):
    event_id: str
    category: AssistantCategory

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome: ...


class AssistantStory(Protocol):
    story_id: str

    def next_event(self, context: AssistantContext) -> AssistantEvent | None: ...
