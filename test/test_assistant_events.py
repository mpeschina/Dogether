from __future__ import annotations

from dataclasses import replace

from src.assistant.core import AssistantContext
from src.assistant.director import AssistantDirector, apply_event_outcome
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
    APP_INTRO_SEEN_KEY,
    TUTORIAL_SEQUENCE_ID,
    AppIntroductionEvent,
    AssistantReadyEvent,
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
        self.selected_choice = selected_choice
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
        return self.selected_choice

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
) -> AssistantContext:
    current_user = profile if profile is not None else {"user_id": "alice"}
    return AssistantContext(
        user_id="alice",
        current_user=current_user,
        state=state,
        session_state={},
        current_page_key="help",
        previous_page_key=previous_page_key,
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


def test_normal_tutorial_plays_once_then_shows_ready_without_another_write() -> None:
    persistence = RecordingPersistence()
    profile = {"user_id": "alice"}
    state = AssistantState.from_profile(profile)
    director = AssistantDirector(persistence, default_stories())
    introduction_view = RecordingView()

    updated = director.render(context_for(state, profile=profile), introduction_view)

    assert isinstance(default_stories()[AssistantMode.NORMAL].next_event(context_for(state)), AppIntroductionEvent)
    assert updated.sequences[TUTORIAL_SEQUENCE_ID] == 1
    assert updated.knowledge[APP_INTRO_SEEN_KEY] is True
    assert len([call for call in introduction_view.calls if call[0] == "say"]) == 4
    assert len(persistence.saved_states) == 1

    ready_view = RecordingView()
    ready_context = context_for(
        AssistantState.from_profile(profile),
        profile=profile,
        previous_page_key="help",
    )
    unchanged = director.render(ready_context, ready_view)

    assert isinstance(
        default_stories()[AssistantMode.NORMAL].next_event(ready_context),
        AssistantReadyEvent,
    )
    assert unchanged == updated
    assert ready_view.calls == [
        ("status", "Assistant ready — come back whenever you need help.")
    ]
    assert len(persistence.saved_states) == 1


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
        sequences={TUTORIAL_SEQUENCE_ID: 1, SPECIAL_SEQUENCE_ID: 2},
        knowledge={APP_INTRO_SEEN_KEY: True, "tutorial.notifications.seen": False},
        events={CLICK_CHALLENGE_EVENT_ID: {"clicks": 20}},
    )

    special_state = normal_state.with_mode(AssistantMode.SPECIAL)
    assert special_state.sequences == normal_state.sequences
    assert special_state.knowledge == normal_state.knowledge
    assert special_state.events == normal_state.events

    assert AssistantState.reset() == AssistantState()
