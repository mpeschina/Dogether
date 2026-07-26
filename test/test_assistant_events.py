from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.assistant.core import AssistantContext, EventOutcome
from src.assistant.director import AssistantDirector, apply_event_outcome
from src.assistant.presentation import (
    PERSIST_TRANSCRIPT_ACROSS_PAGE_HOPS_KEY,
    TRANSCRIPT_KEY,
    clear_transcript_for_new_help_visit,
)
from src.assistant.state import AssistantMode, AssistantState
from src.assistant.stories import default_stories
from src.assistant.stories.greetings import (
    GREETING_DATE_SESSION_KEY,
    GREETING_PENDING_SESSION_KEY,
    GREETING_SELECTION_SESSION_KEY,
    GreetingEvent,
    GreetingsStory,
    INTERACTIVE_GREETING_IDS,
    NORMAL_GREETING_IDS,
)
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
)
from src.assistant.stories.tutorial import (
    ANALYSIS_COMPLETE_NODE,
    AssistantReadyEvent,
    ASSISTANT_DISMISSED_KEY,
    FRIENDS_NODE,
    FRIENDS_EXPLANATION_NODE,
    FRIENDS_EXPLANATION_STEP_KEY,
    GOALS_EXPLANATION_NODE,
    GOALS_EXPLANATION_STEP_KEY,
    GOALS_NODE,
    ONBOARDING_FLOW,
    PROFILE_ANALYSIS_FLOW,
    PUSH_EXPLANATION_NODE,
    PUSH_EXPLANATION_STEP_KEY,
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

    def typing_indicator(self, duration_seconds=0):
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
        return self.choice_to_select if self.choice_to_select in options else None

    def selected_choice(self, event_id, *options):
        return self.choice_to_select if self.choice_to_select in options else None

    def send_control(self, event_id):
        self.input_rendered = True
        self.calls.append(("send_control", event_id))
        return self.send_clicked

    def progress(self, value, text):
        self.calls.append(("progress", value, text))


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
    previous_page_key: str | None = "goals",
    user_state: dict[str, bool] | None = None,
    session_state: dict | None = None,
    create_friend_share_link=None,
) -> AssistantContext:
    current_user = profile if profile is not None else {"user_id": "alice"}
    return AssistantContext(
        user_id="alice",
        current_user=current_user,
        state=state,
        session_state=session_state if session_state is not None else {},
        current_page_key="help",
        previous_page_key=previous_page_key,
        user_state=user_state or {},
        create_friend_share_link=create_friend_share_link,
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
    assert any(call[0] == "say" for call in next_visit.calls)


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
    assert isinstance(director._next_event(context_for(state, user_state={"push_enabled": False})), GreetingEvent)


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
        GreetingEvent,
    )


def test_greeting_roll_uses_an_explicit_eighty_twenty_category_split() -> None:
    state = AssistantState(flow=STANDARD_FLOW, node=READY_NODE, status="completed")
    menu = StandardMenuEvent()

    normal_event = GreetingsStory(menu, random_source=StubRandom(0.79)).next_event(context_for(state))
    interactive_event = GreetingsStory(menu, random_source=StubRandom(0.8)).next_event(context_for(state))

    assert isinstance(normal_event, GreetingEvent)
    assert normal_event.greeting_id in NORMAL_GREETING_IDS
    assert isinstance(interactive_event, GreetingEvent)
    assert interactive_event.greeting_id in INTERACTIVE_GREETING_IDS


def test_daily_greeting_is_session_only_and_date_aware() -> None:
    persistence = RecordingPersistence()
    stories = default_stories()
    stories["greetings"] = GreetingsStory(StandardMenuEvent(), random_source=StubRandom(0.1, 1))
    director = AssistantDirector(persistence, stories)
    state = AssistantState(flow=STANDARD_FLOW, node=READY_NODE, status="completed")
    session_state = {}
    context = replace(
        context_for(state, session_state=session_state, user_state={"push_enabled": False}),
        now=datetime(2026, 7, 26, tzinfo=timezone.utc),
    )
    view = RecordingView()

    assert director.render(context, view) == state
    assert ("say", "Hello, today is July 26.") in view.calls
    assert session_state[GREETING_DATE_SESSION_KEY] == "2026-07-26"
    assert session_state[GREETING_SELECTION_SESSION_KEY] == "date"
    assert GREETING_PENDING_SESSION_KEY not in session_state
    assert persistence.saved_states == []


