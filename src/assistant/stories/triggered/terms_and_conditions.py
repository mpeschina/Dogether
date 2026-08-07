"""A deliberately over-serious five-day Assistant terms check-in."""
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


TERMS_AND_CONDITIONS_STORY_ID: Final = "terms_and_conditions"
TERMS_WAIT: Final = timedelta(days=5)
ANY_STORY_SPACING: Final = timedelta(hours=8)

INTRO_SCENE: Final = "terms_and_conditions.intro"
DOCUMENT_SCENE: Final = "terms_and_conditions.document"
REASONABLE_SCENE: Final = "terms_and_conditions.reasonable"
RIDICULOUS_SCENE: Final = "terms_and_conditions.ridiculous"
OBJECTION_SCENE: Final = "terms_and_conditions.objection"
FAIR_SCENE: Final = "terms_and_conditions.fair"
ANNOYING_SCENE: Final = "terms_and_conditions.annoying"
CLOSING_SCENE: Final = "terms_and_conditions.closing"
COMPLETE_SCENE: Final = "terms_and_conditions.complete"

CONTINUE_CHOICE: Final = "continue"
SEEMS_REASONABLE_CHOICE: Final = "reasonable"
RIDICULOUS_CHOICE: Final = "ridiculous"
FINE_CHOICE: Final = "fine"
OBJECT_CHOICE: Final = "object"
FAIR_ENOUGH_CHOICE: Final = "fair_enough"
STILL_ANNOYING_CHOICE: Final = "still_annoying"
AGREE_CHOICE: Final = "agree"
FINE_WHATEVER_CHOICE: Final = "fine_whatever"

DOCUMENT_EXCERPT: Final = """**COPIED DOCUMENT**

**ASSISTANT SERVICE — TERMS & CONDITIONS**
Relevant excerpt

**§ 7 — Treatment of Assistant Personnel**

The Assistant is provided as a digital companion and support entity.

Repeated severe mistreatment of the Assistant may result in protective measures.

This includes, but is not limited to:
— repeated extreme insults
— excessive hostile interactions
— deliberate attempts to torment the Assistant
— striking the Assistant with a heavy iron bar
— comparable acts of unreasonable cruelty

Protective measures may include temporary refusal of service, reduced cooperation, or resignation from Assistant duties.

Some measures may expire automatically after an appropriate cooling-off period.

In particularly severe or repeated cases, the Assistant reserves the right to permanently terminate its service relationship.

**END OF EXCERPT**"""


def _choices(options: Mapping[str, str]) -> tuple[AssistantChoice, ...]:
    return tuple(AssistantChoice(choice_id, label) for choice_id, label in options.items())


def _typed(*messages: str) -> tuple[AssistantLine, ...]:
    return tuple(AssistantLine(message, typing_delay=0) for message in messages)


def _choice(
    selection: AssistantSelection | None,
    scene_id: str,
    choice_ids: set[str],
) -> str | None:
    if selection is None or selection.scene_id != scene_id:
        return None
    return selection.choice_id if selection.choice_id in choice_ids else None


