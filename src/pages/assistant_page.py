from __future__ import annotations

from datetime import datetime

import streamlit as st

from src.assistant.core import AssistantContext
from src.assistant.director import AssistantDirector
from src.assistant.state import AssistantState, transient_assistant_state_for_user
from src.assistant.presentation import StreamlitAssistantView, clear_transcript_for_new_help_visit
from src.assistant.stories.information import information_completed
from src.assistant.stories import default_stories
from src.friends.share_links import create_friend_share_link
from src.db.persistence import Persistence
from src.push.storage import PushStorage


# Choose one of these palette values for the Assistant badge. Set the active
# color to ``None`` to inherit Streamlit's configured primary color instead.
ASSISTANT_COLORS = {
    "light_ash": "#687B99",
    "sky_blue": "#2E90FA",
    "reddish_pink": "#F0447A",
}
ASSISTANT_ICON_BACKGROUND_COLOR: str | None = ASSISTANT_COLORS["light_ash"]
ASSISTANT_ICON_FOREGROUND_COLOR = "#FFFFFF"
ASSISTANT_BADGE_SIZE_MULTIPLIER: float = 1.0
ASSISTANT_ICON_SIZE_MULTIPLIER: float = 1.0
ASSISTANT_BADGE_BASE_SIZE_REM = 3.5
ASSISTANT_ICON_BASE_SIZE_REM = 1.6



"""Explanation of the RPG Assistant: 

Each story is deliberately written as small, declarative scenes. The director
persists completed state; unfinished scene progress remains session-scoped.

Core interaction style:
    The assistant should feel like a friendly NPC.

Rules:

    One thought per message.
    Usually 2-10 words.
    Never more than ~18 words.
    Maximum 2-3 assistant bubbles before a choice.
    Choices are buttons.
    Fake typing between meaningful beats.
    Never ask open-ended questions when a button works.
    Use known user data directly.
    Never explain what it is checking.

For example, avoid:
“I've analyzed your profile and noticed that you currently only have one friend, which may limit your experience.”

Instead:
    “I had a look.”
    typing…
    “You have one friend here.”
    “Let's fix that.”

    [Invite someone] [Not now]
"""




def render_assistant(
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
    icon_background = ASSISTANT_ICON_BACKGROUND_COLOR or str(
        st.get_option("theme.primaryColor") or "#1F2937"
    )
    badge_size = ASSISTANT_BADGE_BASE_SIZE_REM * ASSISTANT_BADGE_SIZE_MULTIPLIER
    icon_size = ASSISTANT_ICON_BASE_SIZE_REM * ASSISTANT_ICON_SIZE_MULTIPLIER
    st.markdown(
        "<div class='assistant-page-heading'>"
        "<span class='assistant-page-icon' aria-hidden='true' "
        f"style='--assistant-page-icon-background: {icon_background}; "
        f"--assistant-page-icon-color: {ASSISTANT_ICON_FOREGROUND_COLOR}; "
        f"--assistant-page-badge-size: {badge_size}rem; "
        f"--assistant-page-glyph-size: {icon_size}rem;'>"
        "<span class='material-symbols-rounded'>support_agent</span>"
        "</span>"
        "<span>Assistant</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Your friendly helper")

    state = transient_assistant_state_for_user(st.session_state, user_id)
    if state is None:
        state = AssistantState.from_profile(current_user)
    friends = persistence.list_friends(user_id)
    goals = persistence.list_goals_for_user(user_id, now=now)
    user_state = {
        # Counts let the assistant acknowledge a healthy profile without
        # treating one friend or several goals as the same situation.
        "friend_count": len(friends),
        "goal_count": len(goals),
        # Kept for other stories that may still use the older predicates.
        "has_friends": bool(friends),
        "has_goals": bool(goals),
        "push_enabled": bool(push_storage and push_storage.subscriptions_for_user(user_id)),
        "completed_goal_count": _completed_goal_period_count(goals, user_id),
        "goals": goals,
        # Weekly shared-goal insights may only identify people who are already
        # approved friends of the current user.
        "friend_profiles": {friend["user_id"]: friend for friend in friends if friend.get("user_id")},
    }
    context = AssistantContext(
        user_id=user_id,
        current_user=current_user,
        state=state,
        session_state=st.session_state,
        current_page_key="assistant",
        previous_page_key=previous_page_key,
        now=now,
        user_state=user_state,
        create_friend_share_link=lambda: create_friend_share_link(
            persistence, user_id, st.session_state, now=now
        ),
    )
    view = StreamlitAssistantView()
    director = AssistantDirector(persistence, default_stories())
    director.render(context, view)
    if information_completed(st.session_state):
        if st.button("Go Main Page", type="primary", use_container_width=True):
            st.session_state["assistant.destination"] = "goals"
            st.rerun()


def _completed_goal_period_count(goals: list[dict], user_id: str) -> int:
    """Count durable completed periods plus a currently completed period."""
    completed = 0
    for goal in goals:
        participant = goal.get("participants", {}).get(user_id, {})
        if not isinstance(participant, dict):
            continue
        outcomes = participant.get("period_outcomes", {})
        if isinstance(outcomes, dict):
            completed += sum(
                1 for outcome in outcomes.values()
                if isinstance(outcome, dict) and outcome.get("completed") is True
            )
        current = max(0, int(participant.get("current", 0) or 0))
        target = max(1, int(participant.get("target", 1) or 1))
        if not participant.get("skipped", False) and current >= target:
            completed += 1
    return completed


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
            align-items: center;
            display: flex;
            font-size: 1.75rem;
            font-weight: 650;
            gap: 0.6rem;
            letter-spacing: -0.025em;
            line-height: 1.2;
          }
          .assistant-page-icon {
            align-items: center;
            background: var(--assistant-page-icon-background);
            border-radius: 0.65rem;
            color: var(--assistant-page-icon-color);
            display: inline-flex;
            font-size: var(--assistant-page-glyph-size);
            height: var(--assistant-page-badge-size);
            justify-content: center;
            width: var(--assistant-page-badge-size);
          }
          .assistant-page-icon .material-symbols-rounded {
            font-family: 'Material Symbols Rounded';
            font-size: var(--assistant-page-glyph-size);
            font-weight: normal;
            font-style: normal;
            line-height: 1;
            letter-spacing: normal;
            text-transform: none;
            white-space: nowrap;
            word-wrap: normal;
            direction: ltr;
            -webkit-font-feature-settings: 'liga';
            -webkit-font-smoothing: antialiased;
            font-feature-settings: 'liga';
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
            margin: 0.3rem 0 0.8rem;
            padding: 0.55rem 0.75rem;
          }
          .assistant-message {
            background: #f2f4f7;
            border-radius: 0.35rem 1.25rem 1.25rem;
            color: #101828;
            margin: 0.35rem 0;
            max-width: min(80%, 30rem);
            padding: 0.6rem 0.95rem;
            overflow-wrap: anywhere;
          }
          .assistant-message p {
            margin: 0;
          }
          .assistant-message a {
            color: inherit;
            text-decoration: underline;
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
          .assistant-user-choice {
            display: flex;
            justify-content: flex-end;
            margin: 0.8rem 0;
          }
          .assistant-user-choice span {
            background: var(--primary-color, #1f2937);
            border-radius: 1.4rem 0.35rem 1.4rem 1.4rem;
            color: #ffffff;
            display: inline-block;
            max-width: min(80%, 30rem);
            padding: 0.6rem 0.95rem;
            text-align: center;
            overflow-wrap: anywhere;
          }
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
