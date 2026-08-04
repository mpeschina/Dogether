"""Durable Assistant news for shared-goal invitations."""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime
from collections.abc import MutableMapping
from typing import Any, Mapping

from src.assistant.core import (
    AssistantChoice,
    AssistantCard,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
)
from src.assistant.state import AssistantState, claim_story_star
from src.assistant.story_session import story_session
from src.assistant.stories.tutorial import READY_NODE, STANDARD_STORY_ID


INFORMATION_STORY_ID = "information"
GOAL_INVITATION_EVENT_ID = "information.goal_invitations"
INFORMATION_COMPLETE_KEY = "complete"
GOAL_INVITATION_NOTIFICATIONS_UNLOCKED_KNOWLEDGE_KEY = "information.goal_invitation_notifications_unlocked"
GOAL_INVITATION_STAR_REWARD_GRANTED_KNOWLEDGE_KEY = "information.goal_invitation_star_reward_granted"
GOAL_INVITATION_STAR_AWARD_ID = "information.third_shared_goal"


def pending_goal_invitations(state: AssistantState | Mapping[str, Any]) -> list[dict[str, str]]:
    events = state.events if isinstance(state, AssistantState) else state.get("events", {})
    raw_event = events.get(GOAL_INVITATION_EVENT_ID, {}) if isinstance(events, Mapping) else {}
    raw_items = raw_event.get("invitations", []) if isinstance(raw_event, Mapping) else []
    if not isinstance(raw_items, list):
        return []
    return [
        {
            "goal_id": str(item["goal_id"]),
            "inviter_name": str(item["inviter_name"]),
            "goal_name": str(item.get("goal_name") or "Shared goal"),
            "schedule_class": str(item.get("schedule_class") or "daily"),
            "required_periods": str(item.get("required_periods") or 1),
            "target": str(item.get("target") or 1),
            "friend_participant_count": str(item.get("friend_participant_count") or 0),
        }
        for item in raw_items
        if isinstance(item, Mapping) and item.get("goal_id") and item.get("inviter_name")
    ]


def record_goal_invitation_news(
    persistence: Any,
    recipient_user_ids: list[str],
    *,
    goal: Mapping[str, Any],
    inviter_name: str,
    mark_notifications_unlocked_recipient_ids: list[str] | None = None,
    award_star_recipient_ids: list[str] | None = None,
    now: datetime | None = None,
) -> None:
    """Append one durable Assistant news item for each newly added participant."""
    mark_notifications_unlocked_for = set(mark_notifications_unlocked_recipient_ids or [])
    award_star_for = set(award_star_recipient_ids or [])
    for recipient_user_id in sorted(set(recipient_user_ids)):
        profile = persistence.get_user(recipient_user_id)
        if not profile:
            continue
        state = AssistantState.from_profile(profile)
        events = copy.deepcopy(state.events)
        knowledge = copy.deepcopy(state.knowledge)
        invitations = pending_goal_invitations(state)
        if any(item["goal_id"] == str(goal["id"]) for item in invitations):
            continue
        updated_state = state
        if recipient_user_id in mark_notifications_unlocked_for:
            knowledge[GOAL_INVITATION_NOTIFICATIONS_UNLOCKED_KNOWLEDGE_KEY] = True
        if (
            recipient_user_id in award_star_for
            and not knowledge.get(GOAL_INVITATION_STAR_REWARD_GRANTED_KNOWLEDGE_KEY, False)
        ):
            updated_state, _ = claim_story_star(state, GOAL_INVITATION_STAR_AWARD_ID)
            events = copy.deepcopy(updated_state.events)
            knowledge[GOAL_INVITATION_STAR_REWARD_GRANTED_KNOWLEDGE_KEY] = True
        friend_ids = {friend.get("user_id") for friend in persistence.list_friends(recipient_user_id)}
        participants = set(goal.get("participants", {}))
        friend_participant_count = len((participants - {recipient_user_id}) & friend_ids)
        participant = goal.get("participants", {}).get(recipient_user_id, {})
        invitations.append(
            {
                "goal_id": str(goal["id"]),
                "inviter_name": inviter_name,
                "goal_name": str(goal.get("description") or "Shared goal"),
                "schedule_class": str(goal.get("schedule_class") or "daily"),
                "required_periods": str(goal.get("required_periods") or 1),
                "target": str(participant.get("target") or 1),
                "friend_participant_count": str(friend_participant_count),
            }
        )
        events[GOAL_INVITATION_EVENT_ID] = {"invitations": invitations}
        persistence.save_assistant_state(
            recipient_user_id,
            AssistantState(
                mode=updated_state.mode,
                sequences=updated_state.sequences,
                knowledge=knowledge,
                events=events,
                stars=updated_state.stars,
                story=updated_state.story,
                scene=updated_state.scene,
                status=updated_state.status,
            ).to_dict(),
            now=now,
        )


