from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.assistant import director as assistant_director
from src.assistant.core import AssistantChoice, AssistantContext, AssistantSelection, AssistantTurn
from src.assistant.director import AssistantDirector, apply_turn
from src.assistant.presentation import (
    ACTIVE_CONTROL_KEY,
    CONTROL_ROUND_KEY,
    PERSIST_TRANSCRIPT_ACROSS_PAGE_HOPS_KEY,
    TRANSCRIPT_KEY,
    clear_transcript_for_new_help_visit,
)
from src.assistant.state import (
    ASSISTANT_STATE_SCHEMA_VERSION,
    TRANSIENT_ASSISTANT_STATE_SESSION_KEY,
    AssistantMode,
    AssistantState,
    grant_stars,
    transient_assistant_state_for_user,
)
from src.assistant.story_session import story_session
from src.assistant.stories import default_stories
from src.assistant.stories.greetings import (
    GREETING_PENDING_KEY,
    GREETING_RANDOMIZED_AT_KEY,
    GREETING_SELECTION_KEY,
    GREETINGS_STORY_ID,
    MORNING_GREETING_DISPLAYED_ON_KEY,
    MORNING_GREETING_EVENT_ID,
    MORNING_GREETING_REPLIES,
    GreetingsStory,
)
from src.assistant.stories.push_reminder import PushReminderStory
from src.assistant.stories.information import (
    GOAL_INVITATION_EVENT_ID,
    INFORMATION_COMPLETE_KEY,
    INFORMATION_STORY_ID,
    GOAL_INVITATION_NOTIFICATIONS_UNLOCKED_KNOWLEDGE_KEY,
    _goal_fact_cards,
)
from src.assistant.stories.night import (
    NIGHT_AFTER_LEAVING_SCENE,
    NIGHT_COMPLETED_COUNT_KEY,
    NIGHT_EVENT_ID,
    NIGHT_GOOD_NIGHT_SCENE,
    NIGHT_STORY_ID,
    PROGRESS_BAR_CLICK_COUNT as NIGHT_PROGRESS_BAR_CLICK_COUNT,
    PROGRESS_BAR_COUNT as NIGHT_PROGRESS_BAR_COUNT,
    STATUS_CLICK_COUNT as NIGHT_STATUS_CLICK_COUNT,
    NightStory,
)
from src.assistant.stories.smalltalk import (
    FUNNY_SMALLTALK_RESPONSES,
    SMALLTALK_CLICKED_AT_KEY,
    SMALLTALK_OPENERS,
    SMALLTALK_OPENER_SELECTED_AT_KEY,
    SmalltalkStory,
)
from src.assistant.stories.standard import (
    PUSH_PROMPT_EVENT_ID,
    STANDARD_HELP_SCENE,
    STANDARD_MENU_SCENE,
    StandardStory,
)
from src.assistant.stories.tutorial import (
    ANALYSIS_COMPLETE_NODE,
    FRIENDS_EVENT_ID,
    FRIENDS_EXPLANATION_GOODBYE_NODE,
    FRIENDS_EXPLANATION_LINK_NODE,
    FRIENDS_EXPLANATION_NODE,
    FRIENDS_EXPLANATION_OPTIONS_NODE,
    FRIENDS_NODE,
    GOALS_EVENT_ID,
    GOALS_EXPLANATION_FINISH_NODE,
    GOALS_EXPLANATION_NODE,
    GOALS_NODE,
    PUSH_EXPLANATION_FINISH_NODE,
    PUSH_EXPLANATION_NODE,
    PUSH_EVENT_ID,
    PUSH_NODE,
    PROFILE_ANALYSIS_KNOWLEDGE_KEY,
    READY_NODE,
    RESUME_NODE,
    STANDARD_STORY_ID,
    TOUR_NODE,
    TUTORIAL_STORY_ID,
    WELCOME_NODE,
    InitialTutorialStory,
)
from src.db.persistence_helpers import APP_ZONE


class RecordingPersistence:
    def __init__(self) -> None:
        self.saved_states: list[dict] = []
        self.completed_night_events = 0

    def save_assistant_state(self, user_id, assistant_state, now=None):
        del user_id, now
        stored = AssistantState.from_value(assistant_state).to_dict()
        self.saved_states.append(stored)
        return stored

    def increment_completed_night_events(self, user_id, now=None):
        del user_id, now
        self.completed_night_events += 1
        return self.completed_night_events


class RecordingView:
    def __init__(
        self,
        selection: AssistantSelection | None = None,
        *,
        waiting: bool = False,
    ) -> None:
        self.selection = selection
        self.waiting_for_input = waiting
        self.turns = []
        self.finished = False

    def present(self, turn):
        self.turns.append(turn)

    def finish(self):
        self.finished = True

class StubRandom:
    def __init__(self, roll: float, choice_index: int = 0) -> None:
        self.roll = roll
        self.choice_index = choice_index

    def random(self) -> float:
        return self.roll

    def choice(self, choices):
        return choices[self.choice_index]


def context_for(
    state: AssistantState,
    *,
    profile: dict | None = None,
    previous_page_key: str | None = "assistant",
    user_state: dict | None = None,
    session_state: dict | None = None,
    create_friend_share_link=None,
    record_night_event_completion=None,
    now: datetime | None = None,
) -> AssistantContext:
    return AssistantContext(
        user_id="alice",
        current_user=profile if profile is not None else {"user_id": "alice"},
        state=state,
        session_state=session_state if session_state is not None else {},
        current_page_key="assistant",
        previous_page_key=previous_page_key,
        user_state=user_state or {},
        create_friend_share_link=create_friend_share_link,
        record_night_event_completion=record_night_event_completion,
        now=now,
    )


def selection(story: str, scene: str, choice_id: str, label: str | None = None):
    return AssistantSelection(
        story_id=story,
        scene_id=scene,
        choice_id=choice_id,
        label=label or choice_id,
    )


