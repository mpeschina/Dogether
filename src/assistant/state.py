from __future__ import annotations

import copy
from collections.abc import MutableMapping
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping


ASSISTANT_STATE_SCHEMA_VERSION = 2
# Session-only, authoritative story state.  It retains the active story,
# scene, status, and events so an unfinished flow can resume; it deliberately
# does not contain the UI's buttons or input configuration.
TRANSIENT_ASSISTANT_STATE_SESSION_KEY = "assistant.transient_state"


class AssistantMode(str, Enum):
    NORMAL = "normal"
    SPECIAL = "special"


@dataclass(frozen=True)
class AssistantState:
    schema_version: int = ASSISTANT_STATE_SCHEMA_VERSION
    mode: AssistantMode = AssistantMode.NORMAL
    sequences: dict[str, int] = field(default_factory=dict)
    knowledge: dict[str, bool] = field(default_factory=dict)
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    story: str | None = None
    scene: str | None = None
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

        sequences = _normalise_sequences(value.get("sequences"))
        knowledge = _normalise_knowledge(value.get("knowledge"))
        events = _normalise_events(value.get("events"))
        version = _non_negative_int(value.get("schema_version"))

        if version < ASSISTANT_STATE_SCHEMA_VERSION:
            return cls._from_legacy(
                value,
                mode=mode,
                sequences=sequences,
                knowledge=knowledge,
                events=events,
            )

        story = _optional_string(value.get("story"))
        scene = _optional_string(value.get("scene"))
        status = _optional_string(value.get("status")) or "new"
        return cls(
            mode=mode,
            sequences=sequences,
            knowledge=knowledge,
            events=events,
            story=story,
            scene=scene,
            status=status,
        )

    @classmethod
    def _from_legacy(
        cls,
        value: Mapping[str, Any],
        *,
        mode: AssistantMode,
        sequences: dict[str, int],
        knowledge: dict[str, bool],
        events: dict[str, dict[str, Any]],
    ) -> "AssistantState":
        """Keep durable achievements while resetting unfinished v1 conversations."""
        legacy_status = _optional_string(value.get("status")) or "new"
        legacy_flow = _optional_string(value.get("flow"))
        completed = legacy_status in {"completed", "declined", "dismissed"} or legacy_flow == "standard"
        return cls(
            mode=mode,
            sequences=sequences,
            knowledge=knowledge,
            events=events,
            story="standard" if completed and mode is AssistantMode.NORMAL else None,
            scene="ready" if completed and mode is AssistantMode.NORMAL else None,
            status=legacy_status if completed else "new",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ASSISTANT_STATE_SCHEMA_VERSION,
            "mode": self.mode.value,
            "sequences": copy.deepcopy(self.sequences),
            "knowledge": copy.deepcopy(self.knowledge),
            "events": copy.deepcopy(self.events),
            "story": self.story,
            "scene": self.scene,
            "status": self.status,
        }

    def with_mode(self, mode: AssistantMode) -> "AssistantState":
        return replace(self, mode=mode, story=None, scene=None, status="new")

    @classmethod
    def reset(cls) -> "AssistantState":
        return cls()


def transient_assistant_state_for_user(
    session_state: Mapping[str, Any], user_id: str
) -> AssistantState | None:
    value = session_state.get(TRANSIENT_ASSISTANT_STATE_SESSION_KEY)
    if not isinstance(value, Mapping) or value.get("user_id") != user_id:
        return None
    raw_state = value.get("assistant_state")
    if not isinstance(raw_state, Mapping):
        return None
    return AssistantState.from_value(raw_state)


def save_transient_assistant_state(
    session_state: MutableMapping[str, Any], user_id: str, state: AssistantState
) -> None:
    session_state[TRANSIENT_ASSISTANT_STATE_SESSION_KEY] = {
        "user_id": user_id,
        "assistant_state": state.to_dict(),
    }


def clear_transient_assistant_state(
    session_state: MutableMapping[str, Any], user_id: str | None = None
) -> None:
    value = session_state.get(TRANSIENT_ASSISTANT_STATE_SESSION_KEY)
    if user_id is not None and isinstance(value, Mapping) and value.get("user_id") != user_id:
        return
    session_state.pop(TRANSIENT_ASSISTANT_STATE_SESSION_KEY, None)


def _normalise_sequences(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key, position in value.items():
        if not isinstance(key, str) or isinstance(position, bool):
            continue
        try:
            result[key] = max(0, int(position))
        except (TypeError, ValueError):
            continue
    return result


def _normalise_knowledge(value: Any) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: enabled
        for key, enabled in value.items()
        if isinstance(key, str) and isinstance(enabled, bool)
    }


def _normalise_events(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: copy.deepcopy(dict(event_state))
        for key, event_state in value.items()
        if isinstance(key, str) and isinstance(event_state, Mapping)
    }


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
