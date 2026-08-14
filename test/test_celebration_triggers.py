from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.assistant.core import AssistantContext, AssistantSelection
from src.assistant.director import AssistantDirector
from src.assistant.state import AssistantState, StoryExecutionState
from src.assistant.stories.greetings import GREETINGS_STORY_ID, GreetingsStory
from src.assistant.stories.standard import StandardStory
from src.assistant.stories.triggered import triggered_stories
from src.assistant.stories.triggered.celebrations import (
    CELEBRATION_WAIT,
    CELEBRATION_STORY_IDS,
    DEFER_CHOICE_ID,
    VARIANTS,
)
from src.assistant.triggers import StoryImportance, TriggerStorySelector


NOW = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)


def context(
    *,
    state: AssistantState | None = None,
    user_state: dict | None = None,
    created_at: object = (NOW - CELEBRATION_WAIT).isoformat(),
    now: datetime = NOW,
):
    return AssistantContext(
        user_id="alice",
        current_user={"user_id": "alice", "created_at": created_at},
        state=state or AssistantState(story="standard", scene="ready", status="completed"),
        session_state={},
        current_page_key="assistant",
        previous_page_key="assistant",
        now=now,
        user_state=(
            {"goal_count": 1, "goals": [{"description": "Reading"}]}
            if user_state is None
            else user_state
        ),
    )


def selection(turn, choice_id: str) -> AssistantSelection:
    return AssistantSelection(turn.story_id, turn.scene_id, choice_id, "")


class RecordingPersistence:
    def save_assistant_state(self, user_id, assistant_state, now=None):
        del user_id, now
        return assistant_state


class RecordingView:
    waiting_for_input = False

    def __init__(self, selection: AssistantSelection | None = None) -> None:
        self.selection = selection
        self.turns = []

    def present(self, turn) -> None:
        self.turns.append(turn)

    def finish(self) -> None:
        pass


def test_all_celebration_variants_are_discovered_once_and_are_one_time_fun_stories() -> None:
    stories = triggered_stories()
    variants = [stories[story_id] for story_id in CELEBRATION_STORY_IDS]

    assert len(variants) == 15
    assert all(story.trigger_policy.importance is StoryImportance.FUN for story in variants)
    assert all(story.trigger_policy.max_repetitions == 1 for story in variants)
    assert {len(variant.beats) for variant in VARIANTS} >= {2, 10}
    assert len({tuple(beat.lines for beat in variant.beats) for variant in VARIANTS}) == len(VARIANTS)

    used = replace(
        context().state,
        story_executions={CELEBRATION_STORY_IDS[0]: StoryExecutionState(starts=1)},
    )
    assert TriggerStorySelector({CELEBRATION_STORY_IDS[0]: variants[0]}).select(context(state=used)) is None


@pytest.mark.parametrize(
    ("created_at", "now", "expected"),
    (
        ((NOW - CELEBRATION_WAIT + timedelta(microseconds=1)).isoformat(), NOW, False),
        ((NOW - CELEBRATION_WAIT).isoformat(), NOW, True),
        (
            (NOW - CELEBRATION_WAIT)
            .astimezone(timezone(timedelta(hours=2)))
            .isoformat(),
            NOW,
            True,
        ),
        (None, NOW, False),
        ("not-a-date", NOW, False),
        ((NOW - CELEBRATION_WAIT).replace(tzinfo=None).isoformat(), NOW, False),
    ),
)
def test_celebrations_start_only_after_the_wait_with_a_timezone_aware_join_time(
    created_at: object, now: datetime, expected: bool
) -> None:
    story = triggered_stories()[CELEBRATION_STORY_IDS[0]]

    assert story.is_triggered(context(created_at=created_at, now=now)) is expected


@pytest.mark.parametrize("story_id", CELEBRATION_STORY_IDS)
def test_every_choice_rejoins_the_same_linear_celebration_flow(story_id: str) -> None:
    story = triggered_stories()[story_id]
    current = context()
    turn = story.advance(current, None, None)

    while not turn.completed:
        assert 1 <= len(turn.choices) <= 3
        story_choices = [
            choice for choice in turn.choices if choice.id != DEFER_CHOICE_ID
        ]
        alternatives = [
            story.advance(current, turn.scene_id, selection(turn, choice.id))
            for choice in story_choices
        ]
        assert len({next_turn.scene_id for next_turn in alternatives}) == 1
        assert len({next_turn.completed for next_turn in alternatives}) == 1
        turn = alternatives[0]

    assert turn.execution_outcome == "completed"


@pytest.mark.parametrize("story_id", CELEBRATION_STORY_IDS)
def test_every_celebration_can_be_deferred_from_its_opening(story_id: str) -> None:
    story = triggered_stories()[story_id]
    opening = story.advance(context(), None, None)

    defer_choice = next(choice for choice in opening.choices if choice.id == DEFER_CHOICE_ID)
    deferred = story.advance(context(), opening.scene_id, selection(opening, defer_choice.id))

    assert deferred.completed
    assert not deferred.choices
    assert deferred.continue_flow
    assert deferred.skip_greeting
    assert deferred.open_standard_menu
    assert deferred.state_story == "standard"
    assert deferred.state_scene == "ready"
    assert deferred.state_status == "completed"
    assert deferred.execution_outcome == "dismissed"


