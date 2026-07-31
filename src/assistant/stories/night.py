"""The overnight assistant interruption."""
from __future__ import annotations

import random
from typing import Any, Final

from src.assistant.core import (
    AssistantChoice,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
    ProgressEntry,
)
from src.assistant.story_session import story_session


NIGHT_STORY_ID: Final = "night"
NIGHT_EVENT_ID: Final = "night.interruption"
NIGHT_AFTER_LEAVING_SCENE: Final = "night.after_leaving"
NIGHT_GOOD_NIGHT_SCENE: Final = "night.good_night"
NIGHT_CLICKS_KEY: Final = "clicks"
NIGHT_COMPLETED_COUNT_KEY: Final = "completed_count"
INITIAL_STATUSES: Final = (
    "It seems to be empty here",
    "You imagine to hear sleeping noises",
    "Is someone here? You dont know",
    "You feel calm and quiet, with a gentle touch of loneliness.",
    "Something nearby has recently moved.",
    "You have the strange feeling that you arrived too late.",
    "What does this send button do?",
    "The silence makes every small movement feel important.",
)
STATUS_CLICK_COUNT: Final = 6
PROGRESS_BAR_CLICK_COUNT: Final = 30
PROGRESS_BAR_COUNT: Final = 3
EXIT_DELAY_SECONDS: Final = 3


class NightStory(AssistantStory):
    """Make persistent night owls work through the assistant's sleepiness."""

    story_id = NIGHT_STORY_ID

    def __init__(self, *, random_source: Any = random) -> None:
        self._random_source = random_source

    def entry_scene(self, context: AssistantContext) -> str | None:
        del context
        return NIGHT_EVENT_ID

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        if scene_id == NIGHT_AFTER_LEAVING_SCENE:
            return self._after_leaving()
        if scene_id == NIGHT_GOOD_NIGHT_SCENE:
            return self._leave_for_main_page(context)

        session = story_session(context.session_state, self.story_id)
        clicks = _non_negative_int(session.get(NIGHT_CLICKS_KEY))
        if selection is not None:
            clicks += 1

        if clicks <= STATUS_CLICK_COUNT:
            return self._send_turn(
                context,
                clicks,
                statuses=(
                    (f"{clicks}x",)
                    if clicks
                    else (self._initial_status(),)
                ),
                keep_statuses_in_history=selection is None,
            )

        progress_clicks = clicks - STATUS_CLICK_COUNT
        progress = _progress_entries(progress_clicks)
        if progress_clicks < PROGRESS_BAR_CLICK_COUNT * PROGRESS_BAR_COUNT:
            return self._send_turn(context, clicks, progress=progress)

        completed_count = _non_negative_int(
            context.state.events.get(NIGHT_EVENT_ID, {}).get(NIGHT_COMPLETED_COUNT_KEY)
        ) + 1
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=NIGHT_AFTER_LEAVING_SCENE,
            lines=(
                AssistantLine("Man, I am sleeping its super late!"),
                AssistantLine(
                    "(hm, did you already tell me your gender?)", font_scale=0.5
                ),
                AssistantLine("Anyhow, I need to sleep and so do you."),
                AssistantLine("Dont disturb me during the night!!!!"),
            ),
            progress=progress,
            progress_before_content=True,
            assistant_leaves=True,
            allow_interaction_after_leaving=True,
            choices=(
                AssistantChoice("sorry", "Ähm, yes, ok. Sorry ..."),
                AssistantChoice("good_night", "Good Night"),
                AssistantChoice(
                    "not_angry", "But hey, no reason to get angry at me!"
                ),
            ),
            event_updates={
                NIGHT_EVENT_ID: {NIGHT_COMPLETED_COUNT_KEY: completed_count}
            },
            completed=True,
            state_status="paused",
        )

    def _initial_status(self) -> str:
        return self._random_source.choice(INITIAL_STATUSES)

    def _after_leaving(self) -> AssistantTurn:
        """Accept the user's reaction without responding before the final exit."""
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=NIGHT_GOOD_NIGHT_SCENE,
            choices=(
                AssistantChoice("go_to_bed", "You are right, I will also go to bed now"),
                AssistantChoice(
                    "leave_quietly", "Leave chat without a saying", style="italic"
                ),
            ),
            state_status="paused",
        )

    def _leave_for_main_page(self, context: AssistantContext) -> AssistantTurn:
        story_session(context.session_state, self.story_id).clear()
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=NIGHT_GOOD_NIGHT_SCENE,
            destination="goals",
            destination_delay=EXIT_DELAY_SECONDS,
            completed=True,
            state_status="completed",
        )

    def _send_turn(
        self,
        context: AssistantContext,
        clicks: int,
        *,
        statuses: tuple[str, ...] = (),
        progress: tuple[ProgressEntry, ...] = (),
        keep_statuses_in_history: bool = False,
    ) -> AssistantTurn:
        story_session(context.session_state, self.story_id).set(NIGHT_CLICKS_KEY, clicks)
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=NIGHT_EVENT_ID,
            control_kind="send",
            record_selection=False,
            statuses=statuses,
            progress=progress,
            keep_statuses_in_history=keep_statuses_in_history,
            state_status="paused",
        )


def clear_night_session(session_state) -> None:
    """Discard an unfinished overnight exchange after leaving Assistant."""
    story_session(session_state, NIGHT_STORY_ID).clear()


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
            ProgressEntry(clicks / PROGRESS_BAR_CLICK_COUNT, f"{clicks} / {PROGRESS_BAR_CLICK_COUNT}")
        )
    return tuple(entries)
