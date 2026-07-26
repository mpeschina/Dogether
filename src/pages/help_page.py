from __future__ import annotations

from datetime import datetime

import streamlit as st

from src.assistant.core import AssistantContext
from src.assistant.director import AssistantDirector
from src.assistant.state import AssistantState
from src.assistant.presentation import StreamlitAssistantView, clear_transcript_for_new_help_visit
from src.assistant.stories import default_stories
from src.db.persistence import Persistence
from src.push.storage import PushStorage


def render_help(
    persistence: Persistence,
    current_user: dict,
    user_id: str,
    previous_page_key: str | None = None,
    push_storage: PushStorage | None = None,
    *,
    now: datetime | None = None,
) -> None:
    """Render the current user's durable scripted assistant experience."""

    clear_transcript_for_new_help_visit(st.session_state, previous_page_key)
    _render_styles()
    st.markdown("<div class='assistant-page-heading'>Help</div>", unsafe_allow_html=True)
    st.caption("Dogether Assistant")

    state = AssistantState.from_profile(current_user)
    user_state = {
        "has_friends": bool(persistence.list_friends(user_id)),
        "has_goals": bool(persistence.list_goals_for_user(user_id, now=now)),
        "push_enabled": bool(push_storage and push_storage.subscriptions_for_user(user_id)),
    }
    context = AssistantContext(
        user_id=user_id,
        current_user=current_user,
        state=state,
        session_state=st.session_state,
        current_page_key="help",
        previous_page_key=previous_page_key,
        now=now,
        user_state=user_state,
    )
    view = StreamlitAssistantView()
    director = AssistantDirector(persistence, default_stories())
    director.render(context, view)

    if not view.input_rendered:
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
