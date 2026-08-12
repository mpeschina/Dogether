from __future__ import annotations

from datetime import datetime
import hashlib

import streamlit as st

from src.assistant.core import AssistantContext
from src.assistant.director import AssistantDirector
from src.assistant.state import AssistantState, transient_assistant_state_for_user
from src.assistant.presentation import StreamlitAssistantView, clear_transcript_for_new_help_visit
from src.assistant.stories.information import information_completed
from src.assistant.stories.tutorial import TUTORIAL_STORY_ID
from src.assistant.stories import default_stories
from src.friends.share_links import create_friend_share_link
from src.db.persistence import Persistence
from src.push.storage import PushStorage


# Assistant page colour scheme. These CSS custom properties are also consumed
# by ``src.assistant.presentation`` for controls rendered outside this module.
# Choose one of these palette values for the Assistant badge. Set the active
# color to ``None`` to inherit Streamlit's configured primary color instead.
ASSISTANT_COLORS = {
    "primary": str(st.get_option("theme.primaryColor") or "#1F2937"),
    "sky_blue": "#2E90FA",
    "reddish_pink": "#F0447A",
}
ASSISTANT_ICON_BACKGROUND_COLOR: str = ASSISTANT_COLORS["primary"]
ASSISTANT_ICON_FOREGROUND_COLOR = "#FFFFFF"
ASSISTANT_CHOICE_BUTTON_BACKGROUND_COLOR = ASSISTANT_COLORS["primary"]
ASSISTANT_USER_MESSAGE_BACKGROUND_COLOR = "#687892"
ASSISTANT_PAGE_BACKGROUND_COLOR = "#FFFFFF"
ASSISTANT_MESSAGE_BACKGROUND_COLOR = "#F2F4F7"
ASSISTANT_CONTROL_BAR_BACKGROUND_COLOR = ASSISTANT_PAGE_BACKGROUND_COLOR
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
    Maximum 3-4 assistant bubbles before a choice.
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




def _assistant_star_markup(user_id: str, stars: int) -> str:
    """Return stable STAR decoration for the existing Assistant badge."""
    stars = max(0, int(stars))
    if not stars:
        return ""
    if stars <= 5:
        return (
            "<span class='assistant-star-rating'>"
            f"<span class='assistant-star-filled'>{'&#9733;' * stars}</span>"
            f"{'&#9734;' * (5 - stars)}</span>"
        )
    positions = (
        (14, 18), (82, 18), (13, 52), (85, 52),
        (24, 82), (75, 82), (8, 35), (92, 35),
        (45, 88), (56, 12), (30, 10), (70, 10),
        (7, 68), (93, 68), (37, 91), (64, 91),
    )
    digest = hashlib.sha256(f"{user_id}:{stars}".encode()).digest()
    selected = sorted({byte % len(positions) for byte in digest})[:min(stars, len(positions))]
    overlay = "".join(
        f"<span class='assistant-star-overlay' style='left:{positions[index][0]}%;top:{positions[index][1]}%'>&#9733;</span>"
        for index in selected
    )
    return overlay


def _assistant_star_count_markup(stars: int) -> str:
    stars = max(0, int(stars))
    return f"<span class='assistant-star-count'>&#9733; {stars}</span>" if stars > 5 else ""


def _show_disabled_chat_interface(
    state: AssistantState,
) -> bool:
    """Return whether this visit needs the non-interactive chat affordance."""
    if state.stars <= 0:
        return True
    return state.story == TUTORIAL_STORY_ID


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
    state = transient_assistant_state_for_user(st.session_state, user_id)
    if state is None:
        state = AssistantState.from_profile(current_user)
    icon_background = ASSISTANT_ICON_BACKGROUND_COLOR
    badge_size = ASSISTANT_BADGE_BASE_SIZE_REM * ASSISTANT_BADGE_SIZE_MULTIPLIER
    icon_size = ASSISTANT_ICON_BASE_SIZE_REM * ASSISTANT_ICON_SIZE_MULTIPLIER
    st.markdown(
        "<div class='assistant-page-heading'>"
        "<span id='assistant-star-target' class='assistant-page-icon' aria-label='Assistant STAR count' "
        f"style='--assistant-page-icon-background: {icon_background}; "
        f"--assistant-page-icon-color: {ASSISTANT_ICON_FOREGROUND_COLOR}; "
        f"--assistant-page-badge-size: {badge_size}rem; "
        f"--assistant-page-glyph-size: {icon_size}rem;'>"
        "<span class='material-symbols-rounded'>support_agent</span>"
        f"{_assistant_star_markup(user_id, state.stars)}"
        "</span>"
        f"{_assistant_star_count_markup(state.stars)}"
        "<span>Assistant</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Your friendly helper")

    friends = persistence.list_friends(user_id)
    goals = persistence.list_goals_for_user(user_id, now=now)
    weekly_summary_goals = persistence.list_goal_history_for_user(user_id, now=now)
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
        "weekly_summary_goals": weekly_summary_goals,
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
        record_night_event_completion=lambda: persistence.increment_completed_night_events(
            user_id, now=now
        ),
    )
    view = StreamlitAssistantView(
        show_disabled_chat_interface=_show_disabled_chat_interface(state),
        disabled_chat_story_ids=(TUTORIAL_STORY_ID,),
    )
    director = AssistantDirector(persistence, default_stories())
    director.render(context, view)
    if st.session_state.get("assistant.destination"):
        st.rerun()
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
    color_scheme = f"""
          :root {{
            --assistant-choice-button-background: {ASSISTANT_CHOICE_BUTTON_BACKGROUND_COLOR};
            --assistant-control-bar-background: {ASSISTANT_CONTROL_BAR_BACKGROUND_COLOR};
            --assistant-message-background: {ASSISTANT_MESSAGE_BACKGROUND_COLOR};
            --assistant-page-background: {ASSISTANT_PAGE_BACKGROUND_COLOR};
            --assistant-user-message-background: {ASSISTANT_USER_MESSAGE_BACKGROUND_COLOR};
          }}
    """
    st.markdown(
        """
        <style>
        """
        + color_scheme
        + """
          [data-testid="stAppViewContainer"] {
            background: var(--assistant-page-background);
          }
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
            overflow: hidden;
            position: relative;
            height: var(--assistant-page-badge-size);
            justify-content: center;
            width: var(--assistant-page-badge-size);
          }
          .assistant-star-rating { bottom:.28rem; color:#ffd60a; font-family:Arial,sans-serif; font-size:.68rem; left:50%; letter-spacing:-.08rem; line-height:1; position:absolute; transform:translateX(-50%); white-space:nowrap; }
          .assistant-star-filled, .assistant-star-overlay { text-shadow:0 0 .18rem #fff3a3, 0 0 .42rem rgba(255,214,10,.9); }
          .assistant-star-overlay { color:#ffd60a; font-family:Arial,sans-serif; font-size:.8rem; line-height:1; position:absolute; transform:translate(-50%, -50%); }
          .assistant-star-count { color:#ffd60a; font-family:Arial,sans-serif; font-size:1rem; font-weight:700; letter-spacing:0; white-space:nowrap; }
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
            background: var(--assistant-message-background);
            border-radius: 1rem;
            display: inline-flex;
            gap: 0.25rem;
            margin: 0.3rem 0 0.8rem;
            padding: 0.55rem 0.75rem;
          }
          .assistant-message {
            background: var(--assistant-message-background);
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
            background: var(--assistant-user-message-background);
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
