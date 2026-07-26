from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping


ASSISTANT_STATE_SCHEMA_VERSION = 1


class AssistantMode(str, Enum):
    NORMAL = "normal"
    SPECIAL = "special"


class AssistantCategory(str, Enum):
    STANDARD = "standard"
    TUTORIAL = "tutorial"
    CHEER_UP = "cheer_up"
    JOKE = "joke"
    NARRATIVE = "narrative"


@dataclass(frozen=True)
class AssistantState:
    schema_version: int = ASSISTANT_STATE_SCHEMA_VERSION
    mode: AssistantMode = AssistantMode.NORMAL
    sequences: dict[str, int] = field(default_factory=dict)
    knowledge: dict[str, bool] = field(default_factory=dict)
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    # The guided-event engine stores its resume point, rather than a rendered
    # transcript.  The older generic fields remain for backwards-compatible
    # prototype stories and future event metadata.
    flow: str | None = None
    node: str | None = None
    status: str = "new"

    @classmethod
    def from_profile(cls, profile: Mapping[str, Any]) -> "AssistantState":
        return cls.from_value(profile.get("assistant_state"))

    @classmethod
    def from_value(cls, value: Any) -> "AssistantState":
        if not isinstance(value, Mapping):
            return cls()

        try:
            mode = AssistantMode(str(value.get("mode", AssistantMode.NORMAL.value)))
        except ValueError:
            mode = AssistantMode.NORMAL

        sequences: dict[str, int] = {}
        raw_sequences = value.get("sequences")
        if isinstance(raw_sequences, Mapping):
            for key, position in raw_sequences.items():
                if not isinstance(key, str) or isinstance(position, bool):
                    continue
                try:
                    sequences[key] = max(0, int(position))
                except (TypeError, ValueError):
                    continue

        knowledge: dict[str, bool] = {}
        raw_knowledge = value.get("knowledge")
        if isinstance(raw_knowledge, Mapping):
            knowledge = {
                key: enabled
                for key, enabled in raw_knowledge.items()
                if isinstance(key, str) and isinstance(enabled, bool)
            }

        events: dict[str, dict[str, Any]] = {}
        raw_events = value.get("events")
        if isinstance(raw_events, Mapping):
            events = {
                key: copy.deepcopy(dict(event_state))
                for key, event_state in raw_events.items()
                if isinstance(key, str) and isinstance(event_state, Mapping)
            }

        flow = value.get("flow")
        flow = flow if isinstance(flow, str) and flow else None
        node = value.get("node")
        node = node if isinstance(node, str) and node else None
        status = value.get("status", "new")
        status = status if isinstance(status, str) and status else "new"

        return cls(
            mode=mode,
            sequences=sequences,
            knowledge=knowledge,
            events=events,
            flow=flow,
            node=node,
            status=status,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ASSISTANT_STATE_SCHEMA_VERSION,
            "mode": self.mode.value,
            "sequences": copy.deepcopy(self.sequences),
            "knowledge": copy.deepcopy(self.knowledge),
            "events": copy.deepcopy(self.events),
            "flow": self.flow,
            "node": self.node,
            "status": self.status,
        }

    def with_mode(self, mode: AssistantMode) -> "AssistantState":
        return replace(self, mode=mode)

    @classmethod
    def reset(cls) -> "AssistantState":
        return cls()
