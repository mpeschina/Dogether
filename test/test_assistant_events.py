from __future__ import annotations

from dataclasses import replace

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
from src.assistant.stories.tutorial import (
    AssistantReadyEvent,
    ASSISTANT_DISMISSED_KEY,
    FRIENDS_NODE,
    GOALS_NODE,
    ONBOARDING_FLOW,
    PROFILE_ANALYSIS_FLOW,
    PUSH_NODE,
    READY_NODE,
    STANDARD_FLOW,
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

    assert isinstance(default_stories()[AssistantMode.NORMAL].next_event(context_for(state)), WelcomeEvent)
    assert updated.flow == ONBOARDING_FLOW
    assert updated.node == "welcome"
    assert updated.status == "paused"
    assert ("say", "Hey. I'm here if you need me.") in introduction_view.calls
    assert ("say", "What would you like to do?") in introduction_view.calls
    assert ("choices", "onboarding.welcome", "", ("Analyse my profile", "Give me a tour", "I'm good")) in introduction_view.calls
    assert len(persistence.saved_states) == 1

    resume_view = RecordingView()
    ready_context = context_for(
        AssistantState.from_profile(profile),
        profile=profile,
        previous_page_key="goals",
    )
    unchanged = director.render(ready_context, resume_view)

    assert isinstance(default_stories()[AssistantMode.NORMAL].next_event(ready_context), ResumeEvent)
    assert unchanged == updated
    assert ("say", "Hey, you're back.") in resume_view.calls
    assert len(persistence.saved_states) == 1


def test_profile_analysis_checks_real_state_in_order_and_completes() -> None:
    event = ProfileAnalysisEvent()
    state = AssistantState(flow=PROFILE_ANALYSIS_FLOW, node=FRIENDS_NODE, status="active")

    friends_done = apply_event_outcome(
        state, event.render(context_for(state, user_state={"has_friends": True}), RecordingView())
    )
    assert friends_done.node == GOALS_NODE

    goals_done = apply_event_outcome(
        friends_done,
        event.render(
            context_for(friends_done, user_state={"has_friends": True, "has_goals": True}),
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
                user_state={"has_friends": True, "has_goals": True, "push_enabled": True},
            ),
            complete_view,
        ),
    )
    assert completed.flow == STANDARD_FLOW
    assert completed.node == READY_NODE
    assert completed.status == "completed"
    assert ("say", "You're all set.") in complete_view.calls


def test_im_good_leaves_the_assistant_and_prevents_follow_up_events() -> None:
    persistence = RecordingPersistence()
    profile = {"user_id": "alice"}
    director = AssistantDirector(persistence, default_stories())
    state = AssistantState()
    leaving_view = RecordingView(selected_choice="I'm good")
    dismissed = director.render(context_for(state, profile=profile), leaving_view)

    assert dismissed.status == "dismissed"
    assert dismissed.knowledge[ASSISTANT_DISMISSED_KEY] is True
    assert ("leave",) in leaving_view.calls
    assert InitialTutorialStory().next_event(context_for(dismissed)) is None
    next_visit = RecordingView()
    assert director.render(context_for(dismissed, profile=profile), next_visit) == dismissed
    assert next_visit.calls == []


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

    assert dismissed.status == "dismissed"
    assert ("leave",) in leaving_view.calls
    assert ("typing", 0.45) not in leaving_view.calls
    assert not any(call[0] == "choices" for call in leaving_view.calls)
    assert ("say", "Hey, you're back.") not in leaving_view.calls


def test_standard_mode_shows_only_the_unseen_push_setup_reminder() -> None:
    state = AssistantState(flow=STANDARD_FLOW, node=READY_NODE, status="completed")
    story = InitialTutorialStory()
    assert isinstance(story.next_event(context_for(state, user_state={"push_enabled": False})), PushSetupReminderEvent)

    prompted = apply_event_outcome(
        state,
        PushSetupReminderEvent().render(context_for(state), RecordingView()),
    )
    assert story.next_event(context_for(prompted, user_state={"push_enabled": False})) is not None
    assert isinstance(
        story.next_event(context_for(prompted, user_state={"push_enabled": False})),
        AssistantReadyEvent,
    )


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
