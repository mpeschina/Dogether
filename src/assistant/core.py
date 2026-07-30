from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Literal, Mapping, Protocol

from src.assistant.state import AssistantState


ControlKind = Literal["choices", "send"]
TranscriptKind = Literal[
    "assistant", "user", "status", "progress", "live_status", "live_progress"
]


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
    user_state: Mapping[str, Any] = field(default_factory=dict)
    create_friend_share_link: Callable[[], str] | None = None


@dataclass(frozen=True)
class AssistantLine:
    """One assistant message and its presentation timing.

    ``text`` is the message content. ``typing_delay`` controls the typing
    indicator shown before it: ``None`` disables it, ``0`` chooses a random
    duration, and a positive value specifies its duration in seconds.
    ``wait_before`` and ``wait_after`` are plain pauses, in seconds, before
    and after the message is presented.
    """

    text: str
    typing_delay: float | None = None
    wait_before: float = 0
    wait_after: float = 0


@dataclass(frozen=True)
class AssistantChoice:
    """A stable transition value and its user-facing button label."""

    id: str
    label: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Assistant choice IDs must be non-empty.")


@dataclass(frozen=True)
class AssistantCard:
    """A compact, data-led card displayed inline in the assistant transcript."""
    title: str
    value: str = ""
    detail: str = ""
    rows: tuple[tuple[str, str], ...] = ()
    progress: float | None = None
    # Each bar is (week start, completion percentage, is selected week).
    weekly_chart: tuple[tuple[date, float, bool], ...] = ()
    # Trusted inline markup for the Recent row of an insight card.
    recent_activity_html: str = ""
    # Optional percentage fills, aligned with ``rows``.
    row_progress: tuple[float | None, ...] = ()


@dataclass(frozen=True)
class AssistantSelection:
    """A queued user control action that directs the next assistant story turn."""
    # the story that displayed the control
    story_id: str
    # the scene where it was displayed
    scene_id: str
    # the selected action/option
    choice_id: str
    # the user-visible choice text (or submitted message)
    label: str
    # the kind of control used
    control_kind: ControlKind = "choices"


@dataclass(frozen=True)
class ProgressEntry:
    value: float
    text: str


@dataclass(frozen=True)
class AssistantTurn:
    """Declarative output plus state changes for one conversation transition."""

    story_id: str  # Story that owns this turn.
    scene_id: str  # Scene that produced this turn.
    lines: tuple[AssistantLine, ...] = ()  # Assistant messages to show.
    cards: tuple[AssistantCard, ...] = ()  # Inline visual result cards.
    # Ordered content for stories whose messages and cards must alternate.
    # Older stories can continue to use ``lines`` and ``cards``.
    content: tuple[AssistantLine | AssistantCard, ...] = ()
    choices: tuple[AssistantChoice, ...] = ()  # Choice buttons to show.
    choice_label: str = ""  # Label above the choices.
    control_kind: ControlKind = "choices"  # Control UI to render.
    send_placeholder: str = "Message the assistant"  # Placeholder for a send control.
    record_selection: bool = True  # Whether to add the choice to history.
    statuses: tuple[str, ...] = ()  # Status messages to show.
    progress: tuple[ProgressEntry, ...] = ()  # Progress indicators to show.
    # Keep statuses in conversation history rather than treating them as live UI feedback.
    keep_statuses_in_history: bool = False
    assistant_leaves: bool = False  # Whether the assistant leaves the chat.
    destination: str | None = None  # Page to open next.
    completed: bool = False  # Whether to save state durably.
    continue_flow: bool = False  # Whether to advance again immediately.
    advance_sequences: tuple[str, ...] = ()  # Sequences to increment.
    knowledge_updates: Mapping[str, bool] = field(default_factory=dict)  # Knowledge to set.
    event_updates: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # Events to save.
    clear_events: tuple[str, ...] = ()  # Events to remove.
    state_story: str | None = None  # Next active story. where the assistant should resume on a later rerun or page return.
    state_scene: str | None = None  # Next active scene. where the assistant should resume on a later rerun or page return.
    state_status: str | None = None  # Next conversation status. the saved lifecycle state, such as active, paused, or completed.

    def __post_init__(self) -> None:
        choice_ids = tuple(choice.id for choice in self.choices)
        if len(choice_ids) != len(set(choice_ids)):
            raise ValueError("Assistant turn choice IDs must be unique.")

    @property
    def has_control(self) -> bool:
        return self.control_kind == "send" or bool(self.choices)


class AssistantStory(ABC):
    """Common interface implemented by every assistant story."""

    story_id: str

    @abstractmethod
    def entry_scene(self, context: AssistantContext) -> str | None:
        """Return the scene where this story should currently begin."""

    @abstractmethod
    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn | None:
        """Produce the next declarative conversation turn."""
