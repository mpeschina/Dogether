"""The overnight assistant interruption."""
from __future__ import annotations

from typing import Final

from src.assistant.core import (
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
NIGHT_CLICKS_KEY: Final = "clicks"
STATUS_CLICK_COUNT: Final = 6
PROGRESS_BAR_CLICK_COUNT: Final = 30
PROGRESS_BAR_COUNT: Final = 3


class NightStory(AssistantStory):
    """Make persistent night owls work through the assistant's sleepiness."""

    story_id = NIGHT_STORY_ID

    def entry_scene(self, context: AssistantContext) -> str | None:
        del context
        return NIGHT_EVENT_ID

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        del scene_id
        session = story_session(context.session_state, self.story_id)
        clicks = _non_negative_int(session.get(NIGHT_CLICKS_KEY))
        if selection is not None:
            clicks += 1

        if clicks <= STATUS_CLICK_COUNT:
            return self._send_turn(
                context, clicks, statuses=(f"{clicks}x",) if clicks else ()
            )

        progress_clicks = clicks - STATUS_CLICK_COUNT
        progress = _progress_entries(progress_clicks)
        if progress_clicks < PROGRESS_BAR_CLICK_COUNT * PROGRESS_BAR_COUNT:
            return self._send_turn(context, clicks, progress=progress)

        session.clear()
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=NIGHT_EVENT_ID,
            lines=(
                AssistantLine("Man, I am sleeping its super late!"),
                AssistantLine(
                    "(hm, did you already tell me your gender?)", font_scale=0.5
                ),
                AssistantLine("Anyhow, I need to sleep and so do you."),
                AssistantLine("Dont disturb me during the night!!!!"),
            ),
            progress=progress,
            assistant_leaves=True,
            completed=True,
        )

    def _send_turn(
        self,
        context: AssistantContext,
        clicks: int,
        *,
        statuses: tuple[str, ...] = (),
        progress: tuple[ProgressEntry, ...] = (),
    ) -> AssistantTurn:
        story_session(context.session_state, self.story_id).set(NIGHT_CLICKS_KEY, clicks)
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=NIGHT_EVENT_ID,
            control_kind="send",
            record_selection=False,
            statuses=statuses,
            progress=progress,
            keep_statuses_in_history=False,
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
