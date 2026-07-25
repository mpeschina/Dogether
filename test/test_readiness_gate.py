from __future__ import annotations

from contextlib import nullcontext

import pytest

from src.pages import readiness_gate


class FakeStreamlit:
    def __init__(self, button_results: dict[str, bool] | None = None) -> None:
        self.session_state: dict[str, object] = {}
        self.button_results = button_results or {}
        self.markdowns: list[str] = []
        self.buttons: list[tuple[str, str]] = []
        self.rerun_calls = 0

    def markdown(self, body: str, **_: object) -> None:
        self.markdowns.append(body)

    def container(self, **_: object):
        return nullcontext()

    def columns(self, count: int):
        return [nullcontext() for _ in range(count)]

    def button(self, label: str, *, key: str, **_: object) -> bool:
        self.buttons.append((label, key))
        return self.button_results.get(key, False)

    def rerun(self) -> None:
        self.rerun_calls += 1


def _gate(flow_id: str) -> readiness_gate.ReadinessGate:
    return readiness_gate.ReadinessGate(flow_id, "ready", "stage")


def test_flow_ids_are_registered_to_executable_handlers() -> None:
    assert tuple(readiness_gate.FLOW_HANDLERS) == readiness_gate.ReadinessGate.FLOW_IDS
    assert all(callable(handler) for handler in readiness_gate.FLOW_HANDLERS.values())


def test_unknown_flow_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(readiness_gate, "st", fake_st)

    with pytest.raises(ValueError, match="Unknown readiness gate flow: 'missing'"):
        _gate("missing").render()


@pytest.mark.parametrize(
    ("flow_id", "button_label"),
    [
        ("sentence_repeat", "I did it. I am ready!"),
        ("timeline_paradox", "Ready"),
        ("git_humor", "Force push to main. What could possibly go wrong?"),
        ("bureaucratic", "Past me did their best."),
    ],
)
def test_each_flow_renders_its_expected_initial_action(
    monkeypatch: pytest.MonkeyPatch, flow_id: str, button_label: str
) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(readiness_gate, "st", fake_st)

    assert _gate(flow_id).render() is False

    assert fake_st.buttons == [
        (
            button_label,
            "readiness_gate_ready_button"
            if flow_id in {"sentence_repeat", "timeline_paradox"}
            else "readiness_gate_pre_button",
        )
    ]


@pytest.mark.parametrize(
    ("flow_id", "progress_label", "ready_label"),
    [
        ("git_humor", "Rebasing the timeline...", "Force Push History"),
        ("bureaucratic", "Processing paperwork...", "Authorized"),
    ],
)
def test_staged_flows_advance_to_progress_after_pre_button(
    monkeypatch: pytest.MonkeyPatch,
    flow_id: str,
    progress_label: str,
    ready_label: str,
) -> None:
    fake_st = FakeStreamlit({"readiness_gate_pre_button": True})
    monkeypatch.setattr(readiness_gate, "st", fake_st)

    assert _gate(flow_id).render() is False
    assert fake_st.session_state["stage"] == "progress"
    assert fake_st.rerun_calls == 1

    fake_st.button_results = {}
    assert _gate(flow_id).render() is False
    assert fake_st.buttons[-1] == (ready_label, "readiness_gate_ready_button")
    assert any(progress_label in markdown for markdown in fake_st.markdowns)
    assert "readiness-gate-progress" in "\n".join(fake_st.markdowns)


def test_ready_button_marks_gate_complete_and_reruns(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = FakeStreamlit({"readiness_gate_ready_button": True})
    monkeypatch.setattr(readiness_gate, "st", fake_st)

    assert _gate("sentence_repeat").render() is False

    assert fake_st.session_state["ready"] is True
    assert fake_st.rerun_calls == 1
    assert _gate("sentence_repeat").render() is True
