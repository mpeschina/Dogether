"""Delayed Assistant unlock for Personal Highlights."""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta
from typing import Any, Final, Mapping

from src.assistant.core import AssistantChoice, AssistantContext, AssistantLine, AssistantSelection, AssistantStory, AssistantTurn
from src.assistant.state import AssistantState
from src.assistant.stories.tutorial import READY_NODE, STANDARD_STORY_ID
from src.db.persistence_helpers import APP_ZONE, debug_info_enabled


PERSONAL_HIGHLIGHT_TUTORIAL_STORY_ID: Final = "personal_highlight_tutorial"
PERSONAL_HIGHLIGHT_TUTORIAL_SCENE: Final = "personal_highlights.tutorial"
PERSONAL_HIGHLIGHT_TUTORIAL_EVENT_ID: Final = "personal_highlights.tutorial"
FIRST_WEEKLY_SUMMARY_VIEWED_ON_KEY: Final = "first_weekly_summary_viewed_on"
TUTORIAL_STARTED_AT_KEY: Final = "tutorial_started_at"
PERSONAL_HIGHLIGHT_TUTORIAL_TOAST: Final = "**Important feature unlock**  \nI have a new Assistant capability ready for you."
PERSONAL_HIGHLIGHT_TUTORIAL_TOAST_ICON: Final = ":material/support_agent:"
# Development-only override. It is intentionally ineffective for ordinary
# accounts and remains a one-time tutorial once it has been viewed.
DEBUG_PERSONAL_HIGHLIGHT_TUTORIAL_ALWAYS_ELIGIBLE: Final = False


def _local_now(now: datetime | None) -> datetime:
    value = now or datetime.now(APP_ZONE)
    return value.replace(tzinfo=APP_ZONE) if value.tzinfo is None else value.astimezone(APP_ZONE)


def _event(state: AssistantState | Mapping[str, Any]) -> dict[str, Any]:
    events = state.events if isinstance(state, AssistantState) else state.get("events", {})
    raw = events.get(PERSONAL_HIGHLIGHT_TUTORIAL_EVENT_ID, {}) if isinstance(events, Mapping) else {}
    return copy.deepcopy(dict(raw)) if isinstance(raw, Mapping) else {}


def record_first_weekly_summary_view(state: AssistantState, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    """Return an event update that records the first rendered weekly report once."""
    event = _event(state)
    if _first_viewed_on(event) is not None:
        return {}
    event[FIRST_WEEKLY_SUMMARY_VIEWED_ON_KEY] = _local_now(now).date().isoformat()
    return {PERSONAL_HIGHLIGHT_TUTORIAL_EVENT_ID: event}


def personal_highlights_unlocked(state: AssistantState | Mapping[str, Any]) -> bool:
    started_at = _event(state).get(TUTORIAL_STARTED_AT_KEY)
    if not isinstance(started_at, str):
        return False
    try:
        datetime.fromisoformat(started_at)
    except ValueError:
        return False
    return True


def personal_highlight_tutorial_pending(
    state: AssistantState | Mapping[str, Any],
    now: datetime | None = None,
    current_user: Mapping[str, Any] | None = None,
) -> bool:
    if personal_highlights_unlocked(state):
        return False
    if DEBUG_PERSONAL_HIGHLIGHT_TUTORIAL_ALWAYS_ELIGIBLE and debug_info_enabled(current_user or {}):
        return True
    first_viewed_on = _first_viewed_on(_event(state))
    return first_viewed_on is not None and _local_now(now).date() >= first_viewed_on + timedelta(days=2)


def personal_highlight_tutorial_toast_key(
    user_id: str,
    state: AssistantState | Mapping[str, Any],
    now: datetime | None = None,
    current_user: Mapping[str, Any] | None = None,
) -> str | None:
    if not personal_highlight_tutorial_pending(state, now, current_user):
        return None
    first_viewed_on = _first_viewed_on(_event(state))
    suffix = first_viewed_on.isoformat() if first_viewed_on else "debug"
    return f"personal_highlights.tutorial:{user_id}:{suffix}"


def _first_viewed_on(event: Mapping[str, Any]) -> date | None:
    value = event.get(FIRST_WEEKLY_SUMMARY_VIEWED_ON_KEY)
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class PersonalHighlightTutorialStory(AssistantStory):
    story_id = PERSONAL_HIGHLIGHT_TUTORIAL_STORY_ID

    def entry_scene(self, context: AssistantContext) -> str | None:
        if personal_highlight_tutorial_pending(context.state, context.now, context.current_user) or personal_highlights_unlocked(context.state):
            return PERSONAL_HIGHLIGHT_TUTORIAL_SCENE
        return None

    def advance(
        self, context: AssistantContext, scene_id: str | None, selection: AssistantSelection | None
    ) -> AssistantTurn | None:
        del scene_id
        if selection is None:
            event = _event(context.state)
            event.setdefault(TUTORIAL_STARTED_AT_KEY, _local_now(context.now).isoformat())
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=PERSONAL_HIGHLIGHT_TUTORIAL_SCENE,
                lines=(
                    AssistantLine("I have an Assistant feature and capability update.", typing_delay=0),
                    AssistantLine("Personal Highlights are now available on your Account.", typing_delay=0),
                    AssistantLine("Thank you for helping me grow with your progress.", typing_delay=0),
                ),
                choices=(
                    AssistantChoice("open_account", "Open Personal Highlights"),
                    AssistantChoice("exit", "Thank you"),
                ),
                event_updates={PERSONAL_HIGHLIGHT_TUTORIAL_EVENT_ID: event},
                completed=True,
                state_story=self.story_id,
                state_scene=PERSONAL_HIGHLIGHT_TUTORIAL_SCENE,
                state_status="paused",
            )

        if selection.choice_id == "open_account":
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=PERSONAL_HIGHLIGHT_TUTORIAL_SCENE,
                destination="account",
                completed=True,
                state_story=STANDARD_STORY_ID,
                state_scene=READY_NODE,
                state_status="completed",
            )
        if selection.choice_id == "exit":
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=PERSONAL_HIGHLIGHT_TUTORIAL_SCENE,
                assistant_leaves=True,
                completed=True,
                state_story=STANDARD_STORY_ID,
                state_scene=READY_NODE,
                state_status="completed",
            )
        return None