def test_interactive_greeting_resumes_then_forwards_to_the_tutorial_menu() -> None:
    state = AssistantState(flow=STANDARD_FLOW, node=READY_NODE, status="completed")
    session_state = {}
    story = GreetingsStory(StandardMenuEvent(), random_source=StubRandom(0.8))
    context = replace(
        context_for(state, session_state=session_state),
        now=datetime(2026, 7, 26, tzinfo=timezone.utc),
    )

    initial = story.next_event(context)
    initial_view = RecordingView()
    initial.render(context, initial_view)
    assert ("say", "Howdy my friend!") in initial_view.calls
    assert ("choices", "greetings.interaction", "", ("Are you a Cowboy today?",)) in initial_view.calls
    assert session_state[GREETING_PENDING_SESSION_KEY] == "cowboy"

    selected = story.next_event(context)
    selected_view = RecordingView(selected_choice="Are you a Cowboy today?")
    selected.render(context, selected_view)
    assert ("say", "I am just in a good mood. How can I help you?") in selected_view.calls
    assert ("choices", "standard.tutorial_menu", "Tutorials", (
        "How do I add friends?", "How do goals work?", "How do notifications work?", "How do I track progress?",
    )) in selected_view.calls
    assert GREETING_PENDING_SESSION_KEY not in session_state


def test_greetings_fall_back_to_hello_until_a_new_session_day() -> None:
    state = AssistantState(flow=STANDARD_FLOW, node=READY_NODE, status="completed")
    session_state = {}
    story = GreetingsStory(StandardMenuEvent(), random_source=StubRandom(0.1, 2))
    today_context = replace(
        context_for(state, session_state=session_state),
        now=datetime(2026, 7, 26, tzinfo=timezone.utc),
    )
    story.next_event(today_context).render(today_context, RecordingView())

    fallback_view = RecordingView()
    story.next_event(today_context).render(today_context, fallback_view)
    assert ("say", "Hello") in fallback_view.calls

    tomorrow_context = replace(today_context, now=datetime(2026, 7, 27, tzinfo=timezone.utc))
    tomorrow_view = RecordingView()
    story.next_event(tomorrow_context).render(tomorrow_context, tomorrow_view)
    assert ("say", "Good to see you.") in tomorrow_view.calls

    new_session_view = RecordingView()
    new_session_context = replace(tomorrow_context, session_state={})
    story.next_event(new_session_context).render(new_session_context, new_session_view)
    assert ("say", "Good to see you.") in new_session_view.calls


def test_standard_menu_starts_the_selected_tutorial() -> None:
    event = StandardMenuEvent()
    state = AssistantState(flow=STANDARD_FLOW, node=READY_NODE, status="completed")
    tutorials = (
        ("How do I add friends?", "tutorial.friends.seen", FRIENDS_EXPLANATION_NODE),
        ("How do goals work?", "tutorial.goals.seen", GOALS_EXPLANATION_NODE),
        ("How do notifications work?", "tutorial.notifications.seen", PUSH_EXPLANATION_NODE),
    )

    for choice, knowledge_key, node in tutorials:
        outcome = event.render(context_for(state), RecordingView(selected_choice=choice))
        updated = apply_event_outcome(state, outcome)

        assert updated.knowledge[knowledge_key] is True
        assert updated.flow == STANDARD_TUTORIAL_FLOW
        assert updated.node == node
        assert updated.status == "active"
        assert outcome.continue_flow is True


