"""Session-only debug runner for explicitly exercising Assistant flows."""
from __future__ import annotations

from dataclasses import replace
from typing import Final

from src.assistant.core import (
    AssistantContext,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
)
from src.assistant.story_session import story_session
from src.assistant.stories.triggered.terms_and_conditions import (
    ACTIVE_SCENES as TERMS_ACTIVE_SCENES,
    INTRO_SCENE as TERMS_INTRO_SCENE,
    TermsAndConditionsStory,
)


DEBUG_STORY_ID: Final = "debug"
DEBUG_FLOW_SCENE_KEY: Final = "scene"


class DebugFlowStory(AssistantStory):
    """Repeat a selected flow without changing durable Assistant state."""

    story_id = DEBUG_STORY_ID

    def __init__(self) -> None:
        self._flow = TermsAndConditionsStory()

    def entry_scene(self, context: AssistantContext) -> str:
        scene = story_session(context.session_state, self.story_id).get(
            DEBUG_FLOW_SCENE_KEY
        )
        return scene if isinstance(scene, str) and scene in TERMS_ACTIVE_SCENES else TERMS_INTRO_SCENE

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        scene_id = scene_id or self.entry_scene(context)
        turn = self._flow.advance(context, scene_id, selection)
        session = story_session(context.session_state, self.story_id)
        if turn.completed:
            session.clear()
        else:
            session.set(DEBUG_FLOW_SCENE_KEY, turn.scene_id)
        return replace(
            turn,
            story_id=self.story_id,
            completed=False,
            state_story=None,
            state_scene=None,
            state_status=None,
            execution_outcome=None,
        )