def clear_goal_invitation_news(persistence: Any, user_id: str, *, now: datetime | None = None) -> None:
    profile = persistence.get_user(user_id)
    if not profile:
        return
    state = AssistantState.from_profile(profile)
    if not pending_goal_invitations(state):
        return
    events = copy.deepcopy(state.events)
    events.pop(GOAL_INVITATION_EVENT_ID, None)
    persistence.save_assistant_state(
        user_id,
        AssistantState(
            mode=state.mode,
            sequences=state.sequences,
            knowledge=state.knowledge,
            events=events,
            stars=state.stars,
            story=state.story,
            scene=state.scene,
            status=state.status,
        ).to_dict(),
        now=now,
    )


class InformationStory(AssistantStory):
    story_id = INFORMATION_STORY_ID

    def entry_scene(self, context: AssistantContext) -> str | None:
        return "goal_invitations" if pending_goal_invitations(context.state) else None

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn | None:
        del scene_id
        invitations = pending_goal_invitations(context.state)
        if not invitations:
            return None
        if selection is not None and selection.choice_id == "acknowledge":
            story_session(context.session_state, self.story_id).set(
                INFORMATION_COMPLETE_KEY, True
            )
            return AssistantTurn(
                story_id=self.story_id,
                scene_id="goal_invitations",
                lines=(AssistantLine("That’s the news. Have fun together!"),),
                assistant_leaves=True,
                clear_events=(GOAL_INVITATION_EVENT_ID,),
                state_story=STANDARD_STORY_ID,
                state_scene=READY_NODE,
                state_status="completed",
                completed=True,
            )

        names = sorted({item["inviter_name"] for item in invitations})
        inviter_text = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
        invitation_text = (
            f"{inviter_text} invited you to a new shared goal."
            if len(invitations) == 1
            else f"{inviter_text} invited you to {len(invitations)} new shared goals."
        )
        unlock_intro = ()
        knowledge_updates = {}
        if not context.state.knowledge.get(GOAL_INVITATION_NOTIFICATIONS_UNLOCKED_KNOWLEDGE_KEY, False):
            unlock_intro = (
                AssistantLine("You have your 3rd shared Goal!"),
                AssistantLine("I got one STAR reward for it, thank you so much."),
                AssistantLine("This enables me to inform you on new goal invites, from now on."),
            )
            knowledge_updates = {GOAL_INVITATION_NOTIFICATIONS_UNLOCKED_KNOWLEDGE_KEY: True}
        return AssistantTurn(
            story_id=self.story_id,
            scene_id="goal_invitations",
            content=(
                AssistantLine("Hello."),
                AssistantLine("I have important news for you.", typing_delay=0.7),
                AssistantLine(invitation_text, typing_delay=2.7),
                *unlock_intro,
                *(_goal_fact_cards(invitations)),
            ),
            choices=(AssistantChoice("acknowledge", "Got it"),),
            knowledge_updates=knowledge_updates,
            # Persist the one-time unlock as soon as its lines are presented;
            # otherwise a new browser session could replay the introduction.
            completed=bool(unlock_intro),
            state_story=self.story_id,
            state_scene="goal_invitations",
            state_status="paused",
        )


def information_completed(session_state: MutableMapping[str, object]) -> bool:
    return story_session(session_state, INFORMATION_STORY_ID).get(INFORMATION_COMPLETE_KEY) is True


def clear_information_session(session_state: MutableMapping[str, object]) -> None:
    story_session(session_state, INFORMATION_STORY_ID).clear()


def _goal_fact_cards(invitations: list[dict[str, str]]) -> tuple[AssistantCard, ...]:
    """Render one compact fact sheet for every newly shared goal."""
    cards = []
    for invitation in invitations:
        rows = [
            ("Class", _schedule_class_label(invitation["schedule_class"])),
            ("Repetitions", _repetition_label(invitation)),
            ("Target", invitation["target"]),
        ]
        friend_count = int(invitation["friend_participant_count"])
        if friend_count > 1:
            rows.append(("Friends already participating", str(friend_count)))
        cards.append(AssistantCard("NEW SHARED GOAL", invitation["goal_name"], "Your new goal at a glance", tuple(rows)))
    return tuple(cards)


def _schedule_class_label(schedule_class: str) -> str:
    return {
        "daily": "Daily",
        "weekly": "Weekly",
        "daily_x_per_week": "Daily with X per week",
        "weekly_x_per_month": "Weekly with X per month",
    }.get(schedule_class, schedule_class.replace("_", " ").title())


def _repetition_label(invitation: Mapping[str, str]) -> str:
    required_periods = max(1, int(invitation["required_periods"]))
    schedule_class = invitation["schedule_class"]
    if schedule_class == "daily_x_per_week":
        return f"{required_periods} times per week"
    if schedule_class == "weekly_x_per_month":
        return f"{required_periods} times per month"
    return "Every day" if schedule_class == "daily" else "Every week"