def test_schema_v2_normalizes_legacy_completed_and_unfinished_state() -> None:
    completed = AssistantState.from_value(
        {
            "schema_version": 1,
            "mode": "normal",
            "flow": "standard",
            "node": "ready",
            "status": "completed",
            "knowledge": {"seen": True},
            "events": {"push": {"dismissed_count": 2}},
        }
    )
    assert completed.schema_version == ASSISTANT_STATE_SCHEMA_VERSION
    assert completed.story == STANDARD_STORY_ID
    assert completed.scene == READY_NODE
    assert completed.knowledge == {"seen": True}
    assert completed.events["push"]["dismissed_count"] == 2

    unfinished = AssistantState.from_value(
        {
            "schema_version": 1,
            "flow": "onboarding_analysis",
            "node": "goals.explain",
            "status": "paused",
            "knowledge": {"kept": True},
        }
    )
    assert unfinished.story is None
    assert unfinished.scene is None
    assert unfinished.status == "new"
    assert unfinished.knowledge == {"kept": True}


def test_transcript_clear_also_clears_active_control_unless_retained() -> None:
    session = {
        TRANSCRIPT_KEY: [("assistant", "Hello")],
        ACTIVE_CONTROL_KEY: {"round_id": 1},
        CONTROL_ROUND_KEY: 1,
    }
    story_session(session, INFORMATION_STORY_ID).set(INFORMATION_COMPLETE_KEY, True)
    clear_transcript_for_new_help_visit(session, "goals")
    assert TRANSCRIPT_KEY not in session
    assert ACTIVE_CONTROL_KEY not in session
    assert CONTROL_ROUND_KEY not in session
    assert story_session(session, INFORMATION_STORY_ID).get(INFORMATION_COMPLETE_KEY) is None

    retained = {
        TRANSCRIPT_KEY: [("assistant", "Hello")],
        ACTIVE_CONTROL_KEY: {"round_id": 2},
        PERSIST_TRANSCRIPT_ACROSS_PAGE_HOPS_KEY: True,
    }
    clear_transcript_for_new_help_visit(retained, "goals")
    assert retained[TRANSCRIPT_KEY] == [("assistant", "Hello")]
    assert retained[ACTIVE_CONTROL_KEY] == {"round_id": 2}


def test_director_initializes_welcome_once_and_waiting_rerun_is_inert() -> None:
    persistence = RecordingPersistence()
    session = {}
    director = AssistantDirector(persistence, default_stories())
    initial = RecordingView()

    state = director.render(
        context_for(AssistantState(), session_state=session, previous_page_key="goals"),
        initial,
    )

    assert state.story == TUTORIAL_STORY_ID
    assert state.scene == WELCOME_NODE
    assert state.status == "paused"
    assert [line.text for line in initial.turns[0].lines] == [
        "Hi, welcome!",
        "Great to have you here.",
        "Want some help?",
    ]
    assert transient_assistant_state_for_user(session, "alice") == state
    assert persistence.saved_states == []

    waiting = RecordingView(waiting=True)
    unchanged = director.render(context_for(state, session_state=session), waiting)
    assert unchanged == state
    assert waiting.turns == []
    assert waiting.finished


def test_information_story_preempts_other_stories_and_clears_combined_news() -> None:
    persistence = RecordingPersistence()
    session = {}
    state = AssistantState(
        story=STANDARD_STORY_ID,
        scene=READY_NODE,
        status="completed",
        events={
            GOAL_INVITATION_EVENT_ID: {"invitations": [
                {"goal_id": "goal-one", "inviter_name": "Bob"},
                {"goal_id": "goal-two", "inviter_name": "Charlie"},
            ]}
        },
    )
    director = AssistantDirector(persistence, default_stories())
    initial = RecordingView()
    paused = director.render(
        context_for(
            state,
            session_state=session,
            now=datetime(2026, 7, 27, 12, tzinfo=APP_ZONE),
        ),
        initial,
    )

    assert initial.turns[0].story_id == INFORMATION_STORY_ID
    assert [item.text for item in initial.turns[0].content if hasattr(item, "text")][3:6] == [
        "You have your 3rd shared Goal!",
        "I got one STAR reward for it, thank you so much.",
        "This enables me to inform you on new goal invites, from now on.",
    ]
    assert [item.text for item in initial.turns[0].content if hasattr(item, "text")][:3] == [
        "Hello.",
        "I have important news for you.",
        "Bob and Charlie invited you to 2 new shared goals.",
    ]
    assert len(initial.turns[0].content) == 8
    assert paused.story == INFORMATION_STORY_ID
    assert paused.stars == 0
    assert paused.knowledge[GOAL_INVITATION_NOTIFICATIONS_UNLOCKED_KNOWLEDGE_KEY] is True
    assert persistence.saved_states[-1]["knowledge"][GOAL_INVITATION_NOTIFICATIONS_UNLOCKED_KNOWLEDGE_KEY] is True
    assert persistence.saved_states[-1]["stars"] == 0

    acknowledged = RecordingView(selection(INFORMATION_STORY_ID, "goal_invitations", "acknowledge"))
    completed = director.render(
        context_for(
            paused,
            session_state=session,
            now=datetime(2026, 7, 27, 12, tzinfo=APP_ZONE),
        ),
        acknowledged,
    )
    assert acknowledged.turns[0].assistant_leaves is True
    assert GOAL_INVITATION_EVENT_ID not in completed.events
    assert completed.story == STANDARD_STORY_ID
    assert story_session(session, INFORMATION_STORY_ID).get(INFORMATION_COMPLETE_KEY) is True
    assert completed.stars == 0


def test_information_card_hides_a_single_friend_participant() -> None:
    card = _goal_fact_cards([
        {
            "goal_id": "goal-one", "inviter_name": "Bob", "goal_name": "Walk",
            "schedule_class": "daily", "required_periods": "1", "target": "4",
            "friend_participant_count": "1",
        }
    ])[0]
    assert "Friends already participating" not in dict(card.rows)


def test_grant_stars_returns_updated_assistant_state() -> None:
    state = AssistantState(stars=2)

    granted = grant_stars(state)

    assert state.stars == 2
    assert granted.stars == 3
    assert grant_stars(granted, 0).stars == 3


