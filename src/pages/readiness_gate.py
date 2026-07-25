from __future__ import annotations

import streamlit as st


class ReadinessGate:
    """Render and manage a staged confirmation gate for sensitive actions."""

    OPTIONS = [
        {
            "id": "sentence_repeat",
            "sentence1_html": '<span style="color:#6b7280;">&quot;Playing around with the Histroy is dangerous.&quot;</span>',
            "wait1_seconds": 2,
            "sentence2_html": "<strong>-- repeat this sentence 30 times in your head.</strong>",
            "wait2_seconds": 4,
            "pre_button_text": None,
            "progress_seconds": 30,
            "button_text": "I did it. I am ready!",
        },
        {
            "id": "timeline_paradox",
            "sentence1_html": (
                "⚠️ <strong>Historical records are about to be modified.</strong><br>"
                '<span style="font-size:0.82rem;">(Please avoid creating timeline paradoxes.)</span>'
            ),
            "wait1_seconds": 2,
            "sentence2_html": (
                "Before proceeding, repeat this sentence 30 times in your head:<br>"
                "<strong>&quot;I will not accidentally invent a new past.&quot;</strong>"
            ),
            "wait2_seconds": 4,
            "pre_button_text": None,
            "progress_seconds": 60,
            "button_text": "Ready",
        },
        {
            "id": "git_humor",
            "sentence1_html": "You are about to perform a <strong>force push</strong> to history.",
            "wait1_seconds": 2,
            "sentence2_html": "",
            "wait2_seconds": 0,
            "pre_button_text": "Force push to main. What could possibly go wrong?",
            "progress_label_html": "Rebasing the timeline...",
            "progress_seconds": 60,
            "final_button_wait_seconds": 4,
            "button_text": "Force Push History",
        },
        {
            "id": "bureaucratic",
            "sentence1_html": "<strong>Historical Correction Authorization Required.</strong>",
            "wait1_seconds": 3,
            "sentence2_html": "Please complete the mandatory cognitive safety protocol.",
            "pre_button_text": "Past me did their best.",
            "progress_label_html": "Processing paperwork...",
            "progress_seconds": 20,
            "final_button_wait_seconds": 4,
            "button_text": "Authorized",
        },

        ## could add another one:  "You only have a short time to answer:"
        ##  Progress bar with only 6 seconds, display a math, like "what is 3149 x 9413?"
    ]

    def __init__(self, option: dict, ready_key: str, stage_key: str) -> None:
        self.option = option
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
            .readiness-gate-game {
                width: 100%;
                max-width: 34rem;
                margin: 0 auto;
                background: #ffffff;
            }
            .readiness-gate-warning {
                margin: 0 0 1rem;
                font-size: 0.92rem;
                text-align: center;
                opacity: 0;
                animation: readiness-gate-fade-in 0.8s ease forwards;
            }
            .readiness-gate-task {
                margin: 0 0 0.75rem;
                color: #1f2937;
                text-align: center;
                opacity: 0;
                animation: readiness-gate-fade-in 0.6s ease var(--readiness-gate-wait-1) forwards;
            }
            .readiness-gate-progress {
                width: 100%;
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

    def render(self) -> bool:
        if st.session_state.get(self.ready_key):
            return True

        self._render_styles()
        option = self.option
        wait1_seconds = max(0, int(option.get("wait1_seconds", 0) or 0))
        wait2_seconds = max(0, int(option.get("wait2_seconds", 0) or 0))
        pre_button_delay_seconds = wait1_seconds + wait2_seconds
        final_button_wait_seconds = max(0, int(option.get("final_button_wait_seconds", wait2_seconds) or 0))
        progress_seconds = option.get("progress_seconds")
        pre_button_text = option.get("pre_button_text")
        stage = st.session_state.get(self.stage_key, "intro")
        progress_active = pre_button_text is None or stage == "progress"
        final_button_delay_seconds = pre_button_delay_seconds if pre_button_text is None else final_button_wait_seconds

        sentence2_html = ""
        if option.get("sentence2_html") and (not progress_active or pre_button_text is None):
            sentence2_html = f'<p class="readiness-gate-task">{option["sentence2_html"]}</p>'

        progress_label_html = ""
        if progress_active and option.get("progress_label_html"):
            progress_label_html = f'<p class="readiness-gate-task">{option["progress_label_html"]}</p>'

        progress_html = ""
        if progress_active and progress_seconds is not None:
            progress_html = (
                '<div class="readiness-gate-progress" aria-hidden="true">'
                '<div class="readiness-gate-progress-fill"></div>'
                "</div>"
            )

        with st.container(key="readiness_gate"):
            st.markdown(
                (
                    "<style>"
                    'div[class~="st-key-readiness_gate"] {'
                    f"--readiness-gate-wait-1: {wait1_seconds}s;"
                    f"--readiness-gate-pre-button-delay: {pre_button_delay_seconds}s;"
                    f"--readiness-gate-button-delay: {final_button_delay_seconds}s;"
                    f"--readiness-gate-progress-delay: {0 if stage == 'progress' else wait1_seconds}s;"
                    f"--readiness-gate-progress-duration: {max(1, int(progress_seconds or 1))}s;"
                    "}"
                    "</style>"
                    '<div class="readiness-gate-game">'
                    f'<p class="readiness-gate-warning">{option["sentence1_html"]}</p>'
                    f"{sentence2_html}"
                    f"{progress_label_html}"
                    f"{progress_html}"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            if pre_button_text is not None and not progress_active:
                if st.button(
                    str(pre_button_text),
                    type="primary",
                    use_container_width=True,
                    key="readiness_gate_pre_button",
                ):
                    st.session_state[self.stage_key] = "progress"
                    st.rerun()
                return False

            if st.button(
                str(option.get("button_text", "Ready")),
                type="primary",
                use_container_width=True,
                key="readiness_gate_ready_button",
            ):
                st.session_state[self.ready_key] = True
                st.rerun()
        return False
