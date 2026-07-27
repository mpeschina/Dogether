"""Declarative versions of the prototype special-mode scenes."""
from __future__ import annotations

from typing import Final

from src.assistant.core import (
    AssistantChoice,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
    ProgressEntry,
)


SPECIAL_STORY_ID: Final = "special_examples"
SPECIAL_SEQUENCE_ID: Final = "special_examples"
HELP_PAGE_KEY: Final = "help"
WELCOME_EVENT_ID: Final = "special.welcome"
BUTTON_TEST_EVENT_ID: Final = "special.button_test"
CLICK_CHALLENGE_EVENT_ID: Final = "special.click_challenge"

STATUS_CLICK_COUNT: Final = 10
PROGRESS_BAR_CLICK_COUNT: Final = 40
PROGRESS_BAR_COUNT: Final = 3


class SpecialExampleStory(AssistantStory):
    story_id = SPECIAL_STORY_ID

    def entry_scene(self, context: AssistantContext) -> str | None:
        position = context.state.sequences.get(SPECIAL_SEQUENCE_ID, 0)
        scenes = (WELCOME_EVENT_ID, BUTTON_TEST_EVENT_ID, CLICK_CHALLENGE_EVENT_ID)
        if position < 0 or position >= len(scenes):
            return None
        scene = scenes[position]
        if position == 0:
            return scene
        event_state = context.state.events.get(scene, {})
        if context.previous_page_key != HELP_PAGE_KEY or event_state.get("active") is True:
            return scene
        return None

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn | None:
        scene_id = scene_id or self.entry_scene(context)
        if scene_id is None:
            return None
        if scene_id == WELCOME_EVENT_ID:
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=scene_id,
                lines=(
                    AssistantLine("Hey, welcome to our app!"),
                    AssistantLine(
                        "Ok, I just let you time to arrive and organize yourself.",
                        typing_delay=3,
                        wait_before=7,
                        wait_after=1,
                    ),
                ),
                assistant_leaves=True,
                completed=True,
                advance_sequences=(SPECIAL_SEQUENCE_ID,),
            )
        if scene_id == BUTTON_TEST_EVENT_ID:
            return self._button_test(selection)
        return self._click_challenge(context, selection)

    def _button_test(
        self, selection: AssistantSelection | None
    ) -> AssistantTurn:
        if selection is None:
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=BUTTON_TEST_EVENT_ID,
                lines=(
                    AssistantLine(
                        "Would you like to help us test the buttons? Pick a number below."
                    ),
                ),
                choices=tuple(
                    AssistantChoice(id=value, label=value) for value in ("1", "2", "3")
                ),
                choice_label="Choose a number",
                event_updates={BUTTON_TEST_EVENT_ID: {"active": True}},
                state_status="paused",
            )
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=BUTTON_TEST_EVENT_ID,
            lines=(
                AssistantLine(f"Thanks — you selected {selection.label}."),
            ),
            assistant_leaves=True,
            completed=True,
            advance_sequences=(SPECIAL_SEQUENCE_ID,),
            clear_events=(BUTTON_TEST_EVENT_ID,),
        )

    def _click_challenge(
        self,
        context: AssistantContext,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        event = dict(context.state.events.get(CLICK_CHALLENGE_EVENT_ID, {}))
        clicks = _non_negative_int(event.get("clicks"))
        if selection is not None:
            clicks += 1

        if clicks <= STATUS_CLICK_COUNT:
            statuses = (f"{clicks}x",) if clicks else ()
            return self._send_turn(clicks, statuses=statuses)

        progress_clicks = clicks - STATUS_CLICK_COUNT
        progress = _progress_entries(progress_clicks)
        if progress_clicks < PROGRESS_BAR_CLICK_COUNT * PROGRESS_BAR_COUNT:
            return self._send_turn(clicks, progress=progress)

        return AssistantTurn(
            story_id=self.story_id,
            scene_id=CLICK_CHALLENGE_EVENT_ID,
            lines=(
                AssistantLine("Come on."),
                AssistantLine("I AM NOT HERE!", typing_delay=4),
            ),
            progress=progress,
            assistant_leaves=True,
            completed=True,
            advance_sequences=(SPECIAL_SEQUENCE_ID,),
            clear_events=(CLICK_CHALLENGE_EVENT_ID,),
        )

    def _send_turn(
        self,
        clicks: int,
        *,
        statuses: tuple[str, ...] = (),
        progress: tuple[ProgressEntry, ...] = (),
    ) -> AssistantTurn:
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=CLICK_CHALLENGE_EVENT_ID,
            control_kind="send",
            record_selection=False,
            statuses=statuses,
            progress=progress,
            event_updates={
                CLICK_CHALLENGE_EVENT_ID: {"active": True, "clicks": clicks}
            },
            state_status="paused",
        )


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _progress_entries(progress_clicks: int) -> tuple[ProgressEntry, ...]:
    bar_count = min(
        PROGRESS_BAR_COUNT,
        (progress_clicks + PROGRESS_BAR_CLICK_COUNT - 1) // PROGRESS_BAR_CLICK_COUNT,
    )
    entries: list[ProgressEntry] = []
    for index in range(bar_count):
        clicks = min(
            PROGRESS_BAR_CLICK_COUNT,
            max(0, progress_clicks - index * PROGRESS_BAR_CLICK_COUNT),
        )
        entries.append(
            ProgressEntry(
                clicks / PROGRESS_BAR_CLICK_COUNT,
                f"{clicks} / {PROGRESS_BAR_CLICK_COUNT}",
            )
        )
    return tuple(entries)
