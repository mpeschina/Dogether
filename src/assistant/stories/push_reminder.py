"""Declarative optional push-permission reminder."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.assistant.core import (
    AssistantChoice,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
)
from src.assistant.stories.standard import PUSH_PROMPT_EVENT_ID, STANDARD_PUSH_NODE
from src.assistant.stories.tutorial import READY_NODE, STANDARD_STORY_ID


PUSH_REMINDER_STORY_ID = "push_reminder"


class PushReminderStory(AssistantStory):
    story_id = PUSH_REMINDER_STORY_ID

    def entry_scene(self, context: AssistantContext) -> str:
        del context
        return STANDARD_PUSH_NODE

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        del scene_id
        prompt = dict(context.state.events.get(PUSH_PROMPT_EVENT_ID, {}))

        if context.user_state.get("push_enabled", False):
            prompt.update({"active": False, "awaiting": False})
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=STANDARD_PUSH_NODE,
                lines=(AssistantLine("Perfect. Notifications are on. ✓"),),
                event_updates={PUSH_PROMPT_EVENT_ID: prompt},
                state_story=STANDARD_STORY_ID,
                state_scene=READY_NODE,
                state_status="completed",
                completed=True,
            )

        if selection is None:
            was_active = bool(prompt.get("active"))
            prompt.update(
                {
                    "active": True,
                    "awaiting": False,
                    "shown_count": _count(prompt.get("shown_count")) + (not was_active),
                    "last_shown_at": _now_iso(context),
                }
            )
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=STANDARD_PUSH_NODE,
                lines=(
                    AssistantLine("Tiny suggestion."),
                    AssistantLine("Want reminders for your goals?", typing_delay=1.0),
                ),
                choices=(
                    AssistantChoice(id="enable", label="Yes, please"),
                    AssistantChoice(id="dismiss", label="Not now"),
                ),
                event_updates={PUSH_PROMPT_EVENT_ID: prompt},
                state_story=self.story_id,
                state_scene=STANDARD_PUSH_NODE,
                state_status="paused",
            )

        prompt["active"] = False
        if selection.choice_id == "enable":
            prompt["awaiting"] = True
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=STANDARD_PUSH_NODE,
                destination="push_notifications",
                event_updates={PUSH_PROMPT_EVENT_ID: prompt},
                state_story=self.story_id,
                state_scene=STANDARD_PUSH_NODE,
                state_status="paused",
            )

        prompt["awaiting"] = False
        prompt["dismissed_count"] = _count(prompt.get("dismissed_count")) + 1
        prompt["last_dismissed_at"] = _now_iso(context)
        prompt["dismissed_at_completed_goal_count"] = _count(
            context.user_state.get("completed_goal_count")
        )
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=STANDARD_PUSH_NODE,
            event_updates={PUSH_PROMPT_EVENT_ID: prompt},
            state_story=STANDARD_STORY_ID,
            state_scene=READY_NODE,
            state_status="completed",
            completed=True,
        )
def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _now_iso(context: AssistantContext) -> str:
    now = context.now or datetime.now(timezone.utc)
    return now.isoformat()
