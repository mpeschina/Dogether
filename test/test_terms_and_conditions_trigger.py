from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.assistant.core import AssistantContext, AssistantSelection
from src.assistant.state import AssistantState, StoryActivityState, StoryExecutionState
from src.assistant.stories.triggered import (
    TermsAndConditionsStory,
    triggered_stories,
)
from src.assistant.stories.triggered.terms_and_conditions import (
    ANNOYING_SCENE,
    CLOSING_SCENE,
    COMPLETE_SCENE,
    DOCUMENT_SCENE,
    FAIR_SCENE,
    INTRO_SCENE,
    OBJECTION_SCENE,
    REASONABLE_SCENE,
    RIDICULOUS_SCENE,
    TERMS_AND_CONDITIONS_STORY_ID,
)
from src.assistant.triggers import TriggerStorySelector


NOW = datetime(2026, 8, 7, 12, tzinfo=timezone.utc)
DEFAULT_CREATED_AT = object()


def context(
    *,
    now: datetime = NOW,
    created_at: object = DEFAULT_CREATED_AT,
    state: AssistantState | None = None,
) -> AssistantContext:
    profile = {"user_id": "alice"}
    if created_at is not DEFAULT_CREATED_AT and created_at is not None:
        profile["created_at"] = created_at
    elif created_at is DEFAULT_CREATED_AT:
        profile["created_at"] = (now - timedelta(days=5)).isoformat()
    return AssistantContext(
        user_id="alice",
        current_user=profile,
        state=state
        or AssistantState(story="standard", scene="ready", status="completed"),
        session_state={},
        current_page_key="assistant",
        previous_page_key="assistant",
        now=now,
    )


def selection(turn, choice_id: str) -> AssistantSelection:
    return AssistantSelection(turn.story_id, turn.scene_id, choice_id, "")


@pytest.mark.parametrize(
    ("now", "expected"),
    (
        (NOW - timedelta(microseconds=1), False),
        (NOW, True),
        (NOW + timedelta(days=1), True),
    ),
)
def test_terms_trigger_starts_at_the_exact_five_day_boundary(
    now: datetime, expected: bool
) -> None:
    created_at = NOW - timedelta(days=5)
    assert TermsAndConditionsStory().is_triggered(
        context(now=now, created_at=created_at.isoformat())
    ) is expected


@pytest.mark.parametrize("created_at", (None, "", "not-a-date", "2026-08-02T12:00:00"))
def test_terms_trigger_rejects_missing_or_invalid_account_dates(created_at: object) -> None:
    assert not TermsAndConditionsStory().is_triggered(context(created_at=created_at))


def test_terms_story_is_discovered_and_only_starts_once() -> None:
    story = triggered_stories()[TERMS_AND_CONDITIONS_STORY_ID]
    assert isinstance(story, TermsAndConditionsStory)

    used = replace(
        context().state,
        story_executions={story.story_id: StoryExecutionState(starts=1)},
    )
    assert TriggerStorySelector({story.story_id: story}).select(context(state=used)) is None


def test_terms_story_waits_eight_hours_after_any_story() -> None:
    story = TermsAndConditionsStory()
    selector = TriggerStorySelector({story.story_id: story})
    recent = NOW - timedelta(hours=7, minutes=59)
    after_any_story = replace(
        context(now=NOW).state,
        story_activity=StoryActivityState(
            last_story_id="another-story",
            last_story_type="core",
            last_story_started_at=recent.isoformat(),
        ),
    )

    assert selector.select(context(state=after_any_story)) is None
    assert (
        selector.select(context(now=NOW + timedelta(minutes=1), state=after_any_story))
        is story
    )


def test_terms_flow_renders_the_document_and_reasonable_branch() -> None:
    story = TermsAndConditionsStory()
    current = context()
    intro = story.advance(current, None, None)
    document = story.advance(current, intro.scene_id, selection(intro, "continue"))
    reasonable = story.advance(
        current, document.scene_id, selection(document, "reasonable")
    )
    closing = story.advance(
        current, reasonable.scene_id, selection(reasonable, "continue")
    )
    completed = story.advance(current, closing.scene_id, selection(closing, "agree"))

    assert intro.scene_id == INTRO_SCENE
    assert document.scene_id == DOCUMENT_SCENE
    assert document.content
    assert reasonable.scene_id == REASONABLE_SCENE
    assert closing.scene_id == CLOSING_SCENE
    assert completed.scene_id == COMPLETE_SCENE
    assert completed.completed
    assert completed.execution_outcome == "completed"
    assert completed.assistant_leaves


@pytest.mark.parametrize(
    ("objection_response", "expected_scene"),
    (("fair_enough", FAIR_SCENE), ("still_annoying", ANNOYING_SCENE)),
)
def test_terms_ridiculous_objection_branches_rejoin_at_closing(
    objection_response: str, expected_scene: str
) -> None:
    story = TermsAndConditionsStory()
    current = context()
    document = story.advance(current, DOCUMENT_SCENE, None)
    ridiculous = story.advance(
        current, document.scene_id, selection(document, "ridiculous")
    )
    objection = story.advance(
        current, ridiculous.scene_id, selection(ridiculous, "object")
    )
    resolution = story.advance(
        current, objection.scene_id, selection(objection, objection_response)
    )
    closing = story.advance(
        current, resolution.scene_id, selection(resolution, "continue")
    )

    assert ridiculous.scene_id == RIDICULOUS_SCENE
    assert objection.scene_id == OBJECTION_SCENE
    assert resolution.scene_id == expected_scene
    assert closing.scene_id == CLOSING_SCENE


def test_terms_ridiculous_fine_branch_rejoins_at_closing() -> None:
    story = TermsAndConditionsStory()
    current = context()
    ridiculous = story.advance(
        current,
        DOCUMENT_SCENE,
        AssistantSelection(story.story_id, DOCUMENT_SCENE, "ridiculous", ""),
    )
    closing = story.advance(
        current, ridiculous.scene_id, selection(ridiculous, "fine")
    )

    assert closing.scene_id == CLOSING_SCENE
