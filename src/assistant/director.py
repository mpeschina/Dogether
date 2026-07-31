from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from src.assistant.core import (
    AssistantContext,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
    SharedStoryStateStore,
)
from src.assistant.state import (
    AssistantMode,
    AssistantState,
    clear_transient_assistant_state,
    save_transient_assistant_state,
)
from src.assistant.presentation import ASSISTANT_LEFT_THIS_VISIT_KEY, StreamlitAssistantView
from src.assistant.stories.greetings import GREETINGS_STORY_ID
from src.assistant.stories.information import INFORMATION_STORY_ID, pending_goal_invitations
from src.assistant.stories.night import NIGHT_STORY_ID
from src.assistant.stories.push_reminder import PUSH_REMINDER_STORY_ID
from src.assistant.stories.special_examples import SPECIAL_STORY_ID
from src.assistant.stories.standard import PUSH_PROMPT_EVENT_ID
from src.assistant.stories.weekly_summary import WEEKLY_SUMMARY_STORY_ID
from src.assistant.stories.weekly_summary_ready import (
    WEEKLY_SUMMARY_READY_STORY_ID,
    weekly_summary_ready_event,
)
from src.assistant.stories.tutorial import (
    EXPLANATION_SCENES,
    READY_NODE,
    STANDARD_STORY_ID,
    TUTORIAL_STORY_ID,
)
from src.db.persistence_helpers import APP_ZONE


MAX_AUTOMATIC_TURNS = 24


