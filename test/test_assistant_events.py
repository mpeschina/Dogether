from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.assistant.core import AssistantContext
from src.assistant.director import AssistantDirector, apply_event_outcome
from src.assistant.presentation import (
    PERSIST_TRANSCRIPT_ACROSS_PAGE_HOPS_KEY,
    TRANSCRIPT_KEY,
    clear_transcript_for_new_help_visit,
)
from src.assistant.state import AssistantMode, AssistantState
from src.assistant.stories import default_stories
from src.assistant.stories.special_examples import (
    BUTTON_TEST_EVENT_ID,
    CLICK_CHALLENGE_EVENT_ID,
    SPECIAL_SEQUENCE_ID,
    ButtonTestExampleEvent,
    ClickChallengeExampleEvent,
    SpecialExampleStory,
    WelcomeExampleEvent,
)
from src.assistant.stories.push_reminder import PushReminderEvent
from src.assistant.stories.standard import (
    PUSH_PROMPT_EVENT_ID,
    STANDARD_TUTORIAL_FLOW,
    StandardMenuEvent,
    StandardStory,
    StandardTutorialEvent,
)
from src.assistant.stories.tutorial import (
    ANALYSIS_COMPLETE_NODE,
    AssistantReadyEvent,
    ASSISTANT_DISMISSED_KEY,
    FRIENDS_NODE,
    GOALS_NODE,
    ONBOARDING_FLOW,
    PROFILE_ANALYSIS_FLOW,
    PUSH_NODE,
    READY_NODE,
    STANDARD_FLOW,
    WELCOME_NODE,
    InitialTutorialStory,
    ProfileAnalysisEvent,
    PushSetupReminderEvent,
    ResumeEvent,
    WelcomeEvent,
)


class RecordingPersistence:
    def __init__(self) -> None:
        self.saved_states: list[dict] = []

    def save_assistant_state(self, user_id, assistant_state, now=None):
        stored = AssistantState.from_value(assistant_state).to_dict()
        self.saved_states.append(stored)
        return stored


class RecordingView:
    def __init__(self, *, selected_choice=None, send_clicked=False) -> None:
        self.choice_to_select = selected_choice
        self.send_clicked = send_clicked
        self.input_rendered = False
        self.calls: list[tuple] = []

    def say(self, message):
        self.calls.append(("say", message))

    def typing_indicator(self, duration_seconds):
        self.calls.append(("typing", duration_seconds))

    def wait(self, duration_seconds):
        self.calls.append(("wait", duration_seconds))

    def assistant_leave(self):
        self.calls.append(("leave",))

    def go_to(self, destination):
        self.calls.append(("go_to", destination))

    def status(self, message):
        self.calls.append(("status", message))

    def choices(self, event_id, label, *options):
        self.calls.append(("choices", event_id, label, options))
        return self.choice_to_select

    def selected_choice(self, event_id, *options):
        return self.choice_to_select

    def send_control(self, event_id):
        self.input_rendered = True
        self.calls.append(("send_control", event_id))
        return self.send_clicked

    def progress(self, value, text):
        self.calls.append(("progress", value, text))


def context_for(
    state: AssistantState,
    *,
    profile: dict | None = None,
    previous_page_key: str | None = "goals",
    user_state: dict[str, bool] | None = None,
) -> AssistantContext:
    current_user = profile if profile is not None else {"user_id": "alice"}
    return AssistantContext(
        user_id="alice",
        current_user=current_user,
        state=state,
        session_state={},
        current_page_key="help",
        previous_page_key=previous_page_key,
        user_state=user_state or {},
    )


def test_assistant_state_normalizes_missing_and_malformed_values() -> None:
    assert AssistantState.from_profile({}) == AssistantState.reset()

    state = AssistantState.from_value(
        {
            "mode": "unknown",
            "sequences": {"valid": "2", "negative": -1, "invalid": "nope"},
            "knowledge": {"seen": True, "invalid": "yes"},
            "events": {"event": {"clicks": 4}, "invalid": []},
        }
    )

    assert state.mode is AssistantMode.NORMAL
    assert state.sequences == {"valid": 2, "negative": 0}
    assert state.knowledge == {"seen": True}
    assert state.events == {"event": {"clicks": 4}}


