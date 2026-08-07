from datetime import datetime
from zoneinfo import ZoneInfo

from src.assistant.stories.greetings import (
    GREETING_PENDING_KEY,
    GREETING_RANDOMIZED_AT_KEY,
    GREETING_SELECTION_KEY,
    GREETINGS_STORY_ID,
)
from src.assistant.stories.smalltalk import SMALLTALK_CLICKED_AT_KEY, SMALLTALK_STORY_ID
from src.assistant.story_session import ASSISTANT_STORY_SESSION_KEY
from src.pages import account_page
from src.pages.account_page import (
    activity_diagram_html,
    assistant_transient_debug_info,
    clear_greeting_session,
    clear_smalltalk_session,
    completed_night_event_count,
    debug_account_status,
    format_personal_best_day,
    greeting_debug_info,
    personal_best_records,
    personal_bests_html,
    reset_assistant_session_state,
)

BERLIN = ZoneInfo("Europe/Berlin")


class AssistantSettingsStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.subheaders: list[str] = []

    def subheader(self, body: str) -> None:
        self.subheaders.append(body)

    def caption(self, _body: str) -> None:
        pass

    def json(self, _value: object) -> None:
        pass

    def radio(self, _label: str, options: list[str], **_kwargs: object) -> str:
        return options[0]

    def button(self, _label: str, **_kwargs: object) -> bool:
        return False


def test_debug_account_status_reflects_the_persisted_profile_flag() -> None:
    assert debug_account_status({"debug_info": True}) == "Debug account: enabled"
    assert debug_account_status({"debug_info": False}) == "Debug account: disabled"
    assert debug_account_status({}) == "Debug account: disabled"


def test_completed_night_event_count_is_safe_for_missing_or_malformed_profiles() -> None:
    assert completed_night_event_count({"completed_night_events": 4}) == 4
    assert completed_night_event_count({}) == 0
    assert completed_night_event_count({"completed_night_events": "invalid"}) == 0
    assert completed_night_event_count({"completed_night_events": -1}) == 0


def test_assistant_settings_requires_debug_info(monkeypatch) -> None:
    fake_st = AssistantSettingsStreamlit()
    monkeypatch.setattr(account_page, "st", fake_st)

    account_page.render_assistant_settings(object(), {"debug_info": False}, "alice")
    assert fake_st.subheaders == []

    account_page.render_assistant_settings(object(), {"debug_info": True}, "alice")
    assert fake_st.subheaders == ["Assistant (Prototype)"]


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=BERLIN)


def test_activity_diagram_html_renders_variable_month_github_grid() -> None:
    html = activity_diagram_html(
        {
            "2026-11-02": {"active_goals": 2, "fulfilled_goals": 1, "percent": 50.0},
            "2026-12-01": {"active_goals": 1, "fulfilled_goals": 1, "percent": 100.0},
        },
        now=at("2026-12-15T12:00:00"),
        months=2,
    )

    assert "activity-grid" in html
    assert "repeat(8,var(--cell))" in html
    assert ">Nov</div>" in html
    assert ">Dec</div>" in html
    assert html.count("class='activity-day'") == 56
    assert "2026-11-02: 1 / 2 goals fulfilled (50.0%)" in html
    assert "background:#40c463" in html
    assert "2026-12-01: 1 / 1 goals fulfilled (100.0%)" in html
    assert "background:#216e39" in html


def test_activity_diagram_html_renders_full_past_365_days() -> None:
    html = activity_diagram_html(
        {
            "2026-01-01": {"active_goals": 1, "fulfilled_goals": 1, "percent": 100.0},
            "2026-12-31": {"active_goals": 2, "fulfilled_goals": 1, "percent": 50.0},
        },
        now=at("2026-12-31T12:00:00"),
        days=365,
    )

    assert ">Jan</div>" in html
    assert ">Dec</div>" in html
    assert "2026-01-01: 1 / 1 goals fulfilled (100.0%)" in html
    assert "2026-12-31: 1 / 2 goals fulfilled (50.0%)" in html
    assert html.count("class='activity-day'") == 371


def test_greeting_debug_info_shows_and_clears_only_session_greeting_state() -> None:
    session_state = {
        ASSISTANT_STORY_SESSION_KEY: {
            GREETINGS_STORY_ID: {
                GREETING_RANDOMIZED_AT_KEY: "2026-07-26T12:00:00+00:00",
                GREETING_SELECTION_KEY: "cowboy",
                GREETING_PENDING_KEY: "cowboy",
            }
        },
        "unrelated": "kept",
    }

    debug_info = greeting_debug_info(session_state)

    assert debug_info == {
        "greeting": "cowboy",
        "current_greeting_variable": "cowboy",
        "randomized_at": "2026-07-26T12:00:00+00:00",
        "pending_interaction": "cowboy",
    }

    clear_greeting_session(session_state)

    assert session_state == {"unrelated": "kept"}


def test_clear_smalltalk_session_preserves_other_story_sessions() -> None:
    session_state = {
        ASSISTANT_STORY_SESSION_KEY: {
            GREETINGS_STORY_ID: {GREETING_SELECTION_KEY: "cowboy"},
            SMALLTALK_STORY_ID: {SMALLTALK_CLICKED_AT_KEY: "2026-07-26T12:00:00+00:00"},
        },
        "unrelated": "kept",
    }

    clear_smalltalk_session(session_state)

    assert session_state == {
        ASSISTANT_STORY_SESSION_KEY: {
            GREETINGS_STORY_ID: {GREETING_SELECTION_KEY: "cowboy"},
        },
        "unrelated": "kept",
    }


def test_assistant_transient_debug_info_shows_all_assistant_owned_session_values() -> None:
    session_state = {
        "assistant.transient_state": {"user_id": "user-1", "assistant_state": {"story": "weekly_summary"}},
        "assistant.transcript": [("card", {"title": "Weekly completion"})],
        "assistant_choice_3_0": False,
        "assistant_mode_user-1": "normal",
        "assistant_send_input_4": "Hello",
        ASSISTANT_STORY_SESSION_KEY: {"greetings": {"selection": "cowboy"}},
        "help_assistant_dummy_input": "",
        "unrelated": "kept",
    }

    assert assistant_transient_debug_info(session_state) == {
        "assistant.transcript": [["card", {"title": "Weekly completion"}]],
        "assistant.transient_state": {"user_id": "user-1", "assistant_state": {"story": "weekly_summary"}},
        "assistant_choice_3_0": False,
        "assistant_mode_user-1": "normal",
        "assistant_send_input_4": "Hello",
        ASSISTANT_STORY_SESSION_KEY: {"greetings": {"selection": "cowboy"}},
        "help_assistant_dummy_input": "",
    }


def test_reset_assistant_session_state_clears_all_assistant_state_and_story_sessions() -> None:
    session_state = {
        "assistant.transient_state": {
            "user_id": "user-1",
            "assistant_state": {"story": "weekly_summary"},
        },
        "assistant.transcript": [("card", {"title": "Weekly completion"})],
        "assistant_choice_3_0": False,
        "assistant_mode_user-1": "normal",
        "assistant_send_input_4": "Hello",
        ASSISTANT_STORY_SESSION_KEY: {"greetings": {"selection": "cowboy"}},
        "help_assistant_dummy_input": "",
        "unrelated": "kept",
    }

    reset_assistant_session_state(session_state, "user-1")

    assert session_state == {"unrelated": "kept"}
