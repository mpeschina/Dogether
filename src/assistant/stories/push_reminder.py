"""A focused, resumable story for the optional push-permission prompt."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.assistant.core import AssistantContext, AssistantEvent, AssistantView, EventOutcome
from src.assistant.state import AssistantCategory
from src.assistant.stories.standard import PUSH_PROMPT_EVENT_ID, STANDARD_PUSH_FLOW, STANDARD_PUSH_NODE
from src.assistant.stories.tutorial import READY_NODE, STANDARD_FLOW


class PushReminderEvent(AssistantEvent):
    event_id = PUSH_PROMPT_EVENT_ID
    category = AssistantCategory.TUTORIAL

    def render(self, context: AssistantContext, view: AssistantView) -> EventOutcome:
        prompt = dict(context.state.events.get(self.event_id, {}))
        if context.state.flow == STANDARD_PUSH_FLOW and context.user_state.get("push_enabled", False):
            view.say("Perfect. Notifications are on. ✓")
            prompt.update({"active": False, "awaiting": False})
            return EventOutcome.complete(
                event_updates={self.event_id: prompt},
                flow=STANDARD_FLOW,
                node=READY_NODE,
                status="completed",
            )

        options = ("Yes, please", "Not now")
        choice = view.selected_choice(self.event_id, *options)
        if choice is None:
            view.say("Tiny suggestion.")
            view.typing_indicator(1.0)
            view.say("Want reminders for your goals?")
            choice = view.choices(self.event_id, "", *options)
            if choice is None:
                prompt.update(
                    {
                        "active": True,
                        "awaiting": False,
                        "shown_count": _count(prompt.get("shown_count")) + (not bool(prompt.get("active"))),
                        "last_shown_at": _now_iso(context),
                    }
                )
                return EventOutcome.pending(event_updates={self.event_id: prompt})

        if not prompt.get("active"):
            prompt["shown_count"] = _count(prompt.get("shown_count")) + 1
            prompt["last_shown_at"] = _now_iso(context)
        prompt["active"] = False
        if choice == "Yes, please":
            view.go_to("push_notifications")
            prompt["awaiting"] = True
            return EventOutcome.pending(
                event_updates={self.event_id: prompt},
                flow=STANDARD_PUSH_FLOW,
                node=STANDARD_PUSH_NODE,
                status="paused",
                continue_flow=True,
            )

        prompt["awaiting"] = False
        prompt["dismissed_count"] = _count(prompt.get("dismissed_count")) + 1
        prompt["last_dismissed_at"] = _now_iso(context)
        prompt["dismissed_at_completed_goal_count"] = _count(context.user_state.get("completed_goal_count"))
        return EventOutcome.complete(
            event_updates={self.event_id: prompt},
            flow=STANDARD_FLOW,
            node=READY_NODE,
            status="completed",
        )


class PushReminderStory:
    story_id = "push_reminder"

    def __init__(self) -> None:
        self._event = PushReminderEvent()

    def next_event(self, context: AssistantContext) -> AssistantEvent:
        return self._event


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _now_iso(context: AssistantContext) -> str:
    now = context.now or datetime.now(timezone.utc)
    return now.isoformat()