def test_assistant_transcript_is_cleared_after_leaving_help_unless_retained() -> None:
    session_state = {TRANSCRIPT_KEY: [("say", "Hello")]}

    clear_transcript_for_new_help_visit(session_state, "goals")
    assert TRANSCRIPT_KEY not in session_state

    retained_state = {
        TRANSCRIPT_KEY: [("say", "Hello")],
        PERSIST_TRANSCRIPT_ACROSS_PAGE_HOPS_KEY: True,
    }
    clear_transcript_for_new_help_visit(retained_state, "goals")
    assert retained_state[TRANSCRIPT_KEY] == [("say", "Hello")]
    assert PERSIST_TRANSCRIPT_ACROSS_PAGE_HOPS_KEY not in retained_state


def test_first_visit_persists_a_paused_welcome_and_returning_user_can_resume() -> None:
    persistence = RecordingPersistence()
    profile = {"user_id": "alice"}
    state = AssistantState.from_profile(profile)
    director = AssistantDirector(persistence, default_stories())
    introduction_view = RecordingView()

    updated = director.render(context_for(state, profile=profile), introduction_view)

    assert isinstance(director._next_event(context_for(state)), WelcomeEvent)
    assert updated.flow == ONBOARDING_FLOW
    assert updated.node == WELCOME_NODE
    assert updated.status == "paused"
    assert ("say", "Hi, welcome!") in introduction_view.calls
    assert ("say", "Want some help?") in introduction_view.calls
    assert ("choices", "onboarding_intro", "", ("Analyse my profile", "Give me a tour", "I'm good")) in introduction_view.calls
    assert len(persistence.saved_states) == 1

    resume_view = RecordingView()
    ready_context = context_for(
        AssistantState.from_profile(profile),
        profile=profile,
        previous_page_key="goals",
    )
    unchanged = director.render(ready_context, resume_view)

    assert isinstance(director._next_event(ready_context), ResumeEvent)
    assert unchanged == updated
    assert ("say", "Hey, you're back.") in resume_view.calls
    assert len(persistence.saved_states) == 1


def test_profile_analysis_checks_real_state_in_order_and_completes() -> None:
    event = ProfileAnalysisEvent()
    state = AssistantState(flow=PROFILE_ANALYSIS_FLOW, node=FRIENDS_NODE, status="active")

    friends_done = apply_event_outcome(
        state, event.render(context_for(state, user_state={"friend_count": 2}), RecordingView())
    )
    assert friends_done.node == GOALS_NODE

    goals_done = apply_event_outcome(
        friends_done,
        event.render(
            context_for(friends_done, user_state={"friend_count": 2, "goal_count": 1}),
            RecordingView(),
        ),
    )
    assert goals_done.node == PUSH_NODE

    complete_view = RecordingView()
    completed = apply_event_outcome(
        goals_done,
        event.render(
            context_for(
                goals_done,
                user_state={"friend_count": 2, "goal_count": 1, "push_enabled": True},
            ),
            complete_view,
        ),
    )
    assert completed.flow == PROFILE_ANALYSIS_FLOW
    assert completed.node == ANALYSIS_COMPLETE_NODE
    assert completed.status == "active"
    assert ("say", "Notifications are ready. ✓") in complete_view.calls


def test_im_good_leaves_the_assistant_and_prevents_follow_up_events() -> None:
    persistence = RecordingPersistence()
    profile = {"user_id": "alice"}
    director = AssistantDirector(persistence, default_stories())
    state = AssistantState()
    leaving_view = RecordingView(selected_choice="I'm good")
    dismissed = director.render(context_for(state, profile=profile), leaving_view)

    assert dismissed.status == "declined"
    assert ("leave",) in leaving_view.calls
    assert InitialTutorialStory().next_event(context_for(dismissed)) is None
    next_visit = RecordingView()
    assert director.render(context_for(dismissed, profile=profile), next_visit) == dismissed
    assert ("say", "Hello") in next_visit.calls


