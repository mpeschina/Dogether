from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.assistant.core import AssistantContext, AssistantSelection
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
    transient_assistant_state_for_user,
)
from src.assistant.stories import default_stories
from src.assistant.stories.greetings import (
    GREETING_PENDING_SESSION_KEY,
    GREETING_RANDOMIZED_AT_SESSION_KEY,
    GREETING_SELECTION_SESSION_KEY,
    GREETINGS_STORY_ID,
    GreetingsStory,
)
from src.assistant.stories.push_reminder import PushReminderStory
from src.assistant.stories.information import (
    GOAL_INVITATION_EVENT_ID,
    INFORMATION_STORY_ID,
    _goal_fact_cards,
)
from src.assistant.stories.special_examples import (
    BUTTON_TEST_EVENT_ID,
    CLICK_CHALLENGE_EVENT_ID,
    PROGRESS_BAR_CLICK_COUNT,
    PROGRESS_BAR_COUNT,
    SPECIAL_SEQUENCE_ID,
    STATUS_CLICK_COUNT,
    SpecialExampleStory,
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
    READY_NODE,
    RESUME_NODE,
    STANDARD_STORY_ID,
    TUTORIAL_STORY_ID,
    WELCOME_NODE,
    InitialTutorialStory,
)


class RecordingPersistence:
    def __init__(self) -> None:
        self.saved_states: list[dict] = []

    def save_assistant_state(self, user_id, assistant_state, now=None):
        del user_id, now
        stored = AssistantState.from_value(assistant_state).to_dict()
        self.saved_states.append(stored)
        return stored


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
    previous_page_key: str | None = "help",
    user_state: dict | None = None,
    session_state: dict | None = None,
    create_friend_share_link=None,
    now: datetime | None = None,
) -> AssistantContext:
    return AssistantContext(
        user_id="alice",
        current_user=profile if profile is not None else {"user_id": "alice"},
        state=state,
        session_state=session_state if session_state is not None else {},
        current_page_key="help",
        previous_page_key=previous_page_key,
        user_state=user_state or {},
        create_friend_share_link=create_friend_share_link,
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
    clear_transcript_for_new_help_visit(session, "goals")
    assert TRANSCRIPT_KEY not in session
    assert ACTIVE_CONTROL_KEY not in session
    assert CONTROL_ROUND_KEY not in session

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
    paused = director.render(context_for(state, session_state=session), initial)

    assert initial.turns[0].story_id == INFORMATION_STORY_ID
    assert [item.text for item in initial.turns[0].content if hasattr(item, "text")][-1] == "Bob and Charlie invited you to 2 new shared goals."
    assert len(initial.turns[0].content) == 5
    assert paused.story == INFORMATION_STORY_ID

    acknowledged = RecordingView(selection(INFORMATION_STORY_ID, "goal_invitations", "acknowledge"))
    completed = director.render(context_for(paused, session_state=session), acknowledged)
    assert acknowledged.turns[0].assistant_leaves is True
    assert GOAL_INVITATION_EVENT_ID not in completed.events
    assert completed.story == STANDARD_STORY_ID
    assert session["assistant.information.complete"] is True


def test_information_card_hides_a_single_friend_participant() -> None:
    card = _goal_fact_cards([
        {
            "goal_id": "goal-one", "inviter_name": "Bob", "goal_name": "Walk",
            "schedule_class": "daily", "required_periods": "1", "target": "4",
            "friend_participant_count": "1",
        }
    ])[0]
    assert "Friends already participating" not in dict(card.rows)


def test_one_selection_advances_and_renders_the_next_stable_round() -> None:
    persistence = RecordingPersistence()
    director = AssistantDirector(persistence, default_stories())
    state = AssistantState(
        story=TUTORIAL_STORY_ID,
        scene=WELCOME_NODE,
        status="paused",
    )
    view = RecordingView(
        selection(TUTORIAL_STORY_ID, WELCOME_NODE, "Analyse my profile")
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
        "Later",
    ]


def test_declining_welcome_completes_durably() -> None:
    persistence = RecordingPersistence()
    profile = {"user_id": "alice"}
    director = AssistantDirector(persistence, default_stories())
    state = AssistantState(
        story=TUTORIAL_STORY_ID,
        scene=WELCOME_NODE,
        status="paused",
    )
    view = RecordingView(selection(TUTORIAL_STORY_ID, WELCOME_NODE, "I'm good"))

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
        selection(TUTORIAL_STORY_ID, RESUME_NODE, "Yes"),
    )
    assert resumed.state_scene == GOALS_NODE
    assert resumed.continue_flow

    restarted = story.advance(
        context,
        RESUME_NODE,
        selection(TUTORIAL_STORY_ID, RESUME_NODE, "Start over"),
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
        selection(TUTORIAL_STORY_ID, FRIENDS_EXPLANATION_NODE, "Got it"),
    )
    assert next_turn.state_scene == FRIENDS_EXPLANATION_OPTIONS_NODE

    link = story.advance(
        context,
        FRIENDS_EXPLANATION_LINK_NODE,
        selection(
            TUTORIAL_STORY_ID,
            FRIENDS_EXPLANATION_LINK_NODE,
            "Create a Link for me",
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
            "Ciao, thanks for the explanation",
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
            "Cool, thank you for the explanation.",
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
            "Cool, thank you for the explanation.",
        ),
    )
    assert after_push.state_scene == ANALYSIS_COMPLETE_NODE
    assert after_push.event_updates == {PUSH_EVENT_ID: {"outcome": "skipped"}}
    assert after_push.completed is False


