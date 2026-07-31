from datetime import datetime
from zoneinfo import ZoneInfo

from src.assistant.stories.greetings import (
    GREETING_PENDING_SESSION_KEY,
    GREETING_RANDOMIZED_AT_SESSION_KEY,
    GREETING_SELECTION_SESSION_KEY,
)
from src.pages.account_page import (
    activity_diagram_html,
    assistant_transient_debug_info,
    clear_greeting_session,
    greeting_debug_info,
)

BERLIN = ZoneInfo("Europe/Berlin")


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
        GREETING_RANDOMIZED_AT_SESSION_KEY: "2026-07-26T12:00:00+00:00",
        GREETING_SELECTION_SESSION_KEY: "cowboy",
        GREETING_PENDING_SESSION_KEY: "cowboy",
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


def test_assistant_transient_debug_info_shows_all_assistant_owned_session_values() -> None:
    session_state = {
        "assistant.transient_state": {"user_id": "user-1", "assistant_state": {"story": "weekly_summary"}},
        "assistant.transcript": [("card", {"title": "Weekly completion"})],
        "assistant_choice_3_0": False,
        "assistant_mode_user-1": "normal",
        "assistant_send_input_4": "Hello",
        "greetings.selection": "cowboy",
        "help_assistant_dummy_input": "",
        "unrelated": "kept",
    }

    assert assistant_transient_debug_info(session_state) == {
        "assistant.transcript": [["card", {"title": "Weekly completion"}]],
        "assistant.transient_state": {"user_id": "user-1", "assistant_state": {"story": "weekly_summary"}},
        "assistant_choice_3_0": False,
        "assistant_mode_user-1": "normal",
        "assistant_send_input_4": "Hello",
        "greetings.selection": "cowboy",
        "help_assistant_dummy_input": "",
    }