def test_im_good_click_is_processed_after_the_welcome_rerun() -> None:
    persistence = RecordingPersistence()
    profile = {"user_id": "alice"}
    director = AssistantDirector(persistence, default_stories())

    # The initial render persists a paused welcome while its choice buttons
    # remain on screen.  Clicking one reruns Help with Help as the previous
    # page, so it must return to WelcomeEvent instead of showing ResumeEvent.
    paused = director.render(context_for(AssistantState(), profile=profile), RecordingView())
    assert paused.status == "paused"

    leaving_view = RecordingView(selected_choice="I'm good")
    dismissed = director.render(
        context_for(
            AssistantState.from_profile(profile),
            profile=profile,
            previous_page_key="help",
        ),
        leaving_view,
    )

    assert dismissed.status == "declined"
    assert ("leave",) in leaving_view.calls
    assert not any(call[0] == "choices" for call in leaving_view.calls)
    assert ("say", "Hey, you're back.") not in leaving_view.calls


def test_standard_mode_shows_the_default_tutorial_menu_after_onboarding() -> None:
    state = AssistantState(flow=STANDARD_FLOW, node=READY_NODE, status="completed")
    director = AssistantDirector(RecordingPersistence(), default_stories())
    assert isinstance(director._next_event(context_for(state, user_state={"push_enabled": False})), StandardMenuEvent)


def test_director_selects_one_normal_mode_event_in_priority_order() -> None:
    director = AssistantDirector(RecordingPersistence(), default_stories())
    fresh = AssistantState()
    assert isinstance(director._next_event(context_for(fresh)), WelcomeEvent)

    resuming = AssistantState(flow=PROFILE_ANALYSIS_FLOW, node=FRIENDS_NODE, status="active")
    assert isinstance(director._next_event(context_for(resuming)), ProfileAnalysisEvent)

    push_ready = AssistantState(flow=STANDARD_FLOW, node=READY_NODE, status="completed")
    assert isinstance(
        director._next_event(context_for(push_ready, user_state={"push_enabled": False, "completed_goal_count": 1})),
        PushReminderEvent,
    )

    standard = AssistantState(flow=STANDARD_FLOW, node=READY_NODE, status="completed")
    assert isinstance(
        director._next_event(context_for(standard, user_state={"push_enabled": False, "completed_goal_count": 0})),
        StandardMenuEvent,
    )


def test_standard_menu_starts_the_selected_tutorial() -> None:
    event = StandardMenuEvent()
    state = AssistantState(flow=STANDARD_FLOW, node=READY_NODE, status="completed")
    tutorials = (
        ("How do I add friends?", "tutorial.friends.seen", FRIENDS_NODE),
        ("How do I create a goal?", "tutorial.goals.seen", GOALS_NODE),
        ("How do notifications work?", "tutorial.notifications.seen", PUSH_NODE),
    )

    for choice, knowledge_key, node in tutorials:
        outcome = event.render(context_for(state), RecordingView(selected_choice=choice))
        updated = apply_event_outcome(state, outcome)

        assert updated.knowledge[knowledge_key] is True
        assert updated.flow == STANDARD_TUTORIAL_FLOW
        assert updated.node == node
        assert updated.status == "active"
        assert outcome.continue_flow is True


def test_standard_tutorials_return_to_standard_without_advancing_onboarding() -> None:
    tutorials = (
        (FRIENDS_NODE, "Later", {"friend_count": 0}),
        (GOALS_NODE, "Later", {"goal_count": 0}),
        (PUSH_NODE, "Not now", {"push_enabled": False}),
    )
    story = StandardStory()

    for node, choice, user_state in tutorials:
        state = AssistantState(flow=STANDARD_TUTORIAL_FLOW, node=node, status="active")
        event = story.next_event(context_for(state, user_state=user_state))
        outcome = event.render(
            context_for(state, user_state=user_state), RecordingView(selected_choice=choice)
        )
        updated = apply_event_outcome(state, outcome)

        assert isinstance(event, StandardTutorialEvent)
        assert updated.flow == STANDARD_FLOW
        assert updated.node == READY_NODE
        assert updated.status == "completed"
        assert updated.flow != PROFILE_ANALYSIS_FLOW