def test_standard_menu_starts_tutorial_and_tracks_knowledge() -> None:
    story = StandardStory()
    state = AssistantState(
        story=STANDARD_STORY_ID,
        scene=READY_NODE,
        status="completed",
    )
    context = context_for(state)
    menu = story.advance(context, STANDARD_MENU_SCENE, None)
    assert [choice.label for choice in menu.choices] == [
        "Help me with the app",
        "Analyse my progress",
    ]

    help_menu = story.advance(
        context,
        STANDARD_MENU_SCENE,
        selection(STANDARD_STORY_ID, STANDARD_MENU_SCENE, "help", "Help me with the app"),
    )
    assert help_menu.continue_flow is True
    menu = story.advance(context, STANDARD_HELP_SCENE, None)
    assert len(menu.choices) == 4

    start = story.advance(
        context,
        STANDARD_HELP_SCENE,
        selection(STANDARD_STORY_ID, STANDARD_MENU_SCENE, "friends", "How do I add friends?"),
    )
    updated = apply_turn(state, start)
    assert updated.scene == FRIENDS_EXPLANATION_NODE
    assert updated.knowledge["tutorial.friends.seen"] is True


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
    assert session[GREETING_SELECTION_SESSION_KEY] == "tiny_progress"
    randomized_at = session[GREETING_RANDOMIZED_AT_SESSION_KEY]

    within_hour = replace(
        context,
        now=datetime(2026, 7, 26, 0, 59, tzinfo=timezone.utc),
    )
    assert normal.entry_scene(within_hour) == "default"
    hello = normal.advance(within_hour, "default", None)
    assert hello.lines[0].text == "Hello"
    assert session[GREETING_SELECTION_SESSION_KEY] == "tiny_progress"
    assert session[GREETING_RANDOMIZED_AT_SESSION_KEY] == randomized_at

    after_hour = replace(
        context,
        now=datetime(2026, 7, 26, 1, 0, tzinfo=timezone.utc),
    )
    assert normal.entry_scene(after_hour) == "tiny_progress"
    assert session[GREETING_RANDOMIZED_AT_SESSION_KEY] != randomized_at

    interactive_session = {}
    interactive_context = replace(context, session_state=interactive_session)
    interactive = GreetingsStory(random_source=StubRandom(0.8, 0))
    scene = interactive.entry_scene(interactive_context)
    assert interactive_session[GREETING_PENDING_SESSION_KEY] == "mood_check"
    prompt = interactive.advance(interactive_context, scene, None)
    assert [choice.label for choice in prompt.choices] == ["Ready.", "Absolutely not."]
    response = interactive.advance(
        interactive_context,
        scene,
        selection("greetings", scene, "ready", "Ready."),
    )
    assert response.story_id == GREETINGS_STORY_ID
    assert response.continue_flow is True
    assert GREETING_PENDING_SESSION_KEY not in interactive_session


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