def test_information_story_does_not_repeat_goal_notification_unlock_intro() -> None:
    persistence = RecordingPersistence()
    state = AssistantState(
        story=STANDARD_STORY_ID,
        scene=READY_NODE,
        status="completed",
        knowledge={GOAL_INVITATION_NOTIFICATIONS_UNLOCKED_KNOWLEDGE_KEY: True},
        events={
            GOAL_INVITATION_EVENT_ID: {
                "invitations": [{"goal_id": "goal-three", "inviter_name": "Bob"}]
            }
        },
    )
    view = RecordingView()

    AssistantDirector(persistence, default_stories()).render(
        context_for(state, now=datetime(2026, 7, 27, 12, tzinfo=APP_ZONE)),
        view,
    )

    lines = [item.text for item in view.turns[0].content if hasattr(item, "text")]
    assert lines == [
        "Hello.",
        "I have important news for you.",
        "Bob invited you to a new shared goal.",
    ]


def test_one_selection_advances_and_renders_the_next_stable_round() -> None:
    persistence = RecordingPersistence()
    director = AssistantDirector(persistence, default_stories())
    state = AssistantState(
        story=TUTORIAL_STORY_ID,
        scene=WELCOME_NODE,
        status="paused",
    )
    view = RecordingView(
        selection(TUTORIAL_STORY_ID, WELCOME_NODE, "analyse_profile")
    )

    updated = director.render(
        context_for(state, user_state={"friend_count": 0}),
        view,
    )

    assert updated.scene == FRIENDS_NODE
    assert view.turns[-1].scene_id == FRIENDS_NODE
    assert [choice.label for choice in view.turns[-1].choices] == [
        "Invite a friend",
        "Explain the Friendlist to me",
        "I did already, lets move on",
    ]


def test_choice_ids_are_independent_from_tutorial_labels() -> None:
    story = InitialTutorialStory()
    context = context_for(AssistantState(story=TUTORIAL_STORY_ID, scene=WELCOME_NODE))

    prompt = story.advance(context, WELCOME_NODE, None)
    assert prompt.choices[0].id == "analyse_profile"
    relabelled = replace(prompt.choices[0], label="Review my account")
    assert relabelled.id == "analyse_profile"

    selected = story.advance(
        context,
        WELCOME_NODE,
        selection(TUTORIAL_STORY_ID, WELCOME_NODE, relabelled.id, relabelled.label),
    )
    assert selected.state_scene == FRIENDS_NODE


def test_unknown_tutorial_choice_reprompts_current_scene() -> None:
    story = InitialTutorialStory()
    context = context_for(AssistantState(story=TUTORIAL_STORY_ID, scene=WELCOME_NODE))

    turn = story.advance(
        context,
        WELCOME_NODE,
        selection(TUTORIAL_STORY_ID, WELCOME_NODE, "old-visible-label"),
    )

    assert turn.scene_id == WELCOME_NODE
    assert turn.state_scene == WELCOME_NODE
    assert [choice.id for choice in turn.choices] == ["analyse_profile", "tour", "decline"]


def test_finishing_tour_returns_to_the_remaining_welcome_options() -> None:
    story = InitialTutorialStory()
    context = context_for(AssistantState(story=TUTORIAL_STORY_ID, scene=TOUR_NODE))

    turn = story.advance(
        context,
        TOUR_NODE,
        selection(TUTORIAL_STORY_ID, TOUR_NODE, "finish", "Got it"),
    )

    assert turn.scene_id == WELCOME_NODE
    assert turn.state_scene == WELCOME_NODE
    assert [choice.id for choice in turn.choices] == ["analyse_profile", "decline"]
    assert [choice.label for choice in turn.choices] == ["Analyse my profile", "Exit"]


def test_choices_require_non_empty_unique_ids() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        AssistantChoice("", "Continue")
    with pytest.raises(ValueError, match="unique"):
        AssistantTurn(
            story_id="test",
            scene_id="test.scene",
            choices=(AssistantChoice("continue", "Continue"), AssistantChoice("continue", "Next")),
        )


def test_declining_welcome_completes_durably() -> None:
    persistence = RecordingPersistence()
    profile = {"user_id": "alice"}
    director = AssistantDirector(persistence, default_stories())
    state = AssistantState(
        story=TUTORIAL_STORY_ID,
        scene=WELCOME_NODE,
        status="paused",
    )
    view = RecordingView(selection(TUTORIAL_STORY_ID, WELCOME_NODE, "decline"))

    completed = director.render(context_for(state, profile=profile), view)

    assert completed.story == STANDARD_STORY_ID
    assert completed.scene == READY_NODE
    assert completed.status == "declined"
    assert view.turns[-1].assistant_leaves
    assert persistence.saved_states == [completed.to_dict()]


def test_resume_scene_preserves_interrupted_scene_or_restarts() -> None:
    story = InitialTutorialStory()
    state = AssistantState(
        story=TUTORIAL_STORY_ID,
        scene=GOALS_NODE,
        status="paused",
    )
    context = context_for(state, previous_page_key="goals")
    assert story.entry_scene(context) == RESUME_NODE

    resumed = story.advance(
        context,
        RESUME_NODE,
        selection(TUTORIAL_STORY_ID, RESUME_NODE, "continue"),
    )
    assert resumed.state_scene == GOALS_NODE
    assert resumed.continue_flow

    restarted = story.advance(
        context,
        RESUME_NODE,
        selection(TUTORIAL_STORY_ID, RESUME_NODE, "restart"),
    )
    assert restarted.state_scene == WELCOME_NODE


def test_profile_checks_follow_friends_goals_push_analysis_order() -> None:
    story = InitialTutorialStory()
    state = AssistantState(story=TUTORIAL_STORY_ID, scene=FRIENDS_NODE, status="active")

    friends = story.advance(
        context_for(state, user_state={"friend_count": 2}),
        FRIENDS_NODE,
        None,
    )
    state = apply_turn(state, friends)
    assert state.scene == GOALS_NODE

    goals = story.advance(
        context_for(state, user_state={"goal_count": 1}),
        GOALS_NODE,
        None,
    )
    state = apply_turn(state, goals)
    assert state.scene == PUSH_NODE

    push = story.advance(
        context_for(state, user_state={"push_enabled": True}),
        PUSH_NODE,
        None,
    )
    state = apply_turn(state, push)
    assert state.scene == ANALYSIS_COMPLETE_NODE


