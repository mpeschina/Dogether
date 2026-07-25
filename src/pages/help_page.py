from __future__ import annotations

import streamlit as st

from src.assistant.events import (
    assistant_leave,
    button_test_event,
    complete_welcome_event,
    event_for_help_visit,
    third_event,
    welcome_event,
)


def render_help(previous_page_key: str | None = None) -> None:
    """Render the session-only scripted assistant experience."""

    _render_styles()
    st.markdown("<div class='assistant-page-heading'>Help</div>", unsafe_allow_html=True)
    st.caption("Dogether Assistant")

    event = event_for_help_visit(st.session_state, previous_page_key=previous_page_key)
    if event == "welcome":
        welcome_event()
        complete_welcome_event(st.session_state)
    elif event == "button_test":
        button_test_event(st.session_state)
    elif event == "third_event":
        third_event(st.session_state)
    else:
        pass

    if event != "third_event":
        st.chat_input("Message the assistant", disabled=True, key="help_assistant_dummy_input")


def _render_styles() -> None:
    st.markdown(
        """
        <style>
          [data-testid="stMainBlockContainer"] {
            max-width: 760px;
            padding-top: 2.75rem;
            padding-bottom: 2rem;
          }
          .assistant-page-heading {
            color: #101828;
            font-size: 1.75rem;
            font-weight: 650;
            letter-spacing: -0.025em;
            line-height: 1.2;
          }
          .assistant-status, .assistant-choice-label {
            color: #98a2b3;
            font-size: 0.78rem;
            text-align: center;
            margin: 0.85rem 0 1rem;
          }
          .assistant-choice-label {
            color: #667085;
            font-weight: 500;
            margin-bottom: 0.5rem;
          }
          .assistant-typing {
            align-items: center;
            background: #f2f4f7;
            border-radius: 1rem;
            display: inline-flex;
            gap: 0.25rem;
            margin: 0.3rem 0 0.8rem 3rem;
            padding: 0.55rem 0.75rem;
          }
          .assistant-typing span {
            animation: assistant-dot-pulse 1.15s infinite ease-in-out;
            background: #98a2b3;
            border-radius: 50%;
            display: inline-block;
            height: 0.38rem;
            width: 0.38rem;
          }
          .assistant-typing span:nth-child(2) { animation-delay: 0.16s; }
          .assistant-typing span:nth-child(3) { animation-delay: 0.32s; }
          @keyframes assistant-dot-pulse {
            0%, 60%, 100% { opacity: 0.35; transform: translateY(0); }
            30% { opacity: 1; transform: translateY(-0.18rem); }
          }
          [data-testid="stHorizontalBlock"] button[kind="secondary"] {
            background: #f8fafc;
            border: 1px solid #d0d5dd;
            border-radius: 0.7rem;
            color: #344054;
            font-weight: 600;
            min-height: 2.7rem;
          }
          [data-testid="stHorizontalBlock"] button[kind="secondary"]:hover {
            background: #eff8ff;
            border-color: #84adf5;
            color: #175cd3;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )
