from streamlit.testing.v1 import AppTest


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
        ("status", "Sent"),
    ]
