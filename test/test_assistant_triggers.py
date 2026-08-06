from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.assistant.core import (
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantTurn,
)
from src.assistant.director import AssistantDirector
from src.assistant.presentation import clear_transcript_for_new_help_visit
from src.assistant.state import AssistantState, StoryActivityState, StoryExecutionState
import src.assistant.stories as stories_package
from src.assistant.stories import default_stories
from src.assistant.stories.triggered import (
    FunStarTriggerStory,
    ImportantStarTriggerStory,
    InformationalStarTriggerStory,
    triggered_stories,
)
from src.assistant.triggers import (
    OPTIONAL_STORY_STARTED_THIS_VISIT_KEY,
    StoryImportance,
    StoryTriggerPolicy,
    TriggeredAssistantStory,
    TriggerStorySelector,
)


NOW = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)


class RecordingPersistence:
    def __init__(self) -> None:
        self.saved_states: list[dict] = []

    def save_assistant_state(self, user_id, assistant_state, now=None):
        del user_id, now
        stored = AssistantState.from_value(assistant_state).to_dict()
        self.saved_states.append(stored)
        return stored


class RecordingView:
    selection = None
    waiting_for_input = False

    def __init__(self) -> None:
        self.turns = []

    def present(self, turn) -> None:
        self.turns.append(turn)

    def finish(self) -> None:
        pass


class LastChoiceRandom:
    @staticmethod
    def choice(values):
        return values[-1]


class StubTriggeredStory(TriggeredAssistantStory):
    def __init__(
        self,
        story_id: str,
        *,
        importance: StoryImportance = StoryImportance.FUN,
        priority: int = 0,
        event_id: str | None = None,
        outcome: str | None = "completed",
        enabled: bool = True,
        **policy,
    ) -> None:
        self.story_id = story_id
        self.trigger_policy = StoryTriggerPolicy(
            importance=importance,
            priority=priority,
            event_id=event_id,
            **policy,
        )
        self.outcome = outcome
        self.enabled = enabled

    def is_triggered(self, context):
        del context
        return self.enabled

    def entry_scene(self, context):
        del context
        return "entry"

    def advance(self, context, scene_id, selection):
        del context, selection
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=scene_id or "entry",
            lines=(AssistantLine("example"),),
            completed=self.outcome is not None,
            execution_outcome=self.outcome,
        )


def trigger_selector(*stories, random_source=None) -> TriggerStorySelector:
    kwargs = {} if random_source is None else {"random_source": random_source}
    return TriggerStorySelector(
        {story.story_id: story for story in stories},
        **kwargs,
    )


def context(state: AssistantState, *, session=None) -> AssistantContext:
    return AssistantContext(
        user_id="alice",
        current_user={"user_id": "alice"},
        state=state,
        session_state={} if session is None else session,
        current_page_key="assistant",
        previous_page_key="assistant",
        now=NOW,
    )


def ready_state(**changes) -> AssistantState:
    return replace(
        AssistantState(story="standard", scene="ready", status="completed"),
        **changes,
    )


def test_star_examples_require_more_than_five_stars_and_rank_by_importance() -> None:
    director = AssistantDirector(RecordingPersistence(), default_stories())

    at_five = director.story_dispatch(context(ready_state(stars=5)), None)
    at_six = director.story_dispatch(context(ready_state(stars=6)), None)

    assert at_five.story_id == "greetings"
    assert at_six.story_id == ImportantStarTriggerStory.story_id

    important_used = ready_state(
        stars=6,
        story_executions={
            ImportantStarTriggerStory.story_id: StoryExecutionState(starts=1)
        },
    )
    assert (
        director.story_dispatch(context(important_used), None).story_id
        == InformationalStarTriggerStory.story_id
    )


def test_default_stories_registers_every_discovered_trigger_story() -> None:
    discovered = triggered_stories()
    registered = default_stories()

    assert discovered
    assert discovered.keys() <= registered.keys()
    for story_id, story in discovered.items():
        assert type(registered[story_id]) is type(story)
        assert getattr(stories_package, type(story).__name__) is type(story)