def test_friend_explanation_is_explicit_and_can_create_link() -> None:
    story = InitialTutorialStory()
    state = AssistantState(
        story=TUTORIAL_STORY_ID,
        scene=FRIENDS_EXPLANATION_NODE,
        status="active",
    )
    context = context_for(
        state,
        create_friend_share_link=lambda: "https://dogether.example/friend?share=abc",
    )

    intro = story.advance(context, FRIENDS_EXPLANATION_NODE, None)
    assert intro.state_scene == FRIENDS_EXPLANATION_NODE
    next_turn = story.advance(
        context,
        FRIENDS_EXPLANATION_NODE,
        selection(TUTORIAL_STORY_ID, FRIENDS_EXPLANATION_NODE, "skip"),
    )
    assert next_turn.state_scene == FRIENDS_EXPLANATION_OPTIONS_NODE

    link = story.advance(
        context,
        FRIENDS_EXPLANATION_LINK_NODE,
        selection(
            TUTORIAL_STORY_ID,
            FRIENDS_EXPLANATION_LINK_NODE,
            "create_link",
        ),
    )
    assert link.state_scene == FRIENDS_EXPLANATION_GOODBYE_NODE
    assert "https://dogether.example/friend?share=abc" in link.lines[0].text


def test_friend_explanation_continues_profile_analysis_in_onboarding() -> None:
    story = InitialTutorialStory()
    state = AssistantState(
        story=TUTORIAL_STORY_ID,
        scene=FRIENDS_EXPLANATION_GOODBYE_NODE,
        status="paused",
    )

    returned = story.advance(
        context_for(state, user_state={"friend_count": 0}),
        FRIENDS_EXPLANATION_GOODBYE_NODE,
        selection(
            TUTORIAL_STORY_ID,
            FRIENDS_EXPLANATION_GOODBYE_NODE,
            "finish",
        ),
    )

    assert returned.state_story == TUTORIAL_STORY_ID
    assert returned.state_scene == GOALS_NODE
    assert returned.state_status == "active"
    assert returned.completed is False
    assert returned.event_updates == {FRIENDS_EVENT_ID: {"outcome": "skipped"}}


def test_goal_and_notification_explanations_have_explicit_finish_scenes() -> None:
    story = InitialTutorialStory()
    state = AssistantState(story=TUTORIAL_STORY_ID, status="active")
    context = context_for(state)

    goal_intro = story.advance(context, GOALS_EXPLANATION_NODE, None)
    assert goal_intro.choices
    goal_finish = story.advance(context, GOALS_EXPLANATION_FINISH_NODE, None)
    assert [choice.label for choice in goal_finish.choices] == [
        "Create a goal",
        "Cool, thank you for the explanation.",
    ]

    push_intro = story.advance(context, PUSH_EXPLANATION_NODE, None)
    assert push_intro.choices
    push_finish = story.advance(context, PUSH_EXPLANATION_FINISH_NODE, None)
    assert [choice.label for choice in push_finish.choices] == [
        "Enable notifications",
        "Show me Manage Goals",
        "Cool, thank you for the explanation.",
    ]


def test_profile_analysis_resumes_after_goal_and_notification_explanations() -> None:
    story = InitialTutorialStory()

    goal_context = context_for(
        AssistantState(
            story=TUTORIAL_STORY_ID,
            scene=GOALS_EXPLANATION_FINISH_NODE,
            status="paused",
        )
    )
    after_goals = story.advance(
        goal_context,
        GOALS_EXPLANATION_FINISH_NODE,
        selection(
            TUTORIAL_STORY_ID,
            GOALS_EXPLANATION_FINISH_NODE,
            "finish",
        ),
    )
    assert after_goals.state_scene == PUSH_NODE
    assert after_goals.event_updates == {GOALS_EVENT_ID: {"outcome": "skipped"}}
    assert after_goals.completed is False

    push_context = context_for(
        AssistantState(
            story=TUTORIAL_STORY_ID,
            scene=PUSH_EXPLANATION_FINISH_NODE,
            status="paused",
        )
    )
    after_push = story.advance(
        push_context,
        PUSH_EXPLANATION_FINISH_NODE,
        selection(
            TUTORIAL_STORY_ID,
            PUSH_EXPLANATION_FINISH_NODE,
            "finish",
        ),
    )
    assert after_push.state_scene == ANALYSIS_COMPLETE_NODE
    assert after_push.event_updates == {PUSH_EVENT_ID: {"outcome": "skipped"}}
    assert after_push.completed is False


def test_standard_menu_starts_tutorial_and_tracks_knowledge() -> None:
    story = StandardStory(smalltalk_story=SmalltalkStory(random_source=StubRandom(0, 0)))
    state = AssistantState(
        story=STANDARD_STORY_ID,
        scene=READY_NODE,
        status="completed",
    )
    context = context_for(state)
    menu = story.advance(context, STANDARD_MENU_SCENE, None)
    assert [choice.label for choice in menu.choices] == [
        "Help me with the app",
        SMALLTALK_OPENERS[0],
        "Analyse my progress",
    ]

    help_menu = story.advance(
        context,
        STANDARD_MENU_SCENE,
        selection(STANDARD_STORY_ID, STANDARD_MENU_SCENE, "help", "Help me with the app"),
    )
    assert help_menu.continue_flow is False
    assert help_menu.state_scene == STANDARD_HELP_SCENE
    assert len(help_menu.lines) == 1
    assert [choice.label for choice in help_menu.choices] == ["Analyse my Profile"]

    completed_help = story.advance(
        context_for(
            AssistantState(
                story=STANDARD_STORY_ID,
                scene=READY_NODE,
                status="completed",
                knowledge={PROFILE_ANALYSIS_KNOWLEDGE_KEY: True},
            )
        ),
        STANDARD_MENU_SCENE,
        selection(STANDARD_STORY_ID, STANDARD_MENU_SCENE, "help"),
    )
    assert len(completed_help.choices) == 3

    start = story.advance(
        context,
        STANDARD_HELP_SCENE,
        selection(STANDARD_STORY_ID, STANDARD_MENU_SCENE, "analyse_profile", "Analyse my Profile"),
    )
    updated = apply_turn(state, start)
    assert updated.story == TUTORIAL_STORY_ID
    assert updated.scene == FRIENDS_NODE


