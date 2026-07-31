from datetime import datetime, timezone

from src.assistant.core import AssistantContext, AssistantSelection
from src.assistant.director import AssistantDirector
from src.assistant.state import AssistantState
from src.assistant.stories import default_stories
from src.assistant.stories.weekly_summary import SUMMARY_SCENE, WEEK_SELECTION_EVENT_ID
from src.assistant.stories.weekly_summary_ready import (
    WEEKLY_SUMMARY_READY_EVENT_ID,
    WEEKLY_SUMMARY_READY_SCENE,
    WEEKLY_SUMMARY_READY_STORY_ID,
    WEEKLY_SUMMARY_READY_TOAST,
    WEEKLY_SUMMARY_READY_TOAST_ICON,
    refresh_weekly_summary_ready_event,
    weekly_summary_ready_toast_key,
    weekly_summary_ready_event,
    WeeklySummaryReadyStory,
)


class RecordingPersistence:
    def __init__(self) -> None:
        self.saved = []

    def save_assistant_state(self, user_id, assistant_state, now=None):
        del user_id, now
        state = AssistantState.from_value(assistant_state)
        self.saved.append(state)
        return state.to_dict()


class RecordingView:
    waiting_for_input = False
    selection = None

    def __init__(self) -> None:
        self.turns = []

    def present(self, turn) -> None:
        self.turns.append(turn)

    def finish(self) -> None:
        pass


def _now(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_ready_event_is_created_for_last_final_week_and_rolls_over_once() -> None:
    persistence = RecordingPersistence()
    user = {"created_at": "2026-07-01T00:00:00+00:00"}

    first = refresh_weekly_summary_ready_event(persistence, user, "alice", now=_now("2026-07-27T12:00:00"))

    assert first.events[WEEKLY_SUMMARY_READY_EVENT_ID] == {
        "week_start": "2026-07-20", "acknowledged": False
    }
    # Tuesday retains the same durable entry, including its acknowledgement.
    user["assistant_state"] = AssistantState(
        events={WEEKLY_SUMMARY_READY_EVENT_ID: {"week_start": "2026-07-20", "acknowledged": True}}
    ).to_dict()
    refresh_weekly_summary_ready_event(persistence, user, "alice", now=_now("2026-07-28T12:00:00"))
    assert AssistantState.from_profile(user).events[WEEKLY_SUMMARY_READY_EVENT_ID]["acknowledged"] is True

    rolled = refresh_weekly_summary_ready_event(persistence, user, "alice", now=_now("2026-08-03T12:00:00"))
    assert rolled.events == {WEEKLY_SUMMARY_READY_EVENT_ID: {"week_start": "2026-07-27", "acknowledged": False}}
    assert len(persistence.saved) == 2


def test_ready_event_is_not_created_before_a_closed_week() -> None:
    persistence = RecordingPersistence()
    new_user = {"created_at": "2026-07-25T12:00:00+00:00"}
    assert not refresh_weekly_summary_ready_event(persistence, new_user, "alice", now=_now("2026-07-27T12:00:00")).events
    assert not persistence.saved


def test_ready_event_is_created_on_any_day_for_the_latest_completed_week() -> None:
    persistence = RecordingPersistence()
    user = {"created_at": "2026-07-01T00:00:00+00:00"}

    state = refresh_weekly_summary_ready_event(
        persistence, user, "alice", now=_now("2026-07-29T12:00:00")
    )

    assert state.events[WEEKLY_SUMMARY_READY_EVENT_ID] == {
        "week_start": "2026-07-20", "acknowledged": False
    }


def test_pending_ready_event_toasts_once_per_session() -> None:
    assert WEEKLY_SUMMARY_READY_TOAST == "**Important Info**  \nI have your analysis of last week ready."
    assert WEEKLY_SUMMARY_READY_TOAST_ICON == ":material/support_agent:"
    state = AssistantState(events={WEEKLY_SUMMARY_READY_EVENT_ID: {"week_start": "2026-07-20", "acknowledged": False}})
    assert weekly_summary_ready_toast_key("alice", state) == "weekly_summary.ready:alice:2026-07-20"
    assert weekly_summary_ready_toast_key("bob", state) == "weekly_summary.ready:bob:2026-07-20"
    acknowledged = AssistantState(events={WEEKLY_SUMMARY_READY_EVENT_ID: {"week_start": "2026-07-20", "acknowledged": True}})
    assert weekly_summary_ready_toast_key("alice", acknowledged) is None


def test_ready_story_acknowledges_then_opens_last_final_week_summary() -> None:
    state = AssistantState(events={WEEKLY_SUMMARY_READY_EVENT_ID: {"week_start": "2026-07-20", "acknowledged": False}})
    context = AssistantContext(user_id="alice", current_user={}, state=state, session_state={}, current_page_key="assistant", now=_now("2026-07-27T12:00:00"), user_state={"goals": []})
    story = WeeklySummaryReadyStory()

    opening = story.advance(context, None, None)
    assert opening is not None
    assert opening.lines[0].text == "I have your last week’s progress prepared."
    assert [choice.label for choice in opening.choices] == ["Show it to me", "Not interested, but thanks"]

    shown = story.advance(context, WEEKLY_SUMMARY_READY_SCENE, AssistantSelection(WEEKLY_SUMMARY_READY_STORY_ID, WEEKLY_SUMMARY_READY_SCENE, "show", "Show it to me"))
    assert shown is not None
    assert shown.scene_id == SUMMARY_SCENE
    assert shown.event_updates[WEEKLY_SUMMARY_READY_EVENT_ID]["acknowledged"] is True
    assert shown.event_updates[WEEK_SELECTION_EVENT_ID] == {"start": "2026-07-20", "partial": False}


def test_ready_story_has_priority_when_assistant_opens() -> None:
    state = AssistantState(events={WEEKLY_SUMMARY_READY_EVENT_ID: {"week_start": "2026-07-20", "acknowledged": False}})
    context = AssistantContext(user_id="alice", current_user={}, state=state, session_state={}, current_page_key="assistant")
    view = RecordingView()

    AssistantDirector(RecordingPersistence(), default_stories()).render(context, view)

    assert view.turns[0].story_id == WEEKLY_SUMMARY_READY_STORY_ID


def test_ready_story_decline_acknowledges_and_leaves() -> None:
    state = AssistantState(events={WEEKLY_SUMMARY_READY_EVENT_ID: {"week_start": "2026-07-20", "acknowledged": False}})
    context = AssistantContext(user_id="alice", current_user={}, state=state, session_state={}, current_page_key="assistant")
    turn = WeeklySummaryReadyStory().advance(context, None, AssistantSelection(WEEKLY_SUMMARY_READY_STORY_ID, WEEKLY_SUMMARY_READY_SCENE, "decline", "Not interested, but thanks"))
    assert turn is not None
    assert turn.assistant_leaves and turn.completed
    assert turn.event_updates[WEEKLY_SUMMARY_READY_EVENT_ID]["acknowledged"] is True