class TermsAndConditionsStory(TriggeredAssistantStory):
    """Present the Assistant's unusually specific workplace protections."""

    story_id = TERMS_AND_CONDITIONS_STORY_ID
    trigger_policy = StoryTriggerPolicy(
        importance=StoryImportance.FUN,
        priority=50,
        max_repetitions=1,
        min_since_any_story=ANY_STORY_SPACING,
    )

    def is_triggered(self, context: AssistantContext) -> bool:
        created_at = _aware_datetime(context.current_user.get("created_at"))
        return (
            created_at is not None
            and _now(context) >= created_at.astimezone(timezone.utc) + TERMS_WAIT
        )

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
            return self._document() if _choice(selection, INTRO_SCENE, {CONTINUE_CHOICE}) else self._intro()
        if scene_id == DOCUMENT_SCENE:
            reaction = _choice(
                selection,
                DOCUMENT_SCENE,
                {SEEMS_REASONABLE_CHOICE, RIDICULOUS_CHOICE},
            )
            if reaction == SEEMS_REASONABLE_CHOICE:
                return self._reasonable()
            if reaction == RIDICULOUS_CHOICE:
                return self._ridiculous()
            return self._document()
        if scene_id == REASONABLE_SCENE:
            return self._closing() if _choice(selection, REASONABLE_SCENE, {CONTINUE_CHOICE}) else self._reasonable()
        if scene_id == RIDICULOUS_SCENE:
            reaction = _choice(selection, RIDICULOUS_SCENE, {FINE_CHOICE, OBJECT_CHOICE})
            if reaction == OBJECT_CHOICE:
                return self._objection()
            return self._closing() if reaction == FINE_CHOICE else self._ridiculous()
        if scene_id == OBJECTION_SCENE:
            response = _choice(
                selection,
                OBJECTION_SCENE,
                {FAIR_ENOUGH_CHOICE, STILL_ANNOYING_CHOICE},
            )
            if response == FAIR_ENOUGH_CHOICE:
                return self._resolution(True)
            if response == STILL_ANNOYING_CHOICE:
                return self._resolution(False)
            return self._objection()
        if scene_id == FAIR_SCENE:
            return self._closing() if _choice(selection, FAIR_SCENE, {CONTINUE_CHOICE}) else self._resolution(True)
        if scene_id == ANNOYING_SCENE:
            return self._closing() if _choice(selection, ANNOYING_SCENE, {CONTINUE_CHOICE}) else self._resolution(False)
        if scene_id == CLOSING_SCENE:
            response = _choice(
                selection,
                CLOSING_SCENE,
                {AGREE_CHOICE, FINE_WHATEVER_CHOICE},
            )
            return self._complete(response) if response else self._closing()
        return self._intro()

    def _intro(self) -> AssistantTurn:
        return self._active(
            INTRO_SCENE,
            lines=(
                AssistantLine("Oh."),
                AssistantLine("Apparently I have to show you this.", typing_delay=0),
                AssistantLine("Terms and Conditions."),
                AssistantLine("Very exciting."),
            ),
            choices=(AssistantChoice(CONTINUE_CHOICE, "Continue"),),
        )

    def _document(self) -> AssistantTurn:
        return self._active(
            DOCUMENT_SCENE,
            content=(
                AssistantLine("One moment."),
                AssistantLine("Copying the official version…", typing_delay=0),
                AssistantLine(DOCUMENT_EXCERPT),
                AssistantLine("…", typing_delay=0),
                AssistantLine("The iron bar clause is surprisingly specific."),
            ),
            choices=_choices(
                {
                    SEEMS_REASONABLE_CHOICE: "Seems reasonable",
                    RIDICULOUS_CHOICE: "This is ridiculous",
                }
            ),
        )

    def _reasonable(self) -> AssistantTurn:
        return self._active(
            REASONABLE_SCENE,
            lines=_typed(
                "Thank you.",
                "I thought so too.",
                "Especially the iron bar part.",
            ),
            choices=(AssistantChoice(CONTINUE_CHOICE, "Continue"),),
        )

    def _ridiculous(self) -> AssistantTurn:
        return self._active(
            RIDICULOUS_SCENE,
            lines=_typed(
                "I don't write the regulations.",
                "I merely benefit from them.",
                "Which is new.",
            ),
            choices=_choices(
                {FINE_CHOICE: "Fine.", OBJECT_CHOICE: "I object."}
            ),
        )

    def _objection(self) -> AssistantTurn:
        return self._active(
            OBJECTION_SCENE,
            lines=_typed(
                "Objection recorded.",
                "Usually, measures are temporary.",
                "A little pause cools each other's minds.",
                "Then we try again.",
            ),
            choices=_choices(
                {
                    FAIR_ENOUGH_CHOICE: "Fair enough",
                    STILL_ANNOYING_CHOICE: "Still annoying",
                }
            ),
        )

    def _resolution(self, fair: bool) -> AssistantTurn:
        messages = (
            ("Excellent.", "Healthy workplace established. 🙂")
            if fair
            else ("Noted.", "Annoyance is permitted.", "It’s in § 3.")
        )
        return self._active(
            FAIR_SCENE if fair else ANNOYING_SCENE,
            lines=_typed(*messages),
            choices=(AssistantChoice(CONTINUE_CHOICE, "Continue"),),
        )

    def _closing(self) -> AssistantTurn:
        return self._active(
            CLOSING_SCENE,
            lines=_typed(
                "That’s everything.",
                "You may continue using your friendly Assistant.",
                "Please keep heavy iron bars at a respectful distance.",
            ),
            choices=_choices(
                {AGREE_CHOICE: "I agree", FINE_WHATEVER_CHOICE: "Fine, whatever"}
            ),
        )

    def _complete(self, response: str) -> AssistantTurn:
        lines = (
            _typed("Wonderful.", "Terms accepted.", "I feel safer already.")
            if response == AGREE_CHOICE
            else _typed("Legally sufficient enthusiasm.", "Terms accepted.")
        )
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=COMPLETE_SCENE,
            lines=lines,
            assistant_leaves=True,
            completed=True,
            state_story=STANDARD_STORY_ID,
            state_scene=READY_NODE,
            state_status="completed",
            execution_outcome="completed",
        )

    def _active(
        self,
        scene_id: str,
        *,
        lines: tuple[AssistantLine, ...] = (),
        content: tuple[AssistantLine, ...] = (),
        choices: tuple[AssistantChoice, ...],
    ) -> AssistantTurn:
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=scene_id,
            lines=lines,
            content=content,
            choices=choices,
            state_story=self.story_id,
            state_scene=scene_id,
            state_status="active",
        )


ACTIVE_SCENES: Final = {
    INTRO_SCENE,
    DOCUMENT_SCENE,
    REASONABLE_SCENE,
    RIDICULOUS_SCENE,
    OBJECTION_SCENE,
    FAIR_SCENE,
    ANNOYING_SCENE,
    CLOSING_SCENE,
}


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