def test_smalltalk_menu_choice_is_owned_by_smalltalk_story_and_returns_to_standard_menu() -> None:
    assert SMALLTALK_OPENERS
    assert len(set(SMALLTALK_OPENERS)) == len(SMALLTALK_OPENERS)

    smalltalk = SmalltalkStory(random_source=StubRandom(0, 1))
    story = StandardStory(smalltalk_story=smalltalk)
    state = AssistantState(story=STANDARD_STORY_ID, scene=READY_NODE, status="completed")
    context = context_for(state)
    menu = story.advance(context, STANDARD_MENU_SCENE, None)

    assert menu.choices[1].id == "smalltalk"
    assert menu.choices[1].label == SMALLTALK_OPENERS[1]

    placeholder = story.advance(
        context,
        STANDARD_MENU_SCENE,
        selection(STANDARD_STORY_ID, STANDARD_MENU_SCENE, "smalltalk", menu.choices[1].label),
    )
    assert [line.text for line in placeholder.lines] == [
        *FUNNY_SMALLTALK_RESPONSES[1],
    ]
    assert [choice.id for choice in placeholder.choices] == ["help", "weekly_summary"]
    assert placeholder.story_id == STANDARD_STORY_ID
    assert placeholder.scene_id == STANDARD_MENU_SCENE
    returned_state = apply_turn(state, placeholder)
    assert returned_state.story == STANDARD_STORY_ID
    assert returned_state.scene == STANDARD_MENU_SCENE

    ordinary_smalltalk = SmalltalkStory(random_source=StubRandom(0.9, 0))
    ordinary = ordinary_smalltalk.advance(context, None, None)
    assert [line.text for line in ordinary.lines] == [
        "Smalltalk is currently unavailable.",
    ]


def test_smalltalk_opener_is_session_scoped_and_refreshes_after_three_hours() -> None:
    random_source = StubRandom(0, 0)
    smalltalk = SmalltalkStory(random_source=random_source)
    state = AssistantState(story=STANDARD_STORY_ID, scene=READY_NODE, status="completed")
    session = {}
    initial = context_for(
        state,
        session_state=session,
        now=datetime(2026, 7, 26, 12, tzinfo=timezone.utc),
    )

    assert smalltalk.menu_choice(initial).label == SMALLTALK_OPENERS[0]
    assert story_session(session, "smalltalk").get(SMALLTALK_OPENER_SELECTED_AT_KEY) is not None

    random_source.choice_index = 1
    within_interval = replace(initial, now=datetime(2026, 7, 26, 14, 59, tzinfo=timezone.utc))
    assert smalltalk.menu_choice(within_interval).label == SMALLTALK_OPENERS[0]

    at_refresh = replace(initial, now=datetime(2026, 7, 26, 15, tzinfo=timezone.utc))
    assert smalltalk.menu_choice(at_refresh).label == SMALLTALK_OPENERS[1]


def test_smalltalk_choice_is_hidden_for_one_hour_after_clicking() -> None:
    random_source = StubRandom(0, 0)
    smalltalk = SmalltalkStory(random_source=random_source)
    state = AssistantState(story=STANDARD_STORY_ID, scene=READY_NODE, status="completed")
    session = {}
    initial = context_for(
        state,
        session_state=session,
        now=datetime(2026, 7, 26, 12, tzinfo=timezone.utc),
    )

    assert smalltalk.menu_choice(initial) is not None
    smalltalk.advance(initial, None, None)
    assert story_session(session, "smalltalk").get(SMALLTALK_CLICKED_AT_KEY) is not None
    assert smalltalk.menu_choice(initial) is None

    within_cooldown = replace(initial, now=datetime(2026, 7, 26, 12, 59, tzinfo=timezone.utc))
    assert smalltalk.menu_choice(within_cooldown) is None

    random_source.choice_index = 1
    after_cooldown = replace(initial, now=datetime(2026, 7, 26, 13, tzinfo=timezone.utc))
    choice = smalltalk.menu_choice(after_cooldown)
    assert choice is not None
    assert choice.label == SMALLTALK_OPENERS[1]


def test_completing_profile_analysis_unlocks_the_help_tutorial_menu() -> None:
    story = InitialTutorialStory()
    completed = story.advance(
        context_for(
            AssistantState(
                story=TUTORIAL_STORY_ID,
                scene=ANALYSIS_COMPLETE_NODE,
                status="active",
            )
        ),
        ANALYSIS_COMPLETE_NODE,
        selection(TUTORIAL_STORY_ID, ANALYSIS_COMPLETE_NODE, "finish", "Thanks!"),
    )

    assert completed.knowledge_updates == {PROFILE_ANALYSIS_KNOWLEDGE_KEY: True}


def test_help_selection_does_not_repeat_the_greeting() -> None:
    persistence = RecordingPersistence()
    stories = {
        AssistantMode.NORMAL: StandardStory(),
        "greetings": GreetingsStory(random_source=StubRandom(0.1)),
    }
    director = AssistantDirector(persistence, stories)
    state = AssistantState(
        story=STANDARD_STORY_ID,
        scene=READY_NODE,
        status="completed",
        knowledge={PROFILE_ANALYSIS_KNOWLEDGE_KEY: True},
    )

    initial_view = RecordingView()
    state = director.render(
        context_for(state, session_state={}, previous_page_key="goals"),
        initial_view,
    )
    help_view = RecordingView(
        selection(STANDARD_STORY_ID, STANDARD_MENU_SCENE, "help", "Help me with the app")
    )
    state = director.render(context_for(state, session_state={}), help_view)

    all_turns = (*initial_view.turns, *help_view.turns)
    assert sum(turn.story_id == GREETINGS_STORY_ID for turn in all_turns) == 1
    assert len(help_view.turns) == 1
    assert help_view.turns[0].scene_id == STANDARD_HELP_SCENE
    assert len(help_view.turns[0].choices) == 3
    assert state.scene == STANDARD_HELP_SCENE


def test_standard_help_selection_restarts_at_menu_after_leaving_assistant() -> None:
    story = StandardStory()
    selection_state = AssistantState(
        story=STANDARD_STORY_ID,
        scene=STANDARD_HELP_SCENE,
        status="active",
    )

    assert story.entry_scene(context_for(selection_state)) == STANDARD_HELP_SCENE
    assert (
        story.entry_scene(context_for(selection_state, previous_page_key="goals"))
        == STANDARD_MENU_SCENE
    )