def test_friendlist_explanation_creates_and_shows_an_invite_link() -> None:
    event = ProfileAnalysisEvent()
    state = AssistantState(flow=PROFILE_ANALYSIS_FLOW, node=FRIENDS_NODE, status="active")
    session_state = {}

    explanation = apply_event_outcome(
        state,
        event.render(
            context_for(state, user_state={"friend_count": 0}, session_state=session_state),
            RecordingView(selected_choice="Explain the Friendlist to me"),
        ),
    )
    assert explanation.node == FRIENDS_EXPLANATION_NODE

    intro_view = RecordingView(selected_choice="Got it")
    event.render(context_for(explanation, session_state=session_state), intro_view)
    assert ("say", "You have two options to add friends here.") in intro_view.calls

    options_view = RecordingView(selected_choice="Makes sense")
    event.render(context_for(explanation, session_state=session_state), options_view)
    assert ("say", "Your link belongs to you.") in options_view.calls

    link_view = RecordingView(selected_choice="Create a Link for me")
    outcome = event.render(
        context_for(
            explanation,
            session_state=session_state,
            create_friend_share_link=lambda: "https://dogether.example/friend?share=abc",
        ),
        link_view,
    )
    updated = apply_event_outcome(explanation, outcome)
    assert updated.node == FRIENDS_EXPLANATION_NODE
    assert updated.status == "paused"
    assert ("say", "Here’s your invite link:\n\nhttps://dogether.example/friend?share=abc") in link_view.calls
    assert ("choices", "friends_explanation.goodbye", "", ("Ciao, thanks for the explanation",)) in link_view.calls

    goodbye_view = RecordingView(selected_choice="Ciao, thanks for the explanation")
    goodbye = event.render(context_for(updated, session_state=session_state), goodbye_view)
    assert goodbye.status == "completed"
    assert ("leave",) in goodbye_view.calls


def test_notification_explanation_runs_linearly_and_can_enable_notifications() -> None:
    event = ProfileAnalysisEvent()
    state = AssistantState(flow=PROFILE_ANALYSIS_FLOW, node=PUSH_NODE, status="active")
    session_state = {}

    explanation = apply_event_outcome(
        state,
        event.render(
            context_for(state, user_state={"push_enabled": False}, session_state=session_state),
            RecordingView(selected_choice="Explain notifications to me"),
        ),
    )
    assert explanation.node == PUSH_EXPLANATION_NODE

    shared_goals_view = RecordingView(selected_choice="Got it")
    event.render(context_for(explanation, session_state=session_state), shared_goals_view)
    assert ("say", "Friends can finish a shared goal.") in shared_goals_view.calls

    mobile_view = RecordingView(selected_choice="Makes sense")
    event.render(context_for(explanation, session_state=session_state), mobile_view)
    assert ("say", "Desktop is straightforward.") in mobile_view.calls

    consent_view = RecordingView(selected_choice="Got it")
    event.render(context_for(explanation, session_state=session_state), consent_view)
    assert ("say", "Your operating system shows the consent prompt. Only you can approve it.") in consent_view.calls

    controls_view = RecordingView(selected_choice="Makes sense")
    event.render(context_for(explanation, session_state=session_state), controls_view)
    assert ("say", "Each goal has its own settings.") in controls_view.calls

    settings_view = RecordingView(selected_choice="Got it")
    event.render(context_for(explanation, session_state=session_state), settings_view)
    assert (
        "say",
        "Choose alerts when friends complete it and cap completion alerts per day. Also, choose alerts for reactions.",
    ) in settings_view.calls

    finish_view = RecordingView(selected_choice="Makes sense")
    event.render(context_for(explanation, session_state=session_state), finish_view)
    assert ("say", "They live on Manage Goals.") in finish_view.calls

    enable_view = RecordingView(selected_choice="Enable notifications")
    outcome = event.render(context_for(explanation, session_state=session_state), enable_view)
    updated = apply_event_outcome(explanation, outcome)
    assert updated.node == PUSH_NODE
    assert updated.status == "paused"
    assert updated.events["push_check"]["awaiting"] == "enable"
    assert outcome.continue_flow is True
    assert ("go_to", "push_notifications") in enable_view.calls


def test_notification_explanation_final_actions_manage_goals_and_goodbye() -> None:
    event = ProfileAnalysisEvent()
    state = AssistantState(flow=PROFILE_ANALYSIS_FLOW, node=PUSH_EXPLANATION_NODE, status="active")

    manage_session = {PUSH_EXPLANATION_STEP_KEY: "finish"}
    manage_view = RecordingView(selected_choice="Show me Manage Goals")
    manage = event.render(context_for(state, session_state=manage_session), manage_view)
    assert manage.node == PUSH_NODE
    assert manage.status == "paused"
    assert manage.continue_flow is True
    assert ("go_to", "manage_goals") in manage_view.calls

    goodbye_session = {PUSH_EXPLANATION_STEP_KEY: "finish"}
    goodbye_view = RecordingView(selected_choice="Cool, thank you for the explanation.")
    goodbye = event.render(context_for(state, session_state=goodbye_session), goodbye_view)
    assert goodbye.flow == STANDARD_FLOW
    assert goodbye.status == "completed"
    assert ("say", "Ciao.") in goodbye_view.calls
    assert ("leave",) in goodbye_view.calls