def test_push_reminder_backoff_and_third_dismissal_suppression() -> None:
    director = AssistantDirector(RecordingPersistence(), default_stories())
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    state = AssistantState(
        flow=STANDARD_FLOW,
        node=READY_NODE,
        status="completed",
        events={
            PUSH_PROMPT_EVENT_ID: {
                "dismissed_count": 1,
                "dismissed_at_completed_goal_count": 2,
            }
        },
    )
    assert not director._push_prompt_is_eligible(context_for(state, user_state={"completed_goal_count": 2}))
    assert director._push_prompt_is_eligible(context_for(state, user_state={"completed_goal_count": 3}))

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
        replace(context_for(second, user_state={"completed_goal_count": 5}), now=now)
    )
    assert director._push_prompt_is_eligible(
        replace(context_for(second, user_state={"completed_goal_count": 5}), now=now + timedelta(days=1))
    )

    suppressed = replace(second, events={PUSH_PROMPT_EVENT_ID: {"dismissed_count": 3}})
    assert not director._push_prompt_is_eligible(context_for(suppressed, user_state={"completed_goal_count": 99}))


def test_special_story_requires_a_new_help_visit_between_events() -> None:
    story = SpecialExampleStory()
    state = AssistantState(mode=AssistantMode.SPECIAL)

    assert isinstance(story.next_event(context_for(state)), WelcomeExampleEvent)

    state = replace(state, sequences={SPECIAL_SEQUENCE_ID: 1})
    assert story.next_event(context_for(state, previous_page_key="help")) is None
    assert isinstance(
        story.next_event(context_for(state, previous_page_key="friends")),
        ButtonTestExampleEvent,
    )

    state = replace(state, events={BUTTON_TEST_EVENT_ID: {"active": True}})
    assert isinstance(
        story.next_event(context_for(state, previous_page_key="help")),
        ButtonTestExampleEvent,
    )


def test_special_button_progress_is_durable_and_completion_advances_sequence() -> None:
    event = ButtonTestExampleEvent()
    state = AssistantState(
        mode=AssistantMode.SPECIAL,
        sequences={SPECIAL_SEQUENCE_ID: 1},
    )

    pending = event.render(context_for(state), RecordingView())
    active_state = apply_event_outcome(state, pending)
    assert active_state.events[BUTTON_TEST_EVENT_ID] == {"active": True}
    assert active_state.sequences[SPECIAL_SEQUENCE_ID] == 1

    completed = event.render(context_for(active_state), RecordingView(selected_choice="2"))
    completed_state = apply_event_outcome(active_state, completed)
    assert completed_state.sequences[SPECIAL_SEQUENCE_ID] == 2
    assert BUTTON_TEST_EVENT_ID not in completed_state.events


def test_click_challenge_persists_clicks_and_completes_at_existing_threshold() -> None:
    event = ClickChallengeExampleEvent()
    state = AssistantState(
        mode=AssistantMode.SPECIAL,
        sequences={SPECIAL_SEQUENCE_ID: 2},
        events={CLICK_CHALLENGE_EVENT_ID: {"active": True, "clicks": 1}},
    )

    pending_view = RecordingView(send_clicked=True)
    pending_state = apply_event_outcome(
        state,
        event.render(context_for(state), pending_view),
    )
    assert pending_state.events[CLICK_CHALLENGE_EVENT_ID]["clicks"] == 2
    assert ("status", "2x") in pending_view.calls

    almost_complete = replace(
        state,
        events={CLICK_CHALLENGE_EVENT_ID: {"active": True, "clicks": 129}},
    )
    completed_view = RecordingView(send_clicked=True)
    completed_state = apply_event_outcome(
        almost_complete,
        event.render(context_for(almost_complete), completed_view),
    )

    assert completed_state.sequences[SPECIAL_SEQUENCE_ID] == 3
    assert CLICK_CHALLENGE_EVENT_ID not in completed_state.events
    assert ("say", "Come on.") in completed_view.calls
    assert ("say", "I AM NOT HERE!") in completed_view.calls


def test_mode_switch_preserves_progress_and_reset_clears_everything() -> None:
    normal_state = AssistantState(
        sequences={SPECIAL_SEQUENCE_ID: 2},
        knowledge={"tutorial.notifications.seen": False},
        events={CLICK_CHALLENGE_EVENT_ID: {"clicks": 20}},
    )

    special_state = normal_state.with_mode(AssistantMode.SPECIAL)
    assert special_state.sequences == normal_state.sequences
    assert special_state.knowledge == normal_state.knowledge
    assert special_state.events == normal_state.events

    assert AssistantState.reset() == AssistantState()
