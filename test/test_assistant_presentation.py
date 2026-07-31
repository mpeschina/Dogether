from streamlit.testing.v1 import AppTest
from datetime import date

import src.assistant.presentation as presentation
from pathlib import Path
from src.assistant.core import AssistantCard


CHOICE_APP = """
import src.assistant.presentation as presentation
from src.assistant.core import AssistantChoice, AssistantLine, AssistantTurn

view = presentation.StreamlitAssistantView()
if view.selection is not None:
    view.present(
        AssistantTurn(
            story_id="test",
            scene_id="next",
            lines=(AssistantLine(f"Picked {view.selection.label}"),),
            choices=(AssistantChoice("again", "Again"),),
        )
    )
elif not view.waiting_for_input:
    view.present(
        AssistantTurn(
            story_id="test",
            scene_id="start",
            lines=(AssistantLine("Hello"),),
            choices=(AssistantChoice("go", "Go"),),
        )
    )
view.finish()
"""


def test_assistant_page_uses_the_material_support_agent_badge() -> None:
    content = Path("src/pages/assistant_page.py").read_text(encoding="utf-8")

    assert '"sky_blue": "#2E90FA"' in content
    assert '"light_ash": "#667085"' in content
    assert '"reddish_pink": "#F0447A"' in content
    assert '"violet": "#7F56D9"' in content
    assert '"emerald": "#12B76A"' in content
    assert '"amber": "#F79009"' in content
    assert "ASSISTANT_ICON_BACKGROUND_COLOR: str | None = ASSISTANT_COLORS[" in content
    assert 'st.get_option("theme.primaryColor") or "#1F2937"' in content
    assert "ASSISTANT_BADGE_SIZE_MULTIPLIER: float = 1.0" in content
    assert "ASSISTANT_ICON_SIZE_MULTIPLIER: float = 1.0" in content
    assert "ASSISTANT_BADGE_BASE_SIZE_REM * ASSISTANT_BADGE_SIZE_MULTIPLIER" in content
    assert "ASSISTANT_ICON_BASE_SIZE_REM * ASSISTANT_ICON_SIZE_MULTIPLIER" in content
    assert "material-symbols-rounded'>support_agent" in content
    assert "border-radius: 0.65rem" in content


SEND_APP = """
import src.assistant.presentation as presentation
from src.assistant.core import AssistantTurn

view = presentation.StreamlitAssistantView()
if view.selection is not None:
    view.present(
        AssistantTurn(
            story_id="test",
            scene_id="send",
            control_kind="send",
            record_selection=False,
            statuses=("Sent",),
        )
    )
elif not view.waiting_for_input:
    view.present(
        AssistantTurn(
            story_id="test",
            scene_id="send",
            control_kind="send",
            record_selection=False,
        )
    )
view.finish()
"""


def test_choice_round_replays_history_and_consumes_click_once() -> None:
    app = AppTest.from_string(CHOICE_APP, default_timeout=10).run()
    assert not app.exception
    assert [button.label for button in app.button] == ["Go"]

    app.button[0].click().run()
    assert not app.exception
    assert [button.label for button in app.button] == ["Again"]
    assert app.session_state.filtered_state["assistant.transcript"] == [
        ("assistant", "Hello"),
        ("user", "Go"),
        ("assistant", "Picked Go"),
    ]

    app.run()
    assert [button.label for button in app.button] == ["Again"]
    assert app.session_state.filtered_state["assistant.transcript"] == [
        ("assistant", "Hello"),
        ("user", "Go"),
        ("assistant", "Picked Go"),
    ]


def test_send_control_is_restored_without_recording_player_bubbles() -> None:
    app = AppTest.from_string(SEND_APP, default_timeout=10).run()
    assert not app.exception
    assert [button.label for button in app.button] == ["Send"]

    app.button[0].click().run()
    assert not app.exception
    assert [button.label for button in app.button] == ["Send"]
    assert app.session_state.filtered_state["assistant.transcript"] == [
        ("live_status", "Sent"),
    ]