def test_standard_notification_explanation_does_not_persist_an_unanswered_step() -> None:
    story = StandardStory()
    state = AssistantState(flow=STANDARD_TUTORIAL_FLOW, node=PUSH_EXPLANATION_NODE, status="active")

    outcome = story.next_event(context_for(state, previous_page_key="help")).render(
        context_for(state, previous_page_key="help"), RecordingView()
    )

    assert outcome == EventOutcome()


def test_standard_notification_setup_completes_standard_flow_and_navigates() -> None:
    story = StandardStory()
    session_state = {PUSH_EXPLANATION_STEP_KEY: "finish"}
    state = AssistantState(flow=STANDARD_TUTORIAL_FLOW, node=PUSH_EXPLANATION_NODE, status="active")
    view = RecordingView(selected_choice="Enable notifications")
    context = context_for(state, session_state=session_state, previous_page_key="help")

    outcome = story.next_event(context).render(context, view)

    assert outcome.flow == STANDARD_FLOW
    assert outcome.node == READY_NODE
    assert outcome.status == "completed"
    assert outcome.continue_flow is True
    assert ("go_to", "push_notifications") in view.calls


def test_goal_explanation_runs_linearly_in_profile_analysis_and_can_start_goal_creation() -> None:
    event = ProfileAnalysisEvent()
    state = AssistantState(flow=PROFILE_ANALYSIS_FLOW, node=GOALS_NODE, status="active")
    session_state = {}

    explanation = apply_event_outcome(
        state,
        event.render(
            context_for(state, user_state={"goal_count": 0}, session_state=session_state),
            RecordingView(selected_choice="Explain Goals to me"),
        ),
    )
    assert explanation.node == GOALS_EXPLANATION_NODE
    assert explanation.status == "active"

    intro_view = RecordingView()
    intro = event.render(context_for(explanation, session_state=session_state), intro_view)
    assert ("say", "Goals are the heart of Dogether.") in intro_view.calls
    assert ("choices", "goals_explanation.intro", "", ("How do goals work?", "Got it")) in intro_view.calls

    finish = apply_event_outcome(
        explanation,
        event.render(context_for(explanation, session_state=session_state), RecordingView(selected_choice="Got it")),
    )
    goals_view = RecordingView(selected_choice="Makes sense")
    event.render(context_for(finish, session_state=session_state), goals_view)
    assert ("say", "Everyone tracks their own progress.") in goals_view.calls

    progress_view = RecordingView(selected_choice="Nice")
    event.render(context_for(finish, session_state=session_state), progress_view)
    assert ("say", "This is where it gets fun.") in progress_view.calls

    friends_view = RecordingView(selected_choice="And then?")
    event.render(context_for(finish, session_state=session_state), friends_view)
    assert ("say", "Send them a reaction.") in friends_view.calls

    reactions_view = RecordingView(selected_choice="Got it")
    event.render(context_for(finish, session_state=session_state), reactions_view)
    assert ("say", "That’s basically goals.") in reactions_view.calls

    create = apply_event_outcome(
        finish,
        event.render(context_for(finish, session_state=session_state), RecordingView(selected_choice="Create a goal")),
    )
    assert create.node == GOALS_NODE
    assert create.status == "paused"
    assert create.events["goals_check"]["awaiting"] == "create"
    assert "goals_explanation" not in create.events

    restarted_view = RecordingView()
    event.render(context_for(explanation, session_state=session_state), restarted_view)
    assert ("choices", "goals_explanation.intro", "", ("How do goals work?", "Got it")) in restarted_view.calls


