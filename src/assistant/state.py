from __future__ import annotations

import copy
from collections.abc import MutableMapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


ASSISTANT_STATE_SCHEMA_VERSION = 4
# Session-only, authoritative story state.  It retains the active story,
# scene, status, and events so an unfinished flow can resume; it deliberately
# does not contain the UI's buttons or input configuration.
TRANSIENT_ASSISTANT_STATE_SESSION_KEY = "assistant.transient_state"
STAR_AWARDS_EVENT_ID = "stars.story_awards"
WEEKLY_STAR_EVENT_ID = "stars.weekly"


class AssistantMode(str, Enum):
    NORMAL = "normal"
    SPECIAL = "special"


@dataclass(frozen=True)
class StoryExecutionState:
    starts: int = 0
    completions: int = 0
    last_started_at: str | None = None
    last_completed_at: str | None = None
    last_dismissed_at: str | None = None
    pending_event_id: str | None = None

    @classmethod
    def from_value(cls, value: Any) -> "StoryExecutionState":
        if not isinstance(value, Mapping):
            return cls()
        pending = value.get("pending_trigger")
        legacy_pending_event_id = (
            pending.get("event_id") if isinstance(pending, Mapping) else None
        )
        return cls(
            starts=_non_negative_int(value.get("starts")),
            completions=_non_negative_int(value.get("completions")),
            last_started_at=_optional_datetime_string(
                value.get("last_started_at")
            ),
            last_completed_at=_optional_datetime_string(
                value.get("last_completed_at")
            ),
            last_dismissed_at=_optional_datetime_string(
                value.get("last_dismissed_at")
            ),
            pending_event_id=_optional_string(value.get("pending_event_id"))
            or _optional_string(legacy_pending_event_id),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "starts": self.starts,
            "completions": self.completions,
            "last_started_at": self.last_started_at,
            "last_completed_at": self.last_completed_at,
            "last_dismissed_at": self.last_dismissed_at,
            "pending_event_id": self.pending_event_id,
        }


@dataclass(frozen=True)
class StoryActivityState:
    last_story_id: str | None = None
    last_story_type: str | None = None
    last_story_started_at: str | None = None
    last_fun_started_at: str | None = None
    last_important_started_at: str | None = None

    @classmethod
    def from_value(cls, value: Any) -> "StoryActivityState":
        if not isinstance(value, Mapping):
            return cls()
        return cls(
            last_story_id=_optional_string(value.get("last_story_id")),
            last_story_type=_optional_string(value.get("last_story_type")),
            last_story_started_at=_optional_datetime_string(
                value.get("last_story_started_at")
            ),
            last_fun_started_at=_optional_datetime_string(
                value.get("last_fun_started_at")
            ),
            last_important_started_at=_optional_datetime_string(
                value.get("last_important_started_at")
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_story_id": self.last_story_id,
            "last_story_type": self.last_story_type,
            "last_story_started_at": self.last_story_started_at,
            "last_fun_started_at": self.last_fun_started_at,
            "last_important_started_at": self.last_important_started_at,
        }


@dataclass(frozen=True)
class AssistantState:
    schema_version: int = ASSISTANT_STATE_SCHEMA_VERSION
    mode: AssistantMode = AssistantMode.NORMAL
    sequences: dict[str, int] = field(default_factory=dict)
    knowledge: dict[str, bool] = field(default_factory=dict)
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    stars: int = 0
    story: str | None = None
    scene: str | None = None
    status: str = "new"
    story_executions: dict[str, StoryExecutionState] = field(default_factory=dict)
    story_activity: StoryActivityState = field(default_factory=StoryActivityState)

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
        stars = _non_negative_int(value.get("stars"))
        version = _non_negative_int(value.get("schema_version"))

        if version < 2:
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
        story_executions = _normalise_story_executions(value.get("story_executions"))
        story_activity = StoryActivityState.from_value(value.get("story_activity"))
        return cls(
            mode=mode,
            sequences=sequences,
            knowledge=knowledge,
            events=events,
            stars=stars,
            story=story,
            scene=scene,
            status=status,
            story_executions=story_executions,
            story_activity=story_activity,
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
            "stars": self.stars,
            "story": self.story,
            "scene": self.scene,
            "status": self.status,
            "story_executions": {
                story_id: execution.to_dict()
                for story_id, execution in self.story_executions.items()
            },
            "story_activity": self.story_activity.to_dict(),
        }

    def with_mode(self, mode: AssistantMode) -> "AssistantState":
        return replace(self, mode=mode, story=None, scene=None, status="new")

    @classmethod
    def reset(cls) -> "AssistantState":
        return cls()


def grant_stars(state: AssistantState, amount: int = 1) -> AssistantState:
    """Return Assistant state with a non-negative STAR grant applied."""
    return replace(state, stars=state.stars + max(0, int(amount)))


def claim_story_star(state: AssistantState, award_id: str) -> tuple[AssistantState, bool]:
    """Claim a configured story award exactly once for this Assistant state."""
    award_id = str(award_id).strip()
    if not award_id:
        raise ValueError("STAR award IDs must be non-empty.")
    events = copy.deepcopy(state.events)
    award_state = events.get(STAR_AWARDS_EVENT_ID, {})
    claimed = set(award_state.get("claimed", [])) if isinstance(award_state, Mapping) else set()
    if award_id in claimed:
        return state, False
    claimed.add(award_id)
    events[STAR_AWARDS_EVENT_ID] = {"claimed": sorted(claimed)}
    return replace(state, events=events, stars=state.stars + 1), True


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


def _normalise_story_executions(value: Any) -> dict[str, StoryExecutionState]:
    if not isinstance(value, Mapping):
        return {}
    return {
        story_id: StoryExecutionState.from_value(execution)
        for story_id, execution in value.items()
        if isinstance(story_id, str) and story_id and isinstance(execution, Mapping)
    }


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_datetime_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