def test_special_story_uses_choice_and_send_control_rounds() -> None:
    story = SpecialExampleStory()
    state = AssistantState(mode=AssistantMode.SPECIAL)
    welcome = story.advance(context_for(state), story.entry_scene(context_for(state)), None)
    assert welcome.completed
    state = apply_turn(state, welcome)
    assert state.sequences[SPECIAL_SEQUENCE_ID] == 1

    context = context_for(state, previous_page_key="goals")
    buttons = story.advance(context, story.entry_scene(context), None)
    assert buttons.scene_id == BUTTON_TEST_EVENT_ID
    assert [choice.label for choice in buttons.choices] == ["1", "2", "3"]
    state = apply_turn(state, buttons)

    chosen = story.advance(
        context_for(state),
        BUTTON_TEST_EVENT_ID,
        selection(story.story_id, BUTTON_TEST_EVENT_ID, "2"),
    )
    state = apply_turn(state, chosen)
    assert state.sequences[SPECIAL_SEQUENCE_ID] == 2
    assert BUTTON_TEST_EVENT_ID not in state.events

    click_state = replace(
        state,
        events={
            CLICK_CHALLENGE_EVENT_ID: {
                "active": True,
                "clicks": STATUS_CLICK_COUNT,
            }
        },
    )
    send = story.advance(
        context_for(click_state),
        CLICK_CHALLENGE_EVENT_ID,
        selection(
            story.story_id,
            CLICK_CHALLENGE_EVENT_ID,
            "send",
            "Send",
        ),
    )
    assert send.control_kind == "send"
    assert send.progress[0].text == f"1 / {PROGRESS_BAR_CLICK_COUNT}"


def test_special_click_challenge_uses_live_statuses_and_reveals_bars_sequentially() -> None:
    story = SpecialExampleStory()
    state = AssistantState(
        mode=AssistantMode.SPECIAL,
        events={CLICK_CHALLENGE_EVENT_ID: {"active": True, "clicks": 0}},
    )

    for clicks in range(1, STATUS_CLICK_COUNT + 1):
        turn = story.advance(
            context_for(state),
            CLICK_CHALLENGE_EVENT_ID,
            selection(story.story_id, CLICK_CHALLENGE_EVENT_ID, "send", "Send"),
        )
        assert turn.statuses == (f"{clicks}x",)
        assert turn.progress == ()
        assert not turn.keep_statuses_in_history
        state = apply_turn(state, turn)

    first_bar = story.advance(
        context_for(state),
        CLICK_CHALLENGE_EVENT_ID,
        selection(story.story_id, CLICK_CHALLENGE_EVENT_ID, "send", "Send"),
    )
    assert [entry.text for entry in first_bar.progress] == [
        f"1 / {PROGRESS_BAR_CLICK_COUNT}"
    ]

    almost_second_bar = story.advance(
        context_for(
            replace(
                state,
                events={
                    CLICK_CHALLENGE_EVENT_ID: {
                        "active": True,
                        "clicks": STATUS_CLICK_COUNT + PROGRESS_BAR_CLICK_COUNT,
                    }
                },
            )
        ),
        CLICK_CHALLENGE_EVENT_ID,
        selection(story.story_id, CLICK_CHALLENGE_EVENT_ID, "send", "Send"),
    )
    assert [entry.text for entry in almost_second_bar.progress] == [
        f"{PROGRESS_BAR_CLICK_COUNT} / {PROGRESS_BAR_CLICK_COUNT}",
        f"1 / {PROGRESS_BAR_CLICK_COUNT}",
    ]

    final = story.advance(
        context_for(
            replace(
                state,
                events={
                    CLICK_CHALLENGE_EVENT_ID: {
                        "active": True,
                        "clicks": (
                            STATUS_CLICK_COUNT
                            + PROGRESS_BAR_CLICK_COUNT * PROGRESS_BAR_COUNT
                            - 1
                        ),
                    }
                },
            )
        ),
        CLICK_CHALLENGE_EVENT_ID,
        selection(story.story_id, CLICK_CHALLENGE_EVENT_ID, "send", "Send"),
    )
    assert [entry.text for entry in final.progress] == [
        f"{PROGRESS_BAR_CLICK_COUNT} / {PROGRESS_BAR_CLICK_COUNT}"
    ] * PROGRESS_BAR_COUNT


def test_mode_switch_preserves_achievements_but_restarts_conversation() -> None:
    state = AssistantState(
        story=STANDARD_STORY_ID,
        scene=READY_NODE,
        status="completed",
        sequences={SPECIAL_SEQUENCE_ID: 2},
        knowledge={"tutorial.notifications.seen": True},
        events={CLICK_CHALLENGE_EVENT_ID: {"clicks": 20}},
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
    view = RecordingView(selection(TUTORIAL_STORY_ID, WELCOME_NODE, "I'm good"))
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
