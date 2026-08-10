from datetime import datetime, timezone

from scripts.migration_restore_dismissed_assistants import (
    planned_repairs,
    repaired_assistant_state,
)
from src.assistant.core import AssistantContext
from src.assistant.director import AssistantDirector
from src.assistant.state import AssistantState, StoryExecutionState
from src.assistant.stories import default_stories
from src.assistant.stories.information import (
    GOAL_INVITATION_EVENT_ID,
    INFORMATION_STORY_ID,
)
from src.assistant.stories.tutorial import READY_NODE, STANDARD_STORY_ID


def dismissed_state() -> dict:
    return AssistantState(
        stars=3,
        knowledge={"reward": True},
        events={
            GOAL_INVITATION_EVENT_ID: {
                "invitations": [
                    {
                        "goal_id": "goal-1",
                        "inviter_name": "Bob",
                        "goal_name": "Run",
                        "schedule_class": "daily",
                        "required_periods": "1",
                        "target": "5",
                        "friend_participant_count": "1",
                    }
                ]
            }
        },
        status="dismissed",
        story_executions={"past": StoryExecutionState(starts=1)},
    ).to_dict()


def test_repair_preserves_durable_data_and_dispatches_pending_information() -> None:
    repaired = repaired_assistant_state(dismissed_state())

    assert repaired is not None
    assert repaired["status"] == "completed"
    assert repaired["story"] == STANDARD_STORY_ID
    assert repaired["scene"] == READY_NODE
    assert repaired["stars"] == 3
    assert repaired["knowledge"] == {"reward": True}
    assert repaired["story_executions"]["past"]["starts"] == 1

    state = AssistantState.from_value(repaired)
    story = AssistantDirector(object(), default_stories()).story_dispatch(
        AssistantContext(
            user_id="alice",
            current_user={"user_id": "alice"},
            state=state,
            session_state={},
            current_page_key="assistant",
            now=datetime(2026, 8, 10, 12, tzinfo=timezone.utc),
        ),
        None,
    )

    assert story is not None
    assert story.story_id == INFORMATION_STORY_ID


def test_repair_planning_selects_only_dismissed_states_and_is_idempotent() -> None:
    repairs = planned_repairs(
        [
            {"_id": "blocked", "assistant_state": dismissed_state()},
            {"_id": "normal", "assistant_state": AssistantState().to_dict()},
            {"_id": "missing"},
        ]
    )

    assert set(repairs) == {"blocked"}
    assert planned_repairs([{"_id": "blocked", "assistant_state": repairs["blocked"]}]) == {}