def test_greetings_choose_a_randomized_greeting_once_per_hour_and_forward_to_menu() -> None:
    state = AssistantState(
        story=STANDARD_STORY_ID,
        scene=READY_NODE,
        status="completed",
    )
    session = {}
    context = context_for(
        state,
        session_state=session,
        now=datetime(2026, 7, 26, tzinfo=timezone.utc),
    )
    normal = GreetingsStory(random_source=StubRandom(0.1, 0))
    scene = normal.entry_scene(context)
    turn = normal.advance(context, scene, None)
    assert turn.story_id == GREETINGS_STORY_ID
    assert turn.continue_flow is True
    assert turn.lines[0].text == "Tiny progress time."
    greeting_session = story_session(session, GREETINGS_STORY_ID)
    assert greeting_session.get(GREETING_SELECTION_KEY) == "tiny_progress"
    randomized_at = greeting_session.get(GREETING_RANDOMIZED_AT_KEY)

    within_hour = replace(
        context,
        now=datetime(2026, 7, 26, 0, 59, tzinfo=timezone.utc),
    )
    assert normal.entry_scene(within_hour) == "default"
    hello = normal.advance(within_hour, "default", None)
    assert hello.lines[0].text == "Hello"
    assert greeting_session.get(GREETING_SELECTION_KEY) == "tiny_progress"
    assert greeting_session.get(GREETING_RANDOMIZED_AT_KEY) == randomized_at

    after_hour = replace(
        context,
        now=datetime(2026, 7, 26, 1, 0, tzinfo=timezone.utc),
    )
    assert normal.entry_scene(after_hour) == "tiny_progress"
    assert greeting_session.get(GREETING_RANDOMIZED_AT_KEY) != randomized_at

    interactive_session = {}
    interactive_context = replace(context, session_state=interactive_session)
    interactive = GreetingsStory(random_source=StubRandom(0.8, 0))
    scene = interactive.entry_scene(interactive_context)
    assert story_session(interactive_session, GREETINGS_STORY_ID).get(GREETING_PENDING_KEY) == "mood_check"
    prompt = interactive.advance(interactive_context, scene, None)
    assert [choice.label for choice in prompt.choices] == ["Ready.", "Absolutely not."]
    response = interactive.advance(
        interactive_context,
        scene,
        selection("greetings", scene, "ready", "Ready."),
    )
    assert response.story_id == GREETINGS_STORY_ID
    assert response.continue_flow is True
    assert story_session(interactive_session, GREETINGS_STORY_ID).get(GREETING_PENDING_KEY) is None


def test_greetings_choose_interactive_rare_variants_and_keep_them_pending() -> None:
    state = AssistantState(story=STANDARD_STORY_ID, scene=READY_NODE, status="completed")
    context = context_for(state, now=datetime(2026, 7, 26, tzinfo=timezone.utc))

    interactive = GreetingsStory(random_source=StubRandom(0.6, 1))
    interactive_scene = interactive.entry_scene(context)
    assert interactive_scene == "cowboy"
    assert interactive.advance(context, interactive_scene, None).choices[0].label == "Howdy."

    rare_context = replace(context, session_state={})
    rare = GreetingsStory(random_source=StubRandom(0.9, 0))
    rare_scene = rare.entry_scene(rare_context)
    assert rare_scene == "silent"
    silent = rare.advance(rare_context, rare_scene, None)
    assert [choice.label for choice in silent.choices] == ["Hello.", "Hi.", "Hey."]
    reply = rare.advance(rare_context, rare_scene, selection("greetings", rare_scene, "hello", "Hello."))
    assert [line.text for line in reply.lines][0] == "Oh! Hello."


def test_morning_greeting_intercept_is_daily_durable_and_ignores_hourly_cadence() -> None:
    state = AssistantState(story=STANDARD_STORY_ID, scene=READY_NODE, status="completed")
    session = {}
    story = GreetingsStory(random_source=StubRandom(0.1, 2))
    context = context_for(
        state,
        session_state=session,
        now=datetime(2026, 7, 26, 6, tzinfo=timezone.utc),
    )
    story_session(session, GREETINGS_STORY_ID).set(
        GREETING_RANDOMIZED_AT_KEY,
        datetime(2026, 7, 26, 5, 59, tzinfo=timezone.utc).isoformat(),
    )

    scene = story.entry_scene(context)
    assert scene == "morning_greeting"
    assert story_session(session, GREETINGS_STORY_ID).get(GREETING_PENDING_KEY) is None
    prompt = story.advance(context, scene, None)
    assert prompt.lines == ()
    assert [choice.label for choice in prompt.choices] == ["Good Morning", "say nothing"]
    assert prompt.choices[1].style == "italic"
    assert prompt.choices[1].record_selection is False
    assert prompt.completed is True
    assert prompt.event_updates == {
        MORNING_GREETING_EVENT_ID: {MORNING_GREETING_DISPLAYED_ON_KEY: "2026-07-26"}
    }

    displayed_state = apply_turn(state, prompt)
    later = replace(context, state=displayed_state, now=datetime(2026, 7, 26, 8, 59, tzinfo=timezone.utc))
    assert story.entry_scene(later) != "morning_greeting"
    assert story.entry_scene(replace(later, now=datetime(2026, 7, 26, 9, tzinfo=timezone.utc))) != "morning_greeting"
    next_day = replace(later, now=datetime(2026, 7, 27, 6, tzinfo=timezone.utc))
    assert story.entry_scene(next_day) == "morning_greeting"
    next_day_prompt = story.advance(next_day, "morning_greeting", None)
    replaced_state = apply_turn(displayed_state, next_day_prompt)
    assert replaced_state.events == {
        MORNING_GREETING_EVENT_ID: {MORNING_GREETING_DISPLAYED_ON_KEY: "2026-07-27"}
    }