def test_goal_explanation_choices_do_not_change_the_linear_path() -> None:
    event = ProfileAnalysisEvent()
    state = AssistantState(flow=PROFILE_ANALYSIS_FLOW, node=GOALS_EXPLANATION_NODE, status="active")
    session_state = {}

    how_view = RecordingView(selected_choice="How do goals work?")
    event.render(context_for(state, session_state=session_state), how_view)
    assert ("say", "Every goal has participants.") in how_view.calls

    progress_view = RecordingView(selected_choice="Makes sense")
    event.render(context_for(state, session_state=session_state), progress_view)
    assert ("say", "Everyone tracks their own progress.") in progress_view.calls

    friends_view = RecordingView(selected_choice="Nice")
    event.render(context_for(state, session_state=session_state), friends_view)
    assert ("say", "This is where it gets fun.") in friends_view.calls

    reactions_view = RecordingView(selected_choice="And then?")
    event.render(context_for(state, session_state=session_state), reactions_view)
    assert ("say", "Send them a reaction.") in reactions_view.calls


def test_goal_explanation_returns_to_standard_flow_when_thanked() -> None:
    story = StandardStory()
    session_state = {GOALS_EXPLANATION_STEP_KEY: "finish"}
    finish_state = AssistantState(
        flow=STANDARD_TUTORIAL_FLOW,
        node=GOALS_EXPLANATION_NODE,
        status="active",
    )
    back = apply_event_outcome(
        finish_state,
        story.next_event(context_for(finish_state, session_state=session_state, previous_page_key="help")).render(
            context_for(finish_state, session_state=session_state, previous_page_key="help"),
            RecordingView(selected_choice="Cool, thank you for the explanation."),
        ),
    )
    assert back.flow == STANDARD_FLOW
    assert back.node == READY_NODE
    assert back.status == "completed"


def test_standard_goal_explanation_can_navigate_to_goal_creation() -> None:
    story = StandardStory()
    session_state = {GOALS_EXPLANATION_STEP_KEY: "finish"}
    state = AssistantState(flow=STANDARD_TUTORIAL_FLOW, node=GOALS_EXPLANATION_NODE, status="active")
    view = RecordingView(selected_choice="Create a goal")

    outcome = story.next_event(context_for(state, session_state=session_state, previous_page_key="help")).render(
        context_for(state, session_state=session_state, previous_page_key="help"), view
    )

    assert outcome.flow == STANDARD_FLOW
    assert outcome.continue_flow is True
    assert ("go_to", "manage_goals") in view.calls


def test_goal_explanation_can_end_with_a_goodbye() -> None:
    event = ProfileAnalysisEvent()
    session_state = {GOALS_EXPLANATION_STEP_KEY: "finish"}
    state = AssistantState(flow=PROFILE_ANALYSIS_FLOW, node=GOALS_EXPLANATION_NODE, status="active")
    view = RecordingView(selected_choice="Cool, thank you for the explanation.")

    outcome = event.render(context_for(state, session_state=session_state), view)

    assert outcome.status == "completed"
    assert outcome.flow == STANDARD_FLOW
    assert ("say", "Ciao.") in view.calls
    assert ("leave",) in view.calls


def test_standard_goal_explanation_does_not_pause_without_a_choice() -> None:
    story = StandardStory()
    state = AssistantState(flow=STANDARD_TUTORIAL_FLOW, node=GOALS_EXPLANATION_NODE, status="active")

    outcome = story.next_event(context_for(state, previous_page_key="help")).render(
        context_for(state, previous_page_key="help"), RecordingView()
    )

    assert outcome == EventOutcome()


def test_leaving_a_standard_explanation_resets_to_the_standard_menu() -> None:
    story = StandardStory()
    session_state = {
        GOALS_EXPLANATION_STEP_KEY: "finish",
        FRIENDS_EXPLANATION_STEP_KEY: "link",
        PUSH_EXPLANATION_STEP_KEY: "goal_controls",
    }
    state = AssistantState(
        flow=STANDARD_TUTORIAL_FLOW,
        node=PUSH_EXPLANATION_NODE,
        status="active",
    )
    context = context_for(state, previous_page_key="goals", session_state=session_state)

    outcome = story.next_event(context).render(context, RecordingView())
    updated = apply_event_outcome(state, outcome)

    assert isinstance(story.next_event(context), StandardMenuEvent)
    assert updated.flow == STANDARD_FLOW
    assert updated.node == READY_NODE
    assert GOALS_EXPLANATION_STEP_KEY not in session_state
    assert FRIENDS_EXPLANATION_STEP_KEY not in session_state
    assert PUSH_EXPLANATION_STEP_KEY not in session_state


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
