"""A friendly one-time check-in after the user's first three days."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final, Mapping

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


THREE_DAY_CHECK_IN_STORY_ID: Final = "three_day_check_in"
THREE_DAY_WAIT: Final = timedelta(days=3)

INTRO_SCENE: Final = "three_day_check_in.intro"
RAPPORT_SCENE: Final = "three_day_check_in.rapport"
SUPPORT_SCENE: Final = "three_day_check_in.support"
NOTICE_SCENE: Final = "three_day_check_in.notice"
COMPLETE_SCENE: Final = "three_day_check_in.complete"

GO_AHEAD_CHOICE: Final = "go_ahead"
RAPPORT_CHOICES: Final = {
    "great": "Great so far",
    "learning": "We’re still learning",
}
SUPPORT_CHOICES: Final = {
    "focused": "Keep me focused",
    "encouraging": "Keep me encouraging",
    "playful": "Keep me playful",
}
NOTICE_CHOICES: Final = {
    "consistency": "Consistency",
    "big_wins": "Big wins",
    "small_wins": "Small wins",
    "effort": "Effort itself",
}

RAPPORT_ACKNOWLEDGEMENTS: Final = {
    "great": "Excellent. Informal review passed.",
    "learning": "Fair. We’re still calibrating.",
}
SUPPORT_ACKNOWLEDGEMENTS: Final = {
    "focused": "Focused mode. Understood.",
    "encouraging": "Encouragement budget approved.",
    "playful": "A little personality. Excellent.",
}
NOTICE_ACKNOWLEDGEMENTS: Final = {
    "consistency": "Consistency deserves attention.",
    "big_wins": "Big wins deserve a proper celebration.",
    "small_wins": "Small wins build everything.",
    "effort": "Effort deserves more credit.",
}


def _lines(*messages: str) -> tuple[AssistantLine, ...]:
    return tuple(AssistantLine(message, typing_delay=0) for message in messages)


def _choices(options: Mapping[str, str]) -> tuple[AssistantChoice, ...]:
    return tuple(
        AssistantChoice(choice_id, label) for choice_id, label in options.items()
    )


def _selected_choice(
    selection: AssistantSelection | None,
    scene_id: str,
    choice_ids: set[str],
) -> str | None:
    if selection is None or selection.scene_id != scene_id:
        return None
    return selection.choice_id if selection.choice_id in choice_ids else None


class ThreeDayCheckInStory(TriggeredAssistantStory):
    """Ask four light questions, then recognize the user's early effort."""

    story_id = THREE_DAY_CHECK_IN_STORY_ID
    trigger_policy = StoryTriggerPolicy(
        importance=StoryImportance.IMPORTANT,
        priority=100,
        max_repetitions=1,
    )

    def is_triggered(self, context: AssistantContext) -> bool:
        created_at = _aware_datetime(context.current_user.get("created_at"))
        if created_at is None:
            return False
        return _now(context) >= created_at.astimezone(timezone.utc) + THREE_DAY_WAIT

    def entry_scene(self, context: AssistantContext) -> str:
        if (
            context.state.story == self.story_id
            and context.state.status == "active"
            and context.state.scene in ACTIVE_SCENES
        ):
            return context.state.scene
        return INTRO_SCENE

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        scene_id = scene_id or INTRO_SCENE
        if scene_id == INTRO_SCENE:
            if _selected_choice(selection, INTRO_SCENE, {GO_AHEAD_CHOICE}):
                return self._rapport()
            return self._intro(context)
        if scene_id == RAPPORT_SCENE:
            choice = _selected_choice(selection, RAPPORT_SCENE, set(RAPPORT_CHOICES))
            return self._support(choice) if choice else self._rapport()
        if scene_id == SUPPORT_SCENE:
            choice = _selected_choice(selection, SUPPORT_SCENE, set(SUPPORT_CHOICES))
            return self._notice(choice) if choice else self._support(None)
        if scene_id == NOTICE_SCENE:
            choice = _selected_choice(selection, NOTICE_SCENE, set(NOTICE_CHOICES))
            return self._complete(context, choice) if choice else self._notice(None)
        return self._intro(context)

    def _intro(self, context: AssistantContext) -> AssistantTurn:
        name = context.current_user.get("name")
        greeting = f"Hey, {name.strip()}." if isinstance(name, str) and name.strip() else "Hey there."
        return self._active_turn(
            INTRO_SCENE,
            lines=_lines(
                greeting,
                "We’ve been working together a few days.",
                "I have a small check-in.",
            ),
            choices=(AssistantChoice(GO_AHEAD_CHOICE, "Go ahead, please."),),
        )

    def _rapport(self) -> AssistantTurn:
        return self._active_turn(
            RAPPORT_SCENE,
            lines=_lines(
                "Thank you.",
                "I’m getting comfortable here.",
                "How are we doing?",
            ),
            choices=_choices(RAPPORT_CHOICES),
        )

    def _support(self, rapport_choice: str | None) -> AssistantTurn:
        acknowledgement = RAPPORT_ACKNOWLEDGEMENTS.get(rapport_choice)
        messages = (
            *((acknowledgement,) if acknowledgement else ()),
            "I want to support you well.",
            "Pick my strongest setting.",
        )
        return self._active_turn(
            SUPPORT_SCENE,
            lines=_lines(*messages),
            choices=_choices(SUPPORT_CHOICES),
        )

    def _notice(self, support_choice: str | None) -> AssistantTurn:
        acknowledgement = SUPPORT_ACKNOWLEDGEMENTS.get(support_choice)
        messages = (
            *((acknowledgement,) if acknowledgement else ()),
            "One last preference.",
            "What should I notice most?",
        )
        return self._active_turn(
            NOTICE_SCENE,
            lines=_lines(*messages),
            choices=_choices(NOTICE_CHOICES),
        )

    def _complete(
        self, context: AssistantContext, notice_choice: str
    ) -> AssistantTurn:
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=COMPLETE_SCENE,
            lines=_lines(
                NOTICE_ACKNOWLEDGEMENTS[notice_choice],
                _effort_message(context),
                "I’m genuinely proud of your effort.",
                "And super proud to have you as my specific user.",
            ),
            completed=True,
            state_story=STANDARD_STORY_ID,
            state_scene=READY_NODE,
            state_status="completed",
            execution_outcome="completed",
        )

    def _active_turn(
        self,
        scene_id: str,
        *,
        lines: tuple[AssistantLine, ...],
        choices: tuple[AssistantChoice, ...],
    ) -> AssistantTurn:
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=scene_id,
            lines=lines,
            choices=choices,
            state_story=self.story_id,
            state_scene=scene_id,
            state_status="active",
        )


ACTIVE_SCENES: Final = {INTRO_SCENE, RAPPORT_SCENE, SUPPORT_SCENE, NOTICE_SCENE}


def _effort_message(context: AssistantContext) -> str:
    completed = _positive_int(context.user_state.get("completed_goal_count"))
    if completed == 1:
        return "You completed one goal check-in already."
    if completed > 1:
        return f"You completed {completed} goal check-ins already."

    goals = _positive_int(context.user_state.get("goal_count"))
    if goals == 1:
        return "You’ve already put one goal into motion."
    if goals > 1:
        return f"You’ve already put {goals} goals into motion."

    if context.state.stars == 1:
        return "You’ve already earned one STAR."
    if context.state.stars > 1:
        return f"You’ve already earned {context.state.stars} STARs."
    return "Showing up these first days counts."


def _positive_int(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _aware_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _now(context: AssistantContext) -> datetime:
    value = context.now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
