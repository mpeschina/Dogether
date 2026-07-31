"""The default, user-directed declarative assistant story."""
from __future__ import annotations

from dataclasses import replace
from typing import Final

from src.assistant.core import (
    AssistantChoice,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
)
from src.assistant.stories.smalltalk import SmalltalkStory
from src.assistant.stories.tutorial import (
    EXPLANATION_SCENES,
    FRIENDS_EXPLANATION_NODE,
    FRIENDS_NODE,
    GOALS_EXPLANATION_NODE,
    PROFILE_ANALYSIS_KNOWLEDGE_KEY,
    PUSH_EXPLANATION_NODE,
    READY_NODE,
    STANDARD_STORY_ID,
    TUTORIAL_STORY_ID,
    explanation_turn,
)


STANDARD_MENU_EVENT_ID: Final = "standard.tutorial_menu"
STANDARD_MENU_SCENE: Final = "standard.menu"
STANDARD_HELP_SCENE: Final = "standard.help"
STANDARD_TUTORIAL_FLOW: Final = STANDARD_STORY_ID
STANDARD_PUSH_FLOW: Final = "push_reminder"
STANDARD_PUSH_NODE: Final = "push.offer_enable"
PUSH_PROMPT_EVENT_ID: Final = "standard.push_prompt"

TUTORIAL_OPTIONS: Final = (
    ("friends", "How do I add friends?", "tutorial.friends.seen", FRIENDS_EXPLANATION_NODE),
    ("goals", "How do goals work?", "tutorial.goals.seen", GOALS_EXPLANATION_NODE),
    (
        "notifications",
        "How do notifications work?",
        "tutorial.notifications.seen",
        PUSH_EXPLANATION_NODE,
    ),
    ("progress", "How do I track progress?", "tutorial.progress.seen", None),
)


def standard_menu_turn(
    *,
    smalltalk_choice: AssistantChoice | None,
    lines: tuple[AssistantLine, ...] = (),
    knowledge_updates=None,
) -> AssistantTurn:
    return AssistantTurn(
        story_id=STANDARD_STORY_ID,
        scene_id=STANDARD_MENU_SCENE,
        lines=lines,
        choices=tuple(
            choice
            for choice in (
                AssistantChoice("help", "Help me with the app"),
                smalltalk_choice,
                AssistantChoice("weekly_summary", "Analyse my progress"),
            )
            if choice is not None
        ),
        choice_label="",
        knowledge_updates=knowledge_updates or {},
    )


def standard_help_turn(
    *,
    lines: tuple[AssistantLine, ...] = (),
    knowledge_updates=None,
    profile_analysis_completed: bool = False,
) -> AssistantTurn:
    choices = (
        tuple(
            AssistantChoice(id=choice_id, label=label)
            for choice_id, label, _, _ in TUTORIAL_OPTIONS
        )
        if profile_analysis_completed
        else (AssistantChoice("analyse_profile", "Analyse my Profile"),)
    )
    return AssistantTurn(
        story_id=STANDARD_STORY_ID,
        scene_id=STANDARD_HELP_SCENE,
        lines=lines,
        choices=choices,
        choice_label="",
        knowledge_updates=knowledge_updates or {},
    )


class StandardStory(AssistantStory):
    story_id = STANDARD_STORY_ID

    def __init__(self, *, smalltalk_story: SmalltalkStory | None = None) -> None:
        self._smalltalk_story = smalltalk_story or SmalltalkStory()

    def _menu_turn(
        self,
        context: AssistantContext,
        *,
        lines: tuple[AssistantLine, ...] = (),
        knowledge_updates=None,
    ) -> AssistantTurn:
        return standard_menu_turn(
            smalltalk_choice=self._smalltalk_story.menu_choice(context),
            lines=lines,
            knowledge_updates=knowledge_updates,
        )

    def entry_scene(self, context: AssistantContext) -> str:
        # Only preserve an in-progress help scene during a rerun of Assistant.
        if (
            context.previous_page_key == "assistant"
            and context.state.story == self.story_id
            and context.state.scene in (*EXPLANATION_SCENES, STANDARD_HELP_SCENE)
        ):
            return context.state.scene or STANDARD_MENU_SCENE
        return STANDARD_MENU_SCENE

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        scene_id = scene_id or self.entry_scene(context)
        if scene_id in EXPLANATION_SCENES:
            if context.previous_page_key != "assistant" and selection is None:
                return replace(
                    self._menu_turn(context),
                    state_story=self.story_id,
                    state_scene=READY_NODE,
                    state_status="completed",
                    completed=True,
                )
            return explanation_turn(context, self.story_id, scene_id, selection)

        if scene_id == STANDARD_MENU_SCENE:
            if selection is None:
                return self._menu_turn(context)
            if selection.choice_id == "help":
                return replace(
                    standard_help_turn(
                        profile_analysis_completed=bool(
                            context.state.knowledge.get(
                                PROFILE_ANALYSIS_KNOWLEDGE_KEY, False
                            )
                        )
                    ),
                    state_story=self.story_id, state_scene=STANDARD_HELP_SCENE,
                    state_status="active",
                )
            if selection.choice_id == "weekly_summary":
                from src.assistant.stories.weekly_summary import WeeklySummaryStory
                return WeeklySummaryStory().advance(context, None, None)
            if selection.choice_id == "smalltalk":
                return replace(
                    self._smalltalk_story.advance(context, None, selection),
                    story_id=self.story_id,
                    scene_id=STANDARD_MENU_SCENE,
                    choices=self._menu_turn(context).choices,
                )
            return self._menu_turn(context)

        if selection is None:
            return standard_help_turn(
                profile_analysis_completed=bool(
                    context.state.knowledge.get(
                        PROFILE_ANALYSIS_KNOWLEDGE_KEY, False
                    )
                )
            )

        if selection.choice_id == "analyse_profile":
            return AssistantTurn(
                story_id=TUTORIAL_STORY_ID,
                scene_id=FRIENDS_NODE,
                state_story=TUTORIAL_STORY_ID,
                state_scene=FRIENDS_NODE,
                state_status="active",
                continue_flow=True,
            )

        selected = next(
            (item for item in TUTORIAL_OPTIONS if item[0] == selection.choice_id),
            None,
        )
        if selected is None:
            return standard_help_turn(profile_analysis_completed=True)

        _, _, knowledge_key, tutorial_scene = selected
        if tutorial_scene is None:
            return standard_help_turn(
                lines=(AssistantLine("That tutorial is coming soon."),),
                knowledge_updates={knowledge_key: True},
                profile_analysis_completed=True,
            )
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=tutorial_scene,
            knowledge_updates={knowledge_key: True},
            state_story=self.story_id,
            state_scene=tutorial_scene,
            state_status="active",
            continue_flow=True,
        )