def test_star_trigger_examples_are_interactive_flows() -> None:
    for story in (
        ImportantStarTriggerStory(),
        InformationalStarTriggerStory(),
        FunStarTriggerStory(),
    ):
        initial = story.advance(context(ready_state(stars=6)), None, None)

        assert initial.statuses
        assert initial.choices
        assert initial.state_story == story.story_id
        assert initial.state_status == "active"
        assert not initial.completed

        details = story.advance(
            context(ready_state(stars=6)),
            initial.scene_id,
            AssistantSelection(
                story_id=story.story_id,
                scene_id=initial.scene_id,
                choice_id="details",
                label="",
            ),
        )

        assert details.lines
        assert details.statuses
        assert details.choices
        assert details.state_story == story.story_id
        assert details.state_status == "active"
        assert not details.completed

        completed = story.advance(
            context(ready_state(stars=6)),
            details.scene_id,
            AssistantSelection(
                story_id=story.story_id,
                scene_id=details.scene_id,
                choice_id="finish",
                label="",
            ),
        )

        assert completed.completed
        assert completed.execution_outcome == "completed"


def test_trigger_flow_remains_active_until_the_user_finishes_it() -> None:
    persistence = RecordingPersistence()
    director = AssistantDirector(persistence, default_stories())
    state = ready_state(stars=6)

    first_view = RecordingView()
    state = director.render(context(state), first_view)
    initial = first_view.turns[-1]

    assert state.story == ImportantStarTriggerStory.story_id
    assert state.status == "active"
    assert state.story_executions[ImportantStarTriggerStory.story_id].starts == 1
    assert state.story_executions[ImportantStarTriggerStory.story_id].completions == 0

    details_view = RecordingView()
    details_view.selection = AssistantSelection(
        story_id=initial.story_id,
        scene_id=initial.scene_id,
        choice_id="details",
        label="",
    )
    state = director.render(context(state), details_view)
    details = details_view.turns[-1]

    assert state.story == ImportantStarTriggerStory.story_id
    assert state.status == "active"
    assert details.choices

    complete_view = RecordingView()
    complete_view.selection = AssistantSelection(
        story_id=details.story_id,
        scene_id=details.scene_id,
        choice_id="finish",
        label="",
    )
    state = director.render(context(state), complete_view)

    assert state.status == "completed"
    assert state.story_executions[ImportantStarTriggerStory.story_id].completions == 1


def test_candidate_order_uses_priority_stability_and_random_fun_ties() -> None:
    old = StubTriggeredStory("old", importance=StoryImportance.IMPORTANT, priority=4)
    new = StubTriggeredStory("new", importance=StoryImportance.IMPORTANT, priority=4)
    lower = StubTriggeredStory(
        "lower", importance=StoryImportance.IMPORTANT, priority=3
    )
    selector = trigger_selector(new, lower, old)
    assert selector.select(context(ready_state())).story_id == "new"

    alpha = StubTriggeredStory("alpha", importance=StoryImportance.IMPORTANT)
    beta = StubTriggeredStory("beta", importance=StoryImportance.IMPORTANT)
    deterministic = trigger_selector(beta, alpha)
    assert deterministic.select(context(ready_state())).story_id == "alpha"

    randomised = trigger_selector(
        StubTriggeredStory("alpha"),
        StubTriggeredStory("beta"),
        random_source=LastChoiceRandom(),
    )
    assert randomised.select(context(ready_state())).story_id == "beta"


def test_cooldowns_spacing_visit_limit_and_important_override() -> None:
    fun = StubTriggeredStory(
        "fun",
        cooldown=timedelta(days=1),
        min_since_any_story=timedelta(hours=2),
        min_since_fun_story=timedelta(hours=12),
    )
    selector = trigger_selector(fun)
    blocked = ready_state(
        story_executions={
            "fun": StoryExecutionState(last_started_at=(NOW - timedelta(hours=23)).isoformat())
        }
    )
    assert selector.select(context(blocked)) is None

    exact_boundary = ready_state(
        story_executions={
            "fun": StoryExecutionState(last_started_at=(NOW - timedelta(days=1)).isoformat())
        },
        story_activity=StoryActivityState(
            last_story_started_at=(NOW - timedelta(hours=2)).isoformat(),
            last_fun_started_at=(NOW - timedelta(hours=12)).isoformat(),
        ),
    )
    assert selector.select(context(exact_boundary)) is not None

    recently_important = replace(
        exact_boundary,
        story_activity=replace(
            exact_boundary.story_activity,
            last_important_started_at=(NOW - timedelta(hours=3)).isoformat(),
        ),
    )
    assert selector.select(context(recently_important)) is None

    important = StubTriggeredStory("important", importance=StoryImportance.IMPORTANT)
    override = trigger_selector(important)
    used_visit = {OPTIONAL_STORY_STARTED_THIS_VISIT_KEY: "something"}
    assert override.select(context(ready_state(), session=used_visit)) is not None