def test_morning_greeting_prompt_is_saved_durably_when_displayed() -> None:
    persistence = RecordingPersistence()
    director = AssistantDirector(
        persistence,
        {AssistantMode.NORMAL: StandardStory(), GREETINGS_STORY_ID: GreetingsStory()},
    )
    state = AssistantState(story=STANDARD_STORY_ID, scene=READY_NODE, status="completed")
    view = RecordingView()

    saved_state = director.render(
        context_for(state, session_state={}, now=datetime(2026, 7, 26, 6, tzinfo=timezone.utc)),
        view,
    )

    assert len(persistence.saved_states) == 1
    assert saved_state.events == {
        MORNING_GREETING_EVENT_ID: {MORNING_GREETING_DISPLAYED_ON_KEY: "2026-07-26"}
    }


def test_morning_greeting_selection_starts_normal_flow_and_uses_stable_reply() -> None:
    state = AssistantState(story=STANDARD_STORY_ID, scene=READY_NODE, status="completed")
    session = {}
    story = GreetingsStory(random_source=StubRandom(0.1, 1))
    context = context_for(
        state,
        session_state=session,
        now=datetime(2026, 7, 26, 6, tzinfo=timezone.utc),
    )
    scene = story.entry_scene(context)
    prompt = story.advance(context, scene, None)
    displayed_state = apply_turn(state, prompt)
    selected_context = replace(context, state=displayed_state)

    silent = story.advance(
        selected_context,
        scene,
        selection(GREETINGS_STORY_ID, scene, "say_nothing", "say nothing"),
    )
    assert silent.lines == ()
    assert silent.continue_flow is True

    next_day_context = replace(
        selected_context,
        now=datetime(2026, 7, 27, 6, tzinfo=timezone.utc),
    )
    next_day_scene = story.entry_scene(next_day_context)
    story.advance(next_day_context, next_day_scene, None)
    response = story.advance(
        next_day_context,
        next_day_scene,
        selection(GREETINGS_STORY_ID, next_day_scene, "good_morning", "Good Morning"),
    )
    assert tuple(line.text for line in response.lines) == MORNING_GREETING_REPLIES[1]
    assert response.continue_flow is True


def test_push_reminder_backoff_and_turn_updates() -> None:
    director = AssistantDirector(RecordingPersistence(), default_stories())
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    state = AssistantState(
        story=STANDARD_STORY_ID,
        scene=READY_NODE,
        status="completed",
        events={
            PUSH_PROMPT_EVENT_ID: {
                "dismissed_count": 1,
                "dismissed_at_completed_goal_count": 2,
            }
        },
    )
    assert not director._push_prompt_is_eligible(
        context_for(state, user_state={"completed_goal_count": 2})
    )
    assert director._push_prompt_is_eligible(
        context_for(state, user_state={"completed_goal_count": 3})
    )

    second = replace(
        state,
        events={
            PUSH_PROMPT_EVENT_ID: {
                "dismissed_count": 2,
                "dismissed_at_completed_goal_count": 2,
                "last_dismissed_at": (now - timedelta(days=29)).isoformat(),
            }
        },
    )
    assert not director._push_prompt_is_eligible(
        context_for(second, user_state={"completed_goal_count": 5}, now=now)
    )
    assert director._push_prompt_is_eligible(
        context_for(
            second,
            user_state={"completed_goal_count": 5},
            now=now + timedelta(days=1),
        )
    )

    story = PushReminderStory()
    offer = story.advance(context_for(state, now=now), None, None)
    assert offer.event_updates[PUSH_PROMPT_EVENT_ID]["shown_count"] == 1
    dismiss = story.advance(
        context_for(apply_turn(state, offer), now=now),
        offer.scene_id,
        selection(story.story_id, offer.scene_id, "dismiss", "Not now"),
    )
    assert dismiss.completed
    assert dismiss.event_updates[PUSH_PROMPT_EVENT_ID]["dismissed_count"] == 2


@pytest.mark.parametrize(
    ("now", "expected"),
    (
        (datetime(2026, 7, 27, 0, 0, tzinfo=APP_ZONE), NIGHT_STORY_ID),
        (datetime(2026, 7, 27, 5, 59, tzinfo=APP_ZONE), NIGHT_STORY_ID),
        (datetime(2026, 7, 27, 6, 0, tzinfo=APP_ZONE), None),
        (datetime(2026, 7, 27, 23, 59, tzinfo=APP_ZONE), None),
    ),
)
def test_night_event_is_selected_only_during_berlin_night(now, expected) -> None:
    director = AssistantDirector(RecordingPersistence(), default_stories())
    state = AssistantState(story=STANDARD_STORY_ID, scene=READY_NODE, status="completed")

    story = director._important_issue_story(context_for(state, now=now))

    assert story is None if expected is None else story.story_id == expected


def test_debug_night_disable_is_restricted_to_debug_accounts(monkeypatch) -> None:
    monkeypatch.setattr(assistant_director, "DEBUG_DISABLE_NIGHT_EVENT", True)
    director = AssistantDirector(RecordingPersistence(), default_stories())
    state = AssistantState(story=STANDARD_STORY_ID, scene=READY_NODE, status="completed")
    night = datetime(2026, 7, 27, 1, tzinfo=APP_ZONE)

    ordinary = director._important_issue_story(
        context_for(state, profile={"debug_info": False}, now=night)
    )
    debug = director._important_issue_story(
        context_for(state, profile={"debug_info": True}, now=night)
    )

    assert ordinary is not None
    assert ordinary.story_id == NIGHT_STORY_ID
    assert debug is None


def test_night_event_does_not_preempt_fresh_onboarding_but_preempts_information() -> None:
    director = AssistantDirector(RecordingPersistence(), default_stories())
    night = datetime(2026, 7, 27, 1, tzinfo=APP_ZONE)

    fresh = AssistantState()
    assert director.story_dispatch(context_for(fresh, now=night), None).story_id == TUTORIAL_STORY_ID

    information = AssistantState(
        story=STANDARD_STORY_ID,
        scene=READY_NODE,
        status="completed",
        events={
            GOAL_INVITATION_EVENT_ID: {
                "invitations": [{"goal_id": "one", "inviter_name": "Bob"}]
            }
        },
    )
    assert director.story_dispatch(context_for(information, now=night), None).story_id == NIGHT_STORY_ID


