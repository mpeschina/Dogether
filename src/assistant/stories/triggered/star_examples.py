"""Interactive production examples for the trigger-based story framework."""
from __future__ import annotations

from datetime import timedelta
from typing import Final

from src.assistant.core import (
    AssistantChoice,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantTurn,
)
from src.assistant.stories.tutorial import READY_NODE, STANDARD_STORY_ID
from src.assistant.triggers import (
    StoryImportance,
    StoryTriggerPolicy,
    TriggeredAssistantStory,
)


IMPORTANT_STAR_STORY_ID: Final = "trigger_example.star_important"
INFORMATIONAL_STAR_STORY_ID: Final = "trigger_example.star_informational"
FUN_STAR_STORY_ID: Final = "trigger_example.star_fun"
STAR_TRIGGER_SCENE: Final = "star_threshold"
STAR_DETAILS_SCENE: Final = "star_threshold.details"
TRIGGER_EXAMPLE_DISCLAIMER: Final = "This is a testcase"

DETAILS_CHOICE_ID: Final = "details"
FINISH_CHOICE_ID: Final = "finish"


class _StarTriggerStory(TriggeredAssistantStory):
    """A compact two-step conversation shared by the STAR trigger examples."""

    message = ""
    detail_message = ""
    closing_message = ""

    def is_triggered(self, context: AssistantContext) -> bool:
        return context.state.stars > 5

    def entry_scene(self, context: AssistantContext) -> str:
        del context
        return STAR_TRIGGER_SCENE

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        del context
        scene_id = scene_id or STAR_TRIGGER_SCENE
        if scene_id == STAR_DETAILS_SCENE:
            return self._details(selection)
        return self._intro(selection)

    def _intro(self, selection: AssistantSelection | None) -> AssistantTurn:
        choice_id = _selected_choice(selection, STAR_TRIGGER_SCENE)
        if choice_id == DETAILS_CHOICE_ID:
            return self._details(None)
        if choice_id == FINISH_CHOICE_ID:
            return self._complete()
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=STAR_TRIGGER_SCENE,
            lines=(AssistantLine(self.message),),
            statuses=(TRIGGER_EXAMPLE_DISCLAIMER,),
            keep_statuses_in_history=True,
            choices=(
                AssistantChoice(DETAILS_CHOICE_ID, "Tell me more"),
                AssistantChoice(FINISH_CHOICE_ID, "Got it"),
            ),
            state_story=self.story_id,
            state_scene=STAR_TRIGGER_SCENE,
            state_status="active",
        )

    def _details(self, selection: AssistantSelection | None) -> AssistantTurn:
        choice_id = _selected_choice(selection, STAR_DETAILS_SCENE)
        if choice_id == FINISH_CHOICE_ID:
            return self._complete()
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=STAR_DETAILS_SCENE,
            lines=(AssistantLine(self.detail_message),),
            statuses=("Your STAR progress is saved and ready for the next goal.",),
            choices=(AssistantChoice(FINISH_CHOICE_ID, "Continue"),),
            state_story=self.story_id,
            state_scene=STAR_DETAILS_SCENE,
            state_status="active",
        )

    def _complete(self) -> AssistantTurn:
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=STAR_DETAILS_SCENE,
            lines=(AssistantLine(self.closing_message),),
            completed=True,
            state_story=STANDARD_STORY_ID,
            state_scene=READY_NODE,
            state_status="completed",
            execution_outcome="completed",
        )


def _selected_choice(
    selection: AssistantSelection | None, scene_id: str
) -> str | None:
    if selection is None or selection.scene_id != scene_id:
        return None
    if selection.choice_id not in {DETAILS_CHOICE_ID, FINISH_CHOICE_ID}:
        return None
    return selection.choice_id


class ImportantStarTriggerStory(_StarTriggerStory):
    story_id = IMPORTANT_STAR_STORY_ID
    message = "Your STAR collection just became impossible to ignore."
    detail_message = "You have passed the first STAR milestone. Keep choosing goals that matter to you."
    closing_message = "That milestone is yours. Let’s keep the momentum going."
    trigger_policy = StoryTriggerPolicy(
        importance=StoryImportance.IMPORTANT,
        priority=30,
        max_repetitions=1,
    )


class InformationalStarTriggerStory(_StarTriggerStory):
    story_id = INFORMATIONAL_STAR_STORY_ID
    message = "More than five STARs opens up new Assistant moments."
    detail_message = "STARs mark the progress you have made. Each one is part of your longer story."
    closing_message = "You are all caught up on this STAR moment."
    trigger_policy = StoryTriggerPolicy(
        importance=StoryImportance.INFORMATIONAL,
        priority=20,
        max_repetitions=1,
    )


class FunStarTriggerStory(_StarTriggerStory):
    story_id = FUN_STAR_STORY_ID
    message = "That is quite a constellation you are building."
    detail_message = "There is no wrong way to build a constellation—one meaningful STAR at a time."
    closing_message = "Constellation noted. Onward."
    trigger_policy = StoryTriggerPolicy(
        importance=StoryImportance.FUN,
        priority=10,
        cooldown=timedelta(days=7),
    )
