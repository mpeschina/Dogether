"""Durable prompt for a completed weekly analysis."""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any, Final, Mapping

from src.assistant.core import (
    AssistantChoice,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
)
from src.assistant.state import AssistantState
from src.assistant.stories.tutorial import READY_NODE, STANDARD_STORY_ID
from src.assistant.stories.weekly_summary import (
    WEEKLY_SUMMARY_STORY_ID,
    WeeklySummaryStory,
    weekly_summary_is_available,
)
from src.assistant.stories.weekly_summary_analysis import _week_start
from src.db.persistence_helpers import APP_ZONE


WEEKLY_SUMMARY_READY_EVENT_ID: Final = "weekly_summary.ready"
WEEKLY_SUMMARY_READY_STORY_ID: Final = "weekly_summary_ready"
WEEKLY_SUMMARY_READY_SCENE: Final = "weekly.ready"
WEEKLY_SUMMARY_READY_TOAST: Final = "**Important Info**  \nI have your analysis of last week ready."
WEEKLY_SUMMARY_READY_TOAST_ICON: Final = ":material/support_agent:"


def weekly_summary_ready_event(state: AssistantState | Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the one well-formed ready event, if it has not been acknowledged."""
    events = state.events if isinstance(state, AssistantState) else state.get("events", {})
    event = events.get(WEEKLY_SUMMARY_READY_EVENT_ID) if isinstance(events, Mapping) else None
    if not isinstance(event, Mapping) or not isinstance(event.get("week_start"), str):
        return None
    try:
        date.fromisoformat(event["week_start"])
    except ValueError:
        return None
    if event.get("acknowledged") is True:
        return None
    return {"week_start": event["week_start"], "acknowledged": False}


def refresh_weekly_summary_ready_event(
    persistence: Any,
    current_user: dict[str, Any],
    user_id: str,
    *,
    now: datetime | None = None,
) -> AssistantState:
    """Create or roll over the single ready event for the latest completed week."""
    current = AssistantState.from_profile(current_user)
    local_now = _local_now(now)
    if not weekly_summary_is_available(current_user, local_now):
        return current

    week_start = _week_start(local_now.date() - timedelta(days=7)).isoformat()
    existing = current.events.get(WEEKLY_SUMMARY_READY_EVENT_ID)
    if isinstance(existing, Mapping) and existing.get("week_start") == week_start:
        return current

    events = copy.deepcopy(current.events)
    events[WEEKLY_SUMMARY_READY_EVENT_ID] = {
        "week_start": week_start,
        "acknowledged": False,
    }
    updated = replace(current, events=events)
    stored = persistence.save_assistant_state(user_id, updated.to_dict(), now=now)
    normalized = AssistantState.from_value(stored)
    current_user["assistant_state"] = normalized.to_dict()
    return normalized


def weekly_summary_ready_toast_key(user_id: str, state: AssistantState) -> str | None:
    """Return the stable per-user key for a pending ready notification."""
    event = weekly_summary_ready_event(state)
    if event is None:
        return None
    return f"weekly_summary.ready:{user_id}:{event['week_start']}"


class WeeklySummaryReadyStory(AssistantStory):
    """Acknowledge a ready analysis before entering the regular summary story."""

    story_id = WEEKLY_SUMMARY_READY_STORY_ID

    def entry_scene(self, context: AssistantContext) -> str | None:
        return WEEKLY_SUMMARY_READY_SCENE if weekly_summary_ready_event(context.state) else None

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn | None:
        del scene_id
        event = weekly_summary_ready_event(context.state)
        if event is None:
            return None
        if selection is None:
            return AssistantTurn(
                self.story_id,
                WEEKLY_SUMMARY_READY_SCENE,
                lines=(AssistantLine("I have your last week’s progress prepared."),),
                choices=(
                    AssistantChoice("show", "Show it to me"),
                    AssistantChoice("decline", "Not interested, but thanks"),
                ),
                state_story=self.story_id,
                state_scene=WEEKLY_SUMMARY_READY_SCENE,
                state_status="active",
            )

        acknowledged = {"week_start": event["week_start"], "acknowledged": True}
        if selection.choice_id == "show":
            start = datetime.fromisoformat(event["week_start"]).date()
            turn = WeeklySummaryStory()._summary_turn(context, start, False)
            return replace(
                turn,
                completed=True,
                event_updates={WEEKLY_SUMMARY_READY_EVENT_ID: acknowledged, **turn.event_updates},
            )
        if selection.choice_id == "decline":
            return AssistantTurn(
                self.story_id,
                WEEKLY_SUMMARY_READY_SCENE,
                lines=(AssistantLine("Of course. Maybe another time."),),
                assistant_leaves=True,
                completed=True,
                event_updates={WEEKLY_SUMMARY_READY_EVENT_ID: acknowledged},
                state_story=STANDARD_STORY_ID,
                state_scene=READY_NODE,
                state_status="completed",
            )
        return None


def _local_now(now: datetime | None) -> datetime:
    value = now or datetime.now(APP_ZONE)
    return value.replace(tzinfo=APP_ZONE) if value.tzinfo is None else value.astimezone(APP_ZONE)