def test_live_statuses_are_removed_when_assistant_speaks() -> None:
    app_source = """
import streamlit as st
import src.assistant.presentation as presentation
from src.assistant.core import AssistantLine, AssistantTurn

view = presentation.StreamlitAssistantView()
if view.selection is not None:
    count = st.session_state.get('count', 0) + 1
    st.session_state.count = count
    if count == 1:
        view.present(AssistantTurn(
            story_id='test', scene_id='send', control_kind='send',
            record_selection=False, statuses=('Working',),
        ))
    else:
        view.present(AssistantTurn(
            story_id='test', scene_id='send', control_kind='send',
            record_selection=False, lines=(AssistantLine('Finished'),),
        ))
elif not view.waiting_for_input:
    view.present(AssistantTurn(
        story_id='test', scene_id='send', control_kind='send',
        record_selection=False,
    ))
view.finish()
"""
    app = AppTest.from_string(app_source, default_timeout=10).run()
    app.button[0].click().run()
    app.button[0].click().run()

    assert app.session_state.filtered_state["assistant.transcript"] == [
        ("assistant", "Finished"),
    ]


def test_send_control_records_submitted_message_and_uses_turn_placeholder() -> None:
    app_source = """
import src.assistant.presentation as presentation
from src.assistant.core import AssistantTurn

view = presentation.StreamlitAssistantView()
if view.selection is not None:
    view.present(AssistantTurn(
        story_id='test', scene_id='done', statuses=('Done',),
        keep_statuses_in_history=True,
    ))
elif not view.waiting_for_input:
    view.present(AssistantTurn(
        story_id='test', scene_id='start', control_kind='send',
        send_placeholder='Say something…',
    ))
view.finish()
"""
    app = AppTest.from_string(app_source, default_timeout=10).run()
    assert app.text_input[0].placeholder == "Say something…"
    app.text_input[0].set_value("Hello there")
    app.button[0].click().run()
    assert app.session_state.filtered_state["assistant.transcript"] == [
        ("user", "Hello there"),
        ("status", "Done"),
    ]


def test_card_row_progress_renders_a_primary_color_bar(monkeypatch) -> None:
    import src.assistant.presentation as presentation
    from src.assistant.core import AssistantCard

    rendered: list[str] = []
    monkeypatch.setattr(presentation.st, "markdown", lambda body, **_: rendered.append(body))

    presentation.StreamlitAssistantView._render_card(
        AssistantCard("DAILY RHYTHM", rows=(("MON", "75%"),), row_progress=(75,))
    )

    assert "assistant-card-row-track" in rendered[0]
    assert "style='width:75%'" in rendered[0]


def test_weekly_chart_renders_solid_selected_and_outlined_historical_bars(monkeypatch) -> None:
    rendered: list[str] = []
    monkeypatch.setattr(
        presentation.st,
        "markdown",
        lambda body, **_: rendered.append(body),
    )

    presentation.StreamlitAssistantView._render_card(
        AssistantCard(
            "WEEK TO WEEK",
            weekly_chart=(
                (date(2026, 7, 13), 50, False),
                (date(2026, 7, 20), 75, True),
            ),
        )
    )

    assert "assistant-weekly-chart" in rendered[0]
    assert "assistant-weekly-chart-bar-history" in rendered[0]
    assert "assistant-weekly-chart-bar-current" in rendered[0]
    assert "Week of 2026-07-13: 50% completion" in rendered[0]
    assert "Week of 2026-07-20: 75% completion (selected)" in rendered[0]


def test_weekly_chart_history_bars_are_slightly_darker_than_the_secondary_theme_color(monkeypatch) -> None:
    rendered: list[str] = []
    monkeypatch.setattr(
        presentation.st,
        "markdown",
        lambda body, **_: rendered.append(body),
    )

    presentation.StreamlitAssistantView._render_control_styles()

    assert (
        "color-mix(in srgb, var(--secondary-background-color, #f1f5f9) 92%, #1f2937)"
        in rendered[0]
    )


def test_recent_activity_markup_replaces_only_the_recent_row(monkeypatch) -> None:
    rendered: list[str] = []
    monkeypatch.setattr(presentation.st, "markdown", lambda body, **_: rendered.append(body))

    presentation.StreamlitAssistantView._render_card(
        AssistantCard(
            "NEW STREAK RECORD",
            rows=(("Recent", "● ● ●"), ("Previous best", "3 days")),
            recent_activity_html="<span class='mini-activity-dots'></span>",
        )
    )

    assert "<span class='assistant-recent-activity'><span class='mini-activity-dots'></span></span>" in rendered[0]
    assert "Previous best" in rendered[0]
    assert "3 days" in rendered[0]