@pytest.mark.parametrize("variant", VARIANTS, ids=lambda variant: variant.identifier)
def test_celebration_finales_are_rendered_as_complete_messages(variant) -> None:
    story = triggered_stories()[f"celebration.{variant.identifier}"]
    current = context()
    turn = story.advance(current, None, None)

    while not turn.completed:
        turn = story.advance(current, turn.scene_id, selection(turn, turn.choices[0].id))

    rendered_finale = tuple(line.text for line in turn.lines[-len(variant.finale) :])
    assert rendered_finale == variant.finale


def test_goal_aware_variants_use_the_known_goal_without_storing_user_answers() -> None:
    story = triggered_stories()[CELEBRATION_STORY_IDS[4]]
    current = context(
        user_state={
            "goal_count": 2,
            "goals": [
                {"description": "Swimming", "participants": {"alice": {"current": 8, "target": 10}}},
                {"description": "Reading", "participants": {"alice": {"current": 12, "target": 10}}},
            ],
        }
    )
    first = story.advance(current, None, None)
    status_turn = story.advance(current, first.scene_id, selection(first, first.choices[0].id))

    assert any("Reading" in line.text and "12 / 10" in line.text for line in status_turn.lines)
    assert not status_turn.event_updates
    assert not status_turn.knowledge_updates


def test_goal_aware_variants_can_name_a_goal_that_needs_focus() -> None:
    story = triggered_stories()[CELEBRATION_STORY_IDS[7]]
    current = context(
        user_state={
            "goal_count": 1,
            "goals": [
                {"description": "Running", "participants": {"alice": {"current": 2, "target": 10}}}
            ],
        }
    )
    first = story.advance(current, None, None)
    status_turn = story.advance(current, first.scene_id, selection(first, first.choices[0].id))

    assert any("Running" in line.text and "2 / 10" in line.text for line in status_turn.lines)


def test_player_options_are_spoken_lines_or_italic_actions() -> None:
    for variant in VARIANTS:
        for beat in variant.beats:
            raw_choices = dict(beat.choices)
            story = triggered_stories()[f"celebration.{variant.identifier}"]
            scene_index = variant.beats.index(beat)
            turn = story.advance(context(), f"{story.story_id}.beat_{scene_index}", None)
            for choice in turn.choices:
                if choice.id == DEFER_CHOICE_ID:
                    continue
                raw_label = raw_choices[choice.id]
                if raw_label.startswith("*"):
                    assert choice.style == "italic"
                    assert choice.label == raw_label[1:-1]
                    assert choice.record_selection is False
                else:
                    assert choice.style == "default"
                    assert choice.record_selection is True
                    assert choice.label[-1] in ".?!"
                    assert len(choice.label.split()) >= 2


def test_celebration_completion_opens_standard_menu_without_a_greeting() -> None:
    celebration = triggered_stories()[CELEBRATION_STORY_IDS[0]]
    director = AssistantDirector(
        RecordingPersistence(),
        {
            celebration.story_id: celebration,
            "standard": StandardStory(),
            GREETINGS_STORY_ID: GreetingsStory(),
        },
    )
    current = context()
    view = RecordingView()
    state = director.render(current, view)

    while view.turns[-1].story_id == celebration.story_id:
        displayed = view.turns[-1]
        view = RecordingView(selection(displayed, displayed.choices[0].id))
        current = replace(current, state=state)
        state = director.render(current, view)

    assert view.turns[-1].story_id == "standard"
    assert all(turn.story_id != GREETINGS_STORY_ID for turn in view.turns)


def test_deferring_a_celebration_opens_standard_menu_without_completing_it() -> None:
    celebration = triggered_stories()[CELEBRATION_STORY_IDS[0]]
    director = AssistantDirector(
        RecordingPersistence(),
        {
            celebration.story_id: celebration,
            "standard": StandardStory(),
            GREETINGS_STORY_ID: GreetingsStory(),
        },
    )
    current = context()
    opening_view = RecordingView()
    started_state = director.render(current, opening_view)
    opening = opening_view.turns[-1]
    defer_choice = next(choice for choice in opening.choices if choice.id == DEFER_CHOICE_ID)

    deferred_view = RecordingView(selection(opening, defer_choice.id))
    state = director.render(replace(current, state=started_state), deferred_view)

    execution = state.story_executions[celebration.story_id]
    assert deferred_view.turns[-1].story_id == "standard"
    assert all(turn.story_id != GREETINGS_STORY_ID for turn in deferred_view.turns)
    assert state.story == "standard"
    assert state.scene == "ready"
    assert state.status == "completed"
    assert execution.starts == 1
    assert execution.completions == 0
    assert execution.last_dismissed_at is not None