def test_active_trigger_story_resumes_even_when_trigger_is_no_longer_eligible() -> None:
    story = StubTriggeredStory("active", enabled=False, outcome=None)
    director = AssistantDirector(RecordingPersistence(), {"active": story})
    state = ready_state(story="active", scene="entry", status="active")

    assert director.story_dispatch(context(state), None) is story


def test_optional_story_visit_count_is_cleared_only_on_a_new_visit() -> None:
    session = {OPTIONAL_STORY_STARTED_THIS_VISIT_KEY: 1}

    clear_transcript_for_new_help_visit(session, "assistant")
    assert session[OPTIONAL_STORY_STARTED_THIS_VISIT_KEY] == 1

    clear_transcript_for_new_help_visit(session, "goals")
    assert OPTIONAL_STORY_STARTED_THIS_VISIT_KEY not in session


def test_render_persists_start_completion_activity_and_event_consumption() -> None:
    story = StubTriggeredStory(
        "event-story",
        importance=StoryImportance.IMPORTANT,
        event_id="event.ready",
        consume_trigger_on="completion",
    )
    persistence = RecordingPersistence()
    director = AssistantDirector(persistence, {story.story_id: story})
    state = ready_state(events={"event.ready": {"payload": 3}})

    result = director.render(context(state), RecordingView())

    execution = result.story_executions[story.story_id]
    assert execution.starts == 1
    assert execution.completions == 1
    assert execution.last_started_at == NOW.isoformat()
    assert execution.last_completed_at == NOW.isoformat()
    assert execution.pending_event_id is None
    assert result.story_activity.last_story_id == story.story_id
    assert result.story_activity.last_story_type == "important"
    assert result.events["event.ready"] == {
        "payload": 3,
        "consumed_at": NOW.isoformat(),
        "consumed_by": story.story_id,
    }
    assert persistence.saved_states


def test_dismissal_is_recorded_and_start_consumes_event() -> None:
    story = StubTriggeredStory(
        "dismissed-story",
        importance=StoryImportance.IMPORTANT,
        event_id="event.ready",
        outcome="dismissed",
        consume_trigger_on="start",
    )
    result = AssistantDirector(RecordingPersistence(), {story.story_id: story}).render(
        context(ready_state(events={"event.ready": {}})), RecordingView()
    )

    execution = result.story_executions[story.story_id]
    assert execution.starts == 1
    assert execution.completions == 0
    assert execution.last_dismissed_at == NOW.isoformat()
    assert execution.pending_event_id == "event.ready"
    assert result.events["event.ready"]["consumed_by"] == story.story_id


def test_schema_v2_upgrade_preserves_conversation_and_normalises_execution_data() -> None:
    upgraded = AssistantState.from_value(
        {
            "schema_version": 2,
            "mode": "normal",
            "story": "some-story",
            "scene": "middle",
            "status": "active",
            "stars": 7,
            "story_executions": {
                "valid": {
                    "starts": "2",
                    "last_started_at": "2026-08-06T12:00:00",
                    "last_completed_at": "not-a-date",
                    "pending_trigger": {"event_id": "legacy.event"},
                }
            },
            "story_activity": {"last_story_started_at": "not-a-date"},
        }
    )

    assert upgraded.story == "some-story"
    assert upgraded.scene == "middle"
    assert upgraded.status == "active"
    assert upgraded.stars == 7
    assert upgraded.story_executions["valid"].starts == 2
    assert upgraded.story_executions["valid"].last_started_at.endswith("+00:00")
    assert upgraded.story_executions["valid"].last_completed_at is None
    assert upgraded.story_executions["valid"].pending_event_id == "legacy.event"
    assert upgraded.story_activity.last_story_started_at is None
