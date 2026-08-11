"""Session-only runner for previewing any Assistant story on debug accounts."""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Final, Mapping

from src.assistant.core import (
    AssistantContext,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
)
from src.assistant.state import AssistantMode, AssistantState
from src.assistant.story_session import story_session
from src.assistant.stories.tutorial import READY_NODE, STANDARD_STORY_ID
from src.assistant.stories.information import (
    GOAL_INVITATION_EVENT_ID,
    INFORMATION_STORY_ID,
)
from src.assistant.stories.personal_highlight_tutorial import (
    PERSONAL_HIGHLIGHT_TUTORIAL_EVENT_ID,
    PERSONAL_HIGHLIGHT_TUTORIAL_STORY_ID,
    FIRST_WEEKLY_SUMMARY_VIEWED_ON_KEY,
)
from src.assistant.stories.triggered.terms_and_conditions import TermsAndConditionsStory
from src.assistant.stories.weekly_summary_ready import (
    WEEKLY_SUMMARY_READY_EVENT_ID,
    WEEKLY_SUMMARY_READY_STORY_ID,
)


DEBUG_STORY_ID: Final = "debug"
DEBUG_FLOW_SCENE_KEY: Final = "scene"
DEBUG_FLOW_STORY_ID_KEY: Final = "story_id"


def debug_story_options() -> dict[str, AssistantStory]:
    """Return every concrete Assistant story that can be previewed."""
    # A local import avoids the package's DebugFlowStory/default_stories cycle.
    from src.assistant.stories import default_stories

    options: dict[str, AssistantStory] = {}
    for story in default_stories().values():
        if story.story_id != DEBUG_STORY_ID:
            options[story.story_id] = story
    return dict(sorted(options.items()))


def select_debug_story(session_state: dict[str, object], story_id: str) -> bool:
    """Start a fresh session-only preview when the story ID is known."""
    if story_id not in debug_story_options():
        return False
    session = story_session(session_state, DEBUG_STORY_ID)
    session.clear()
    session = story_session(session_state, DEBUG_STORY_ID)
    session.set(DEBUG_FLOW_STORY_ID_KEY, story_id)
    return True


def debug_story_label(story_id: str) -> str:
    """Turn a stable story ID into a compact, readable debug-menu label."""
    return story_id.replace(".", " · ").replace("_", " ").title()


class DebugFlowStory(AssistantStory):
    """Run one selected story without retaining its durable effects."""

    story_id = DEBUG_STORY_ID

    def entry_scene(self, context: AssistantContext) -> str | None:
        story = self._selected_story(context)
        if story is None:
            return None
        session = story_session(context.session_state, self.story_id)
        scene = session.get(DEBUG_FLOW_SCENE_KEY)
        if isinstance(scene, str):
            return scene
        return story.entry_scene(self._preview_context(context, story))

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn | None:
        story = self._selected_story(context)
        if story is None:
            return None
        preview_context = self._preview_context(context, story)
        scene_id = scene_id or story.entry_scene(preview_context)
        turn = story.advance(preview_context, scene_id, selection)
        if turn is None:
            return None

        session = story_session(context.session_state, self.story_id)
        if turn.completed and not turn.has_control:
            session.clear()
            return self._finish_preview(turn)
        else:
            session.set(DEBUG_FLOW_SCENE_KEY, turn.scene_id)
        return replace(
            turn,
            story_id=self.story_id,
            completed=False,
            destination=None,
            state_story=None,
            state_scene=None,
            state_status=None,
            execution_outcome=None,
            advance_sequences=(),
            stars_delta=0,
            star_grant_animation=False,
            knowledge_updates={},
            event_updates={},
            clear_events=(),
        )

    @staticmethod
    def _finish_preview(turn: AssistantTurn) -> AssistantTurn:
        """Leave debug mode and open Standard after the selected story ends."""
        return replace(
            turn,
            story_id=DEBUG_STORY_ID,
            assistant_leaves=False,
            completed=True,
            continue_flow=True,
            skip_greeting=True,
            open_standard_menu=True,
            destination=None,
            state_story=STANDARD_STORY_ID,
            state_scene=READY_NODE,
            state_status="completed",
            state_mode=AssistantMode.NORMAL,
            execution_outcome=None,
            advance_sequences=(),
            stars_delta=0,
            star_grant_animation=False,
            knowledge_updates={},
            event_updates={},
            clear_events=(),
        )

    @staticmethod
    def _selected_story(context: AssistantContext) -> AssistantStory | None:
        session = story_session(context.session_state, DEBUG_STORY_ID)
        selected_id = session.get(DEBUG_FLOW_STORY_ID_KEY)
        if isinstance(selected_id, str):
            return debug_story_options().get(selected_id)
        # Retain the original debug-flow behaviour until a story is selected.
        return TermsAndConditionsStory()

    @staticmethod
    def _preview_context(
        context: AssistantContext, story: AssistantStory
    ) -> AssistantContext:
        """Supply harmless fixture events for stories that normally need one."""
        events = copy.deepcopy(context.state.events)
        if story.story_id == INFORMATION_STORY_ID:
            events.setdefault(
                GOAL_INVITATION_EVENT_ID,
                {
                    "invitations": [
                        {
                            "goal_id": "debug-goal",
                            "inviter_name": "Debug teammate",
                            "goal_name": "A shared goal",
                            "schedule_class": "daily",
                            "required_periods": "1",
                            "target": "1",
                            "friend_participant_count": "1",
                        }
                    ]
                },
            )
        elif story.story_id == PERSONAL_HIGHLIGHT_TUTORIAL_STORY_ID:
            events.setdefault(
                PERSONAL_HIGHLIGHT_TUTORIAL_EVENT_ID,
                {
                    FIRST_WEEKLY_SUMMARY_VIEWED_ON_KEY: (
                        _preview_day(context) - timedelta(days=2)
                    ).isoformat()
                },
            )
        elif story.story_id == WEEKLY_SUMMARY_READY_STORY_ID:
            events.setdefault(
                WEEKLY_SUMMARY_READY_EVENT_ID,
                {"week_start": (_preview_day(context) - timedelta(days=7)).isoformat()},
            )
        return replace(context, state=replace(context.state, events=events))


def _preview_day(context: AssistantContext):
    now = context.now
    return now.date() if now is not None else datetime.now().date()
