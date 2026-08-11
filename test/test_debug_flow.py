from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.assistant.core import AssistantContext, AssistantSelection
from src.assistant.director import AssistantDirector
from src.assistant.state import AssistantMode, AssistantState
from src.assistant.stories import default_stories
from src.assistant.stories.debug import (
    DEBUG_STORY_ID,
    debug_story_options,
    select_debug_story,
    DebugFlowStory,
)
from src.assistant.stories.triggered.terms_and_conditions import (
    COMPLETE_SCENE,
    DOCUMENT_SCENE,
    INTRO_SCENE,
)


NOW = datetime(2026, 8, 7, 12, tzinfo=timezone.utc)


class RecordingPersistence:
    def __init__(self) -> None:
        self.saved_states: list[dict] = []

    def save_assistant_state(self, user_id, assistant_state, now=None):
        del user_id, now
        self.saved_states.append(assistant_state)
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


def context(
    state: AssistantState,
    session_state: dict,
) -> AssistantContext:
    return AssistantContext(
        user_id="alice",
        current_user={
            "user_id": "alice",
            "created_at": (NOW - timedelta(days=8)).isoformat(),
        },
        state=state,
        session_state=session_state,
        current_page_key="assistant",
        previous_page_key="assistant",
        now=NOW,
    )


def selection(turn, choice_id: str) -> AssistantSelection:
    return AssistantSelection(DEBUG_STORY_ID, turn.scene_id, choice_id, "")


def test_debug_runner_repeats_terms_flow_without_turn_state() -> None:
    story = DebugFlowStory()
    state = AssistantState(mode=AssistantMode.SPECIAL)
    session: dict = {}
    current = context(state, session)

    intro = story.advance(current, None, None)
    document = story.advance(current, intro.scene_id, selection(intro, "continue"))

    assert intro.story_id == DEBUG_STORY_ID
    assert intro.scene_id == INTRO_SCENE
    assert document.scene_id == DOCUMENT_SCENE
    assert not intro.completed
    assert intro.state_story is None
    assert intro.state_scene is None
    assert intro.state_status is None
    assert intro.execution_outcome is None


def test_debug_runner_clears_its_session_after_terms_completion() -> None:
    story = DebugFlowStory()
    state = AssistantState(mode=AssistantMode.SPECIAL)
    session: dict = {}
    current = context(state, session)
    turn = story.advance(current, None, None)

    for choice_id in ("continue", "reasonable", "continue", "agree"):
        turn = story.advance(current, turn.scene_id, selection(turn, choice_id))

    assert turn.scene_id == COMPLETE_SCENE
    assert turn.completed
    assert turn.state_mode is AssistantMode.NORMAL
    assert turn.open_standard_menu
    assert turn.skip_greeting
    assert story.entry_scene(current) == INTRO_SCENE


def test_special_mode_does_not_persist_or_count_the_debug_flow() -> None:
    persistence = RecordingPersistence()
    director = AssistantDirector(persistence, default_stories())
    state = AssistantState(mode=AssistantMode.SPECIAL)
    session: dict = {}

    result = director.render(context(state, session), RecordingView())

    assert result == state
    assert not persistence.saved_states
    assert not result.story_executions
    assert result.story_activity.last_story_started_at is None


def test_debug_player_offers_every_non_debug_story_and_rejects_unknown_ids() -> None:
    options = debug_story_options()
    session: dict = {}
    expected_story_ids = {
        story.story_id
        for story in default_stories().values()
        if story.story_id != DEBUG_STORY_ID
    }

    assert set(options) == expected_story_ids
    assert select_debug_story(session, next(iter(options)))
    assert not select_debug_story(session, "not-a-story")


def test_selected_debug_story_keeps_rewards_and_events_out_of_preview_state() -> None:
    story_id = "personal_highlight_tutorial"
    session: dict = {}
    assert select_debug_story(session, story_id)
    story = DebugFlowStory()
    state = AssistantState(mode=AssistantMode.SPECIAL)
    current = context(state, session)

    turn = story.advance(current, None, None)

    assert turn is not None
    assert turn.story_id == DEBUG_STORY_ID
    assert not turn.completed
    assert not turn.open_standard_menu
    assert not turn.event_updates
    assert not turn.knowledge_updates
    assert turn.destination is None


def test_completed_debug_preview_opens_standard_menu_without_replaying_or_greeting() -> None:
    persistence = RecordingPersistence()
    director = AssistantDirector(persistence, default_stories())
    state = AssistantState(mode=AssistantMode.SPECIAL)
    session: dict = {}
    current = context(state, session)
    view = RecordingView()
    state = director.render(current, view)

    for choice_id in ("continue", "reasonable", "continue", "agree"):
        displayed = view.turns[-1]
        view = RecordingView(selection(displayed, choice_id))
        current = replace(current, state=state)
        state = director.render(current, view)

    assert [turn.story_id for turn in view.turns][-1] == "standard"
    assert all(turn.story_id != "greetings" for turn in view.turns)
    assert state.mode is AssistantMode.NORMAL
