from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.assistant.core import AssistantContext, AssistantSelection
from src.assistant.director import AssistantDirector
from src.assistant.state import AssistantState, StoryExecutionState
from src.assistant.stories import default_stories
from src.assistant.stories.triggered import (
    ThreeDayCheckInStory,
    triggered_stories,
)
from src.assistant.stories.triggered.three_day_check_in import (
    COMPLETE_SCENE,
    INTRO_SCENE,
    NOTICE_SCENE,
    RAPPORT_SCENE,
    SUPPORT_SCENE,
    THREE_DAY_CHECK_IN_STORY_ID,
)
from src.assistant.triggers import TriggerStorySelector


NOW = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)
CREATED_AT = datetime(2026, 8, 3, 14, tzinfo=timezone(timedelta(hours=2)))


class RecordingPersistence:
    def __init__(self) -> None:
        self.saved_states: list[dict] = []

    def save_assistant_state(self, user_id, assistant_state, now=None):
        del user_id, now
        stored = AssistantState.from_value(assistant_state).to_dict()
        self.saved_states.append(stored)
        return stored


class RecordingView:
    waiting_for_input = False

    def __init__(self, selection: AssistantSelection | None = None) -> None:
        self.selection = selection
        self.turns = []

    def present(self, turn) -> None:
        self.turns.append(turn)

    def finish(self) -> None:
        pass


def context(
    *,
    state: AssistantState | None = None,
    created_at: object = CREATED_AT.isoformat(),
    now: datetime = NOW,
    name: object = "Alice",
    user_state: dict | None = None,
) -> AssistantContext:
    profile = {"user_id": "alice"}
    if created_at is not None:
        profile["created_at"] = created_at
    if name is not None:
        profile["name"] = name
    return AssistantContext(
        user_id="alice",
        current_user=profile,
        state=state
        or AssistantState(story="standard", scene="ready", status="completed"),
        session_state={},
        current_page_key="assistant",
        previous_page_key="assistant",
        now=now,
        user_state=user_state or {},
    )


def selection(turn, choice_id: str) -> AssistantSelection:
    return AssistantSelection(
        story_id=turn.story_id,
        scene_id=turn.scene_id,
        choice_id=choice_id,
        label="",
    )


@pytest.mark.parametrize(
    ("now", "expected"),
    (
        (NOW - timedelta(microseconds=1), False),
        (NOW, True),
        (NOW + timedelta(days=1), True),
    ),
)
def test_three_day_trigger_uses_an_exact_timezone_aware_boundary(
    now: datetime, expected: bool
) -> None:
    assert ThreeDayCheckInStory().is_triggered(context(now=now)) is expected


@pytest.mark.parametrize(
    "created_at",
    (None, "", "not-a-date", "2026-08-03T12:00:00"),
)
def test_three_day_trigger_rejects_missing_or_invalid_join_times(
    created_at: object,
) -> None:
    assert not ThreeDayCheckInStory().is_triggered(context(created_at=created_at))


def test_three_day_story_is_discovered_once_and_outranks_trigger_examples() -> None:
    discovered = triggered_stories()
    story = discovered[THREE_DAY_CHECK_IN_STORY_ID]

    assert isinstance(story, ThreeDayCheckInStory)
    assert (
        AssistantDirector(RecordingPersistence(), default_stories())
        .story_dispatch(context(state=replace(context().state, stars=6)), None)
        .story_id
        == THREE_DAY_CHECK_IN_STORY_ID
    )

    used_state = replace(
        context().state,
        story_executions={
            THREE_DAY_CHECK_IN_STORY_ID: StoryExecutionState(starts=1)
        },
    )
    assert (
        TriggerStorySelector({story.story_id: story}).select(
            context(state=used_state)
        )
        is None
    )