def test_night_story_uses_the_special_progress_pattern_and_finishes() -> None:
    story = NightStory(random_source=StubRandom(0))
    state = AssistantState()
    session = {}

    initial = story.advance(context_for(state, session_state=session), NIGHT_EVENT_ID, None)
    assert len(initial.statuses) == 1
    assert initial.keep_statuses_in_history

    for clicks in range(1, NIGHT_STATUS_CLICK_COUNT + 1):
        turn = story.advance(
            context_for(state, session_state=session),
            NIGHT_EVENT_ID,
            selection(NIGHT_STORY_ID, NIGHT_EVENT_ID, "send", "Send"),
        )
        assert turn.statuses == (f"{clicks}x",)
        assert turn.progress == ()
        state = apply_turn(state, turn)

    first_bar = story.advance(
        context_for(state, session_state=session),
        NIGHT_EVENT_ID,
        selection(NIGHT_STORY_ID, NIGHT_EVENT_ID, "send", "Send"),
    )
    assert [entry.text for entry in first_bar.progress] == [
        f"1 / {NIGHT_PROGRESS_BAR_CLICK_COUNT}"
    ]

    session["assistant.story_session"][NIGHT_STORY_ID]["clicks"] = (
        NIGHT_STATUS_CLICK_COUNT
        + NIGHT_PROGRESS_BAR_CLICK_COUNT * NIGHT_PROGRESS_BAR_COUNT
        - 1
    )
    final = story.advance(
        context_for(state, session_state=session),
        NIGHT_EVENT_ID,
        selection(NIGHT_STORY_ID, NIGHT_EVENT_ID, "send", "Send"),
    )
    assert len(final.lines) == 4
    assert final.lines[1].font_scale == 0.5
    assert final.progress_before_content
    assert [entry.text for entry in final.progress] == [
        f"{NIGHT_PROGRESS_BAR_CLICK_COUNT} / {NIGHT_PROGRESS_BAR_CLICK_COUNT}"
    ] * NIGHT_PROGRESS_BAR_COUNT
    assert final.assistant_leaves
    assert final.allow_interaction_after_leaving
    assert final.completed
    assert apply_turn(state, final).events[NIGHT_EVENT_ID] == {
        NIGHT_COMPLETED_COUNT_KEY: 1
    }
    assert [choice.id for choice in final.choices] == ["sorry", "good_night", "not_angry"]

    acknowledgement = story.advance(
        context_for(state, session_state=session),
        NIGHT_AFTER_LEAVING_SCENE,
        selection(NIGHT_STORY_ID, NIGHT_AFTER_LEAVING_SCENE, "sorry"),
    )
    assert acknowledgement.lines == ()
    assert [choice.id for choice in acknowledgement.choices] == ["go_to_bed", "leave_quietly"]
    assert acknowledgement.choices[1].style == "italic"

    exit_turn = story.advance(
        context_for(state, session_state=session),
        NIGHT_GOOD_NIGHT_SCENE,
        selection(NIGHT_STORY_ID, NIGHT_GOOD_NIGHT_SCENE, "leave_quietly"),
    )
    assert exit_turn.destination == "goals"
    assert exit_turn.destination_delay == 3
    assert exit_turn.completed
    assert "assistant.story_session" not in session


def test_night_completion_increments_the_normal_profile_once() -> None:
    persistence = RecordingPersistence()
    director = AssistantDirector(persistence, {NIGHT_STORY_ID: NightStory(random_source=StubRandom(0))})
    session = {
        "assistant.story_session": {
            NIGHT_STORY_ID: {
                "clicks": NIGHT_STATUS_CLICK_COUNT + NIGHT_PROGRESS_BAR_CLICK_COUNT * NIGHT_PROGRESS_BAR_COUNT - 1
            }
        }
    }
    profile = {"user_id": "alice"}

    completed_state = director.render(
        context_for(
            AssistantState(),
            profile=profile,
            session_state=session,
            record_night_event_completion=lambda: persistence.increment_completed_night_events("alice"),
        ),
        RecordingView(selection(NIGHT_STORY_ID, NIGHT_EVENT_ID, "send", "Send")),
    )
    director.render(
        context_for(
            completed_state,
            profile=profile,
            session_state=session,
        ),
        RecordingView(selection(NIGHT_STORY_ID, NIGHT_AFTER_LEAVING_SCENE, "sorry")),
    )

    assert persistence.completed_night_events == 1
    assert profile["completed_night_events"] == 1


def test_night_story_can_open_with_imagined_sleeping_noises() -> None:
    ordinary = NightStory(random_source=StubRandom(0)).advance(
        context_for(AssistantState(), session_state={}), NIGHT_EVENT_ID, None
    )
    imagined = NightStory(random_source=StubRandom(0, 1)).advance(
        context_for(AssistantState(), session_state={}), NIGHT_EVENT_ID, None
    )

    assert len(imagined.statuses) == 1
    assert imagined.statuses != ordinary.statuses


def test_mode_switch_preserves_achievements_but_restarts_conversation() -> None:
    state = AssistantState(
        story=STANDARD_STORY_ID,
        scene=READY_NODE,
        status="completed",
        sequences={"debug": 2},
        knowledge={"tutorial.notifications.seen": True},
        events={"debug.flow": {"step": 2}},
    )
    switched = state.with_mode(AssistantMode.SPECIAL)
    assert switched.story is None
    assert switched.scene is None
    assert switched.status == "new"
    assert switched.sequences == state.sequences
    assert switched.knowledge == state.knowledge
    assert switched.events == state.events


def test_durable_completion_clears_transient_state() -> None:
    persistence = RecordingPersistence()
    session = {
        TRANSIENT_ASSISTANT_STATE_SESSION_KEY: {
            "user_id": "alice",
            "assistant_state": AssistantState(
                story=TUTORIAL_STORY_ID,
                scene=WELCOME_NODE,
                status="paused",
            ).to_dict(),
        }
    }
    director = AssistantDirector(persistence, default_stories())
    view = RecordingView(selection(TUTORIAL_STORY_ID, WELCOME_NODE, "decline"))
    completed = director.render(
        context_for(
            AssistantState(
                story=TUTORIAL_STORY_ID,
                scene=WELCOME_NODE,
                status="paused",
            ),
            session_state=session,
        ),
        view,
    )
    assert completed.status == "declined"
    assert TRANSIENT_ASSISTANT_STATE_SESSION_KEY not in session
