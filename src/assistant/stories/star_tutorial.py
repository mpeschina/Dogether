"""Reusable, caller-owned explanation scenes for Assistant STARs."""
from __future__ import annotations

from typing import Final

from src.assistant.core import (
    AssistantChoice,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantTurn,
)


STAR_TUTORIAL_INTRO_SCENE: Final = "stars.tutorial.intro"
STAR_TUTORIAL_CHECK_SCENE: Final = "stars.tutorial.check"
STAR_TUTORIAL_FINISH_SCENE: Final = "stars.tutorial.finish"
STAR_TUTORIAL_SCENES: Final = frozenset(
    (STAR_TUTORIAL_INTRO_SCENE, STAR_TUTORIAL_CHECK_SCENE, STAR_TUTORIAL_FINISH_SCENE)
)


def _choices(*items: tuple[str, str]) -> tuple[AssistantChoice, ...]:
    return tuple(AssistantChoice(choice_id, label) for choice_id, label in items)


def _lines(*text: str, long_pause: bool = False) -> tuple[AssistantLine, ...]:
    lines = tuple(AssistantLine(item, typing_delay=0) for item in text)
    return (*lines, AssistantLine("", typing_delay=6)) if long_pause else lines


def star_tutorial_turn(
    context: AssistantContext,
    owner: str,
    scene_id: str,
    selection: AssistantSelection | None,
    *,
    return_scene: str,
) -> AssistantTurn:
    """Render the STAR tutorial and return to the calling story when finished."""
    del context
    if scene_id == STAR_TUTORIAL_INTRO_SCENE:
        choices = _choices(("measurement", "Ok, and and a measurement of what?"))
        if selection is None or selection.choice_id not in {choice.id for choice in choices}:
            return AssistantTurn(
                owner,
                scene_id,
                lines=_lines(
                    "Sure, I can explain you the STARs",
                    "The STARS are not just decoration",
                    "they are a measurement.",
                ),
                choices=choices,
                state_story=owner,
                state_scene=scene_id,
                state_status="active",
            )
        return AssistantTurn(
            owner,
            scene_id,
            state_story=owner,
            state_scene=STAR_TUTORIAL_CHECK_SCENE,
            state_status="active",
            continue_flow=True,
        )

    if scene_id == STAR_TUTORIAL_CHECK_SCENE:
        choices = _choices(("faster", "Can you check faster, please?"))
        if selection is None or selection.choice_id not in {choice.id for choice in choices}:
            return AssistantTurn(
                owner,
                scene_id,
                lines=_lines("You mean of what exactly? Ill check that..", long_pause=True),
                choices=choices,
                state_story=owner,
                state_scene=scene_id,
                state_status="active",
            )
        return AssistantTurn(
            owner,
            scene_id,
            state_story=owner,
            state_scene=STAR_TUTORIAL_FINISH_SCENE,
            state_status="active",
            continue_flow=True,
        )

    choices = _choices(("thanks", "ok, thanks"), ("not_helpful", "ok, that was not helpful"))
    if selection is None or selection.choice_id not in {choice.id for choice in choices}:
        return AssistantTurn(
            owner,
            STAR_TUTORIAL_FINISH_SCENE,
            lines=_lines(
                "Yes...",
                "It seems, that information is currently above my clearance level.",
                "But every STAR appears to increase my rating.",
                "... and every rating also increases my clearance level!",
                "So, just get MORE STARs!",
            ),
            choices=choices,
            state_story=owner,
            state_scene=STAR_TUTORIAL_FINISH_SCENE,
            state_status="active",
        )
    return AssistantTurn(
        owner,
        STAR_TUTORIAL_FINISH_SCENE,
        state_story=owner,
        state_scene=return_scene,
        state_status="active",
        continue_flow=True,
    )