def test_story_has_one_two_three_and_four_choice_scenes() -> None:
    story = ThreeDayCheckInStory()
    current = context()

    intro = story.advance(current, None, None)
    rapport = story.advance(
        current, intro.scene_id, selection(intro, intro.choices[0].id)
    )
    support = story.advance(
        current, rapport.scene_id, selection(rapport, rapport.choices[0].id)
    )
    notice = story.advance(
        current, support.scene_id, selection(support, support.choices[0].id)
    )
    completed = story.advance(
        current, notice.scene_id, selection(notice, notice.choices[0].id)
    )

    assert [len(turn.choices) for turn in (intro, rapport, support, notice)] == [
        1,
        2,
        3,
        4,
    ]
    assert [turn.scene_id for turn in (intro, rapport, support, notice)] == [
        INTRO_SCENE,
        RAPPORT_SCENE,
        SUPPORT_SCENE,
        NOTICE_SCENE,
    ]
    assert all(turn.state_status == "active" for turn in (intro, rapport, support, notice))
    assert all(not turn.completed for turn in (intro, rapport, support, notice))
    assert completed.scene_id == COMPLETE_SCENE
    assert completed.completed
    assert completed.execution_outcome == "completed"
    assert not completed.choices


def test_every_answer_rejoins_the_shared_next_scene() -> None:
    story = ThreeDayCheckInStory()
    current = context()
    intro = story.advance(current, None, None)
    rapport = story.advance(
        current, intro.scene_id, selection(intro, intro.choices[0].id)
    )

    support_turns = [
        story.advance(current, rapport.scene_id, selection(rapport, choice.id))
        for choice in rapport.choices
    ]
    assert {turn.scene_id for turn in support_turns} == {SUPPORT_SCENE}
    assert len({tuple(line.text for line in turn.lines) for turn in support_turns}) == 2

    support = support_turns[0]
    notice_turns = [
        story.advance(current, support.scene_id, selection(support, choice.id))
        for choice in support.choices
    ]
    assert {turn.scene_id for turn in notice_turns} == {NOTICE_SCENE}
    assert len({tuple(line.text for line in turn.lines) for turn in notice_turns}) == 3

    notice = notice_turns[0]
    completed_turns = [
        story.advance(current, notice.scene_id, selection(notice, choice.id))
        for choice in notice.choices
    ]
    assert {turn.scene_id for turn in completed_turns} == {COMPLETE_SCENE}
    assert all(turn.completed for turn in completed_turns)
    assert len({tuple(line.text for line in turn.lines) for turn in completed_turns}) == 4


def test_completion_uses_each_available_effort_signal_without_storing_answers() -> None:
    story = ThreeDayCheckInStory()
    notice = story.advance(context(), NOTICE_SCENE, None)
    chosen = selection(notice, notice.choices[0].id)
    contexts = (
        context(
            state=replace(context().state, stars=4),
            user_state={"completed_goal_count": 3, "goal_count": 2},
        ),
        context(
            state=replace(context().state, stars=4),
            user_state={"goal_count": 2},
        ),
        context(state=replace(context().state, stars=4)),
        context(),
    )

    completions = [
        story.advance(current, NOTICE_SCENE, chosen) for current in contexts
    ]

    assert len({tuple(line.text for line in turn.lines) for turn in completions}) == 4
    assert all(not turn.event_updates for turn in completions)
    assert all(not turn.knowledge_updates for turn in completions)


def test_intro_uses_the_profile_name_when_available() -> None:
    story = ThreeDayCheckInStory()
    named = story.advance(context(name="Alice"), None, None)
    anonymous = story.advance(context(name=None), None, None)

    assert tuple(line.text for line in named.lines) != tuple(
        line.text for line in anonymous.lines
    )
    assert len(named.lines) == len(anonymous.lines)


def test_director_records_completion_only_after_the_last_choice() -> None:
    story = ThreeDayCheckInStory()
    persistence = RecordingPersistence()
    director = AssistantDirector(persistence, {story.story_id: story})
    current_context = context()

    view = RecordingView()
    state = director.render(current_context, view)
    turn = view.turns[-1]
    execution = state.story_executions[story.story_id]
    assert execution.starts == 1
    assert execution.completions == 0

    for _ in range(4):
        view = RecordingView(selection(turn, turn.choices[0].id))
        state = director.render(context(state=state), view)
        turn = view.turns[-1]
        if turn.choices:
            assert state.story == story.story_id
            assert state.status == "active"
            assert state.story_executions[story.story_id].completions == 0

    assert state.story == "standard"
    assert state.scene == "ready"
    assert state.status == "completed"
    assert state.story_executions[story.story_id].completions == 1
    assert persistence.saved_states
