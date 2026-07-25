from __future__ import annotations

from collections.abc import Callable

import streamlit as st


FlowHandler = Callable[["ReadinessGate"], bool]


def print_html(html: str, *, delay: int = 0) -> None:
    """Render centered gate text after an optional CSS animation delay."""
    _, text_column, _ = st.columns(3)
    with text_column:
        st.markdown(
            (
                '<p class="readiness-gate-text" '
                f'style="--readiness-gate-element-delay: {max(0, delay)}s; text-align: center">'
                f"{html}</p>"
            ),
            unsafe_allow_html=True,
        )


def show_progress_bar(*, delay: int = 0, duration: int) -> None:
    """Render the shared progress bar with flow-controlled timing."""
    st.markdown(
        (
            '<div class="readiness-gate-progress" aria-hidden="true" '
            f'style="--readiness-gate-progress-delay: {max(0, delay)}s; '
            f'--readiness-gate-progress-duration: {max(1, duration)}s">'
            '<div class="readiness-gate-progress-fill"></div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def wait_delay(seconds: int, *, target: str = "ready_button") -> None:
    """Delay a gate button without blocking Streamlit's execution."""
    variable = "--readiness-gate-button-delay"
    if target == "pre_button":
        variable = "--readiness-gate-pre-button-delay"
    st.markdown(
        f'<style>div[class~="st-key-readiness_gate"] {{ {variable}: {max(0, seconds)}s; }}</style>',
        unsafe_allow_html=True,
    )


class ReadinessGate:
    """Render and manage a staged confirmation gate for sensitive actions."""

    FLOW_IDS = (
        "sentence_repeat",
        "timeline_paradox",
        "git_humor",
        "bureaucratic",
    )

    def __init__(self, flow_id: str, ready_key: str, stage_key: str) -> None:
        self.flow_id = flow_id
        self.ready_key = ready_key
        self.stage_key = stage_key

    @staticmethod
    def _render_styles() -> None:
        st.markdown(
            """
            <style>
            div[class~="st-key-readiness_gate"] {
                min-height: 62vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
            }
            div[class~="st-key-readiness_gate"] div[data-testid="stMarkdown"] {
                width: 100%;
                text-align: center;
            }
            .readiness-gate-text {
                width: 100%;
                max-width: 34rem;
                margin: 0 auto 0.75rem;
                color: #1f2937;
                text-align: center;
                opacity: 0;
                animation: readiness-gate-fade-in 0.6s ease var(--readiness-gate-element-delay) forwards;
            }
            .readiness-gate-progress {
                width: 100%;
                max-width: 34rem;
                margin: 0 auto;
                height: 0.55rem;
                overflow: hidden;
                border-radius: 999px;
                background: #e5e7eb;
                box-shadow: inset 0 0 0 1px rgba(31, 41, 55, 0.08);
                opacity: 0;
                animation: readiness-gate-fade-in 0.6s ease var(--readiness-gate-progress-delay) forwards;
            }
            .readiness-gate-progress-fill {
                width: 100%;
                height: 100%;
                transform-origin: left center;
                transform: scaleX(0);
                animation: readiness-gate-fill var(--readiness-gate-progress-duration) linear var(--readiness-gate-progress-delay) forwards;
                background: #1f2937;
            }
            div[class*="st-key-readiness_gate_ready_button"],
            div[class*="st-key-readiness_gate_pre_button"] {
                width: 100%;
                max-width: 34rem;
                margin: 1rem auto 0;
                visibility: hidden;
                opacity: 0;
                pointer-events: none;
            }
            div[class*="st-key-readiness_gate_ready_button"] {
                animation: readiness-gate-ready-button 0.8s ease var(--readiness-gate-button-delay) forwards;
            }
            div[class*="st-key-readiness_gate_pre_button"] {
                animation: readiness-gate-ready-button 0.8s ease var(--readiness-gate-pre-button-delay) forwards;
            }
            @keyframes readiness-gate-fade-in {
                to { opacity: 1; }
            }
            @keyframes readiness-gate-fill {
                to { transform: scaleX(1); }
            }
            @keyframes readiness-gate-ready-button {
                to {
                    visibility: visible;
                    opacity: 1;
                    pointer-events: auto;
                }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    def _advance_to_progress(self) -> None:
        st.session_state[self.stage_key] = "progress"
        st.rerun()

    def _complete(self) -> None:
        st.session_state[self.ready_key] = True
        st.rerun()

    def _render_sentence_repeat(self) -> bool:
        print_html('<span style="color:#6b7280;">&quot;Playing around with the Histroy is dangerous.&quot;</span>')
        print_html("<strong>-- repeat this sentence 30 times in your head.</strong>", delay=2)
        show_progress_bar(delay=2, duration=30)
        wait_delay(6)
        if st.button(
            "I did it. I am ready!",
            type="primary",
            use_container_width=True,
            key="readiness_gate_ready_button",
        ):
            self._complete()
        return False

    def _render_timeline_paradox(self) -> bool:
        print_html(
            "⚠️ <strong>Historical records are about to be modified.</strong><br>"
            '<span style="font-size:0.82rem;">(Please avoid creating timeline paradoxes.)</span>'
        )
        print_html(
            "Before proceeding, repeat this sentence 30 times in your head:<br>"
            "<strong>&quot;I will not accidentally invent a new past.&quot;</strong>",
            delay=2,
        )
        show_progress_bar(delay=2, duration=60)
        wait_delay(6)
        if st.button(
            "Ready",
            type="primary",
            use_container_width=True,
            key="readiness_gate_ready_button",
        ):
            self._complete()
        return False

    def _render_git_humor(self) -> bool:
        print_html("You are about to perform a <strong>force push</strong> to history.")
        if st.session_state.get(self.stage_key, "intro") != "progress":
            wait_delay(2, target="pre_button")
            if st.button(
                "Force push to main. What could possibly go wrong?",
                type="primary",
                use_container_width=True,
                key="readiness_gate_pre_button",
            ):
                self._advance_to_progress()
            return False

        print_html("Rebasing the timeline...", delay=2)
        show_progress_bar(duration=60)
        wait_delay(4)
        if st.button(
            "Force Push History",
            type="primary",
            use_container_width=True,
            key="readiness_gate_ready_button",
        ):
            self._complete()
        return False

    def _render_bureaucratic(self) -> bool:
        print_html("<strong>Historical Correction Authorization Required.</strong>")
        if st.session_state.get(self.stage_key, "intro") != "progress":
            print_html("Please complete the mandatory cognitive safety protocol.", delay=3)
            wait_delay(3, target="pre_button")
            if st.button(
                "Past me did their best.",
                type="primary",
                use_container_width=True,
                key="readiness_gate_pre_button",
            ):
                self._advance_to_progress()
            return False

        print_html("Processing paperwork...", delay=3)
        show_progress_bar(duration=20)
        wait_delay(4)
        if st.button(
            "Authorized",
            type="primary",
            use_container_width=True,
            key="readiness_gate_ready_button",
        ):
            self._complete()
        return False

    def render(self) -> bool:
        if st.session_state.get(self.ready_key):
            return True

        handler = FLOW_HANDLERS.get(self.flow_id)
        if handler is None:
            raise ValueError(f"Unknown readiness gate flow: {self.flow_id!r}")

        self._render_styles()
        with st.container(key="readiness_gate"):
            return handler(self)


FLOW_HANDLERS: dict[str, FlowHandler] = {
    "sentence_repeat": ReadinessGate._render_sentence_repeat,
    "timeline_paradox": ReadinessGate._render_timeline_paradox,
    "git_humor": ReadinessGate._render_git_humor,
    "bureaucratic": ReadinessGate._render_bureaucratic,
}