class AssistantDirector:
    """Advance declarative stories and own every state/persistence boundary."""

    def __init__(
        self,
        persistence,
        stories: Mapping[AssistantMode | str, AssistantStory],
        *,
        shared_story_state_store: SharedStoryStateStore | None = None,
    ) -> None:
        self.persistence = persistence
        self.shared_story_state_store = shared_story_state_store
        self.stories: dict[str, AssistantStory] = {}
        for key, story in stories.items():
            self.stories[str(key)] = story
            self.stories[story.story_id] = story

    def render(
        self, context: AssistantContext, view: StreamlitAssistantView
    ) -> AssistantState:
        if (
            context.state.status == "dismissed"
            or view.waiting_for_input
            or context.session_state.get(ASSISTANT_LEFT_THIS_VISIT_KEY) is True
        ):
            view.finish()
            return context.state

        state = context.state
        # The queued user action to process on this render's first story turn.
        selection: AssistantSelection | None = view.selection
        state_changed = False
        save_durably = False
        greeting_has_played = False

        for _ in range(MAX_AUTOMATIC_TURNS):
            effective_context = self._context_with_state(context, state)
            story = self.story_dispatch(
                effective_context,
                selection,
                skip_greeting=greeting_has_played,
            )
            if story is None:
                break
            scene_id = (
                selection.scene_id
                if selection is not None
                else self._entry_scene(story, effective_context)
            )
            if scene_id is None:
                break

            turn = story.advance(effective_context, scene_id, selection)
            selection = None
            if turn is None:
                break

            view.present(turn)
            greeting_has_played = greeting_has_played or story.story_id == GREETINGS_STORY_ID
            updated_state = apply_turn(state, turn)
            state_changed = state_changed or updated_state != state
            state = updated_state
            save_durably = save_durably or turn.completed

            if turn.destination or turn.has_control or not turn.continue_flow:
                break
        else:
            raise RuntimeError("Assistant story exceeded the automatic transition limit.")

        if state_changed:
            state = self._save_state(context, state, durably=save_durably)

        view.finish()
        return state

    def _context_with_state(
        self, context: AssistantContext, state: AssistantState
    ) -> AssistantContext:
        effective = replace(context, state=state)
        if (
            effective.shared_story_state_store is None
            and self.shared_story_state_store is not None
        ):
            effective = replace(
                effective,
                shared_story_state_store=self.shared_story_state_store,
            )
        return effective

    def story_dispatch(
        self,
        context: AssistantContext,
        selection: AssistantSelection | None,
        *,
        skip_greeting: bool = False,
    ) -> AssistantStory | None:
        if selection is not None:
            return self.stories.get(selection.story_id)

        state = context.state
        # high priority interrupt rules
        if self._super_important_issue_story(context) is not None:
            return self._super_important_issue_story(context)
        if state.mode is AssistantMode.SPECIAL:
            return self.stories.get(SPECIAL_STORY_ID)

        # resume and continue rules to dispatch to a currently running story
        if state.story == TUTORIAL_STORY_ID and state.scene not in {None, READY_NODE}:
            return self.stories.get(TUTORIAL_STORY_ID)
        if state.story == PUSH_REMINDER_STORY_ID:
            return self.stories.get(PUSH_REMINDER_STORY_ID)
        if state.story == WEEKLY_SUMMARY_STORY_ID and state.status == "active":
            return self.stories.get(WEEKLY_SUMMARY_STORY_ID)
        if state.story == STANDARD_STORY_ID and state.scene in EXPLANATION_SCENES:
            return self.stories.get(STANDARD_STORY_ID)

        # normal dispatcher
        if self._is_fully_fresh(state):
            return self.stories.get(TUTORIAL_STORY_ID)
        if self._important_issue_story(context) is not None:
            return self._important_issue_story(context)
        if weekly_summary_ready_event(state):
            return self.stories.get(WEEKLY_SUMMARY_READY_STORY_ID)
        if pending_goal_invitations(state):
            return self.stories.get(INFORMATION_STORY_ID)
        if self._unseen_tutorial_story(context) is not None:
            return self._unseen_tutorial_story(context)
        if self._push_prompt_is_eligible(context):
            return self.stories.get(PUSH_REMINDER_STORY_ID)
        if not skip_greeting:
            return self.stories.get(GREETINGS_STORY_ID)
        return self.stories.get(STANDARD_STORY_ID)

    @staticmethod
    def _entry_scene(
        story: AssistantStory, context: AssistantContext
    ) -> str | None:
        return story.entry_scene(context)

    def _save_state(
        self,
        context: AssistantContext,
        state: AssistantState,
        *,
        durably: bool,
    ) -> AssistantState:
        if not durably:
            save_transient_assistant_state(context.session_state, context.user_id, state)
            return state

        stored = self.persistence.save_assistant_state(
            context.user_id,
            state.to_dict(),
            now=context.now,
        )
        normalized = AssistantState.from_value(stored)
        context.current_user["assistant_state"] = normalized.to_dict()
        clear_transient_assistant_state(context.session_state, context.user_id)
        return normalized

    @staticmethod
    def _is_fully_fresh(state: AssistantState) -> bool:
        return (
            state.status == "new"
            and state.story is None
            and state.scene is None
        )

    def _super_important_issue_story(self, context: AssistantContext):
            return None

    def _important_issue_story(self, context: AssistantContext):
        # return self.stories.get(NIGHT_STORY_ID) ##### just for debugging this event, keep this line
        now = context.now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if 0 <= now.astimezone(APP_ZONE).hour < 6:
            return self.stories.get(NIGHT_STORY_ID)
        return None

    @staticmethod
    def _unseen_tutorial_story(context: AssistantContext):
        del context
        return None

    @staticmethod
    def _push_prompt_is_eligible(context: AssistantContext) -> bool:
        if context.user_state.get("push_enabled", False):
            return False
        prompt = context.state.events.get(PUSH_PROMPT_EVENT_ID, {})
        dismissed = _non_negative_int(prompt.get("dismissed_count"))
        if dismissed >= 3 or prompt.get("awaiting"):
            return False

        completed = _non_negative_int(
            context.user_state.get("completed_goal_count")
        )
        if dismissed == 0:
            return completed >= 1

        since_dismissal = completed - _non_negative_int(
            prompt.get("dismissed_at_completed_goal_count")
        )
        if dismissed == 1:
            return since_dismissal >= 1
        if since_dismissal < 3:
            return False
        dismissed_at = _parse_datetime(prompt.get("last_dismissed_at"))
        if dismissed_at is None:
            return False
        now = context.now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now >= dismissed_at + timedelta(days=30)


def apply_turn(state: AssistantState, turn: AssistantTurn) -> AssistantState:
    sequences = copy.deepcopy(state.sequences)
    knowledge = copy.deepcopy(state.knowledge)
    events = copy.deepcopy(state.events)

    for sequence_id in turn.advance_sequences:
        sequences[sequence_id] = sequences.get(sequence_id, 0) + 1
    knowledge.update(turn.knowledge_updates)
    for event_id, event_state in turn.event_updates.items():
        events[event_id] = copy.deepcopy(dict(event_state))
    for event_id in turn.clear_events:
        events.pop(event_id, None)

    return replace(
        state,
        sequences=sequences,
        knowledge=knowledge,
        events=events,
        story=turn.state_story if turn.state_story is not None else state.story,
        scene=turn.state_scene if turn.state_scene is not None else state.scene,
        status=turn.state_status if turn.state_status is not None else state.status,
    )


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed

