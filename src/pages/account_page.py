from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from html import escape
from typing import Any
import streamlit as st

from src.assistant.state import AssistantMode, AssistantState, clear_transient_assistant_state
from src.assistant.stories.personal_highlight_tutorial import personal_highlights_unlocked
from src.assistant.story_session import clear_story_sessions, story_session
from src.assistant.stories.greetings import (
    GREETING_PENDING_KEY,
    GREETING_RANDOMIZED_AT_KEY,
    GREETING_SELECTION_KEY,
    GREETINGS_STORY_ID,
)
from src.assistant.stories.smalltalk import SMALLTALK_STORY_ID
from src.db.persistence import Persistence
from src.db.persistence_helpers import APP_ZONE, debug_info_enabled
from src.pages.common_helpers import (
    ACTIVITY_CELL_GAP,
    ACTIVITY_CELL_SIZE,
    ACTIVITY_COLORS,
    activity_color_for_percent,
)


def completed_night_event_count(profile: Mapping[str, Any]) -> int:
    try:
        return max(0, int(profile.get("completed_night_events", 0)))
    except (TypeError, ValueError):
        return 0


def render_account(
    persistence: Persistence,
    current_user: dict,
    user_id: str,
    now: datetime | None = None,
) -> None:
    st.title("Account")
    st.write("Name")
    picture_url = st.user.get("picture")
    if picture_url:
        image_col, name_col = st.columns([0.15, 0.85], vertical_alignment="center", gap="xsmall")
        image_col.image(picture_url, width=80)
        name_col.subheader(current_user["name"])
    else:
        st.subheader(current_user["name"])
    st.write("Email")
    st.subheader(current_user["email"])
    st.caption(debug_account_status(current_user))

    stats = persistence.account_stats(user_id, now=now)
    cols = st.columns(4)
    cols[0].metric("Active goals", stats["active_goals"])
    cols[1].metric("Friends", stats["friend_count"])
    cols[2].metric("Days using app", stats["days_using_app"])
    cols[3].metric("Month completion", f"{stats['completion_rate']}%")
    st.caption(f"Completed night events: {completed_night_event_count(current_user)}")

    st.subheader("Activity")
    render_activity_diagram(stats.get("activity_days", {}), now=now, days=365)
    if personal_highlights_visible(current_user):
        render_personal_bests(current_user, persistence.list_goals_for_user(user_id, now=now))
    if debug_info_enabled(current_user):
        render_assistant_settings(persistence, current_user, user_id, now=now)


def debug_account_status(current_user: Mapping[str, Any]) -> str:
    return "Debug account: enabled" if debug_info_enabled(current_user) else "Debug account: disabled"


def personal_highlights_visible(current_user: Mapping[str, Any]) -> bool:
    """Whether the delayed Assistant unlock permits Personal Highlights to render."""
    return personal_highlights_unlocked(AssistantState.from_profile(current_user))


def personal_best_records(current_user: Mapping[str, Any], goals: list[dict]) -> list[dict[str, object]]:
    """Return display-ready personal bests for active numeric goals only."""
    stored_bests = current_user.get("personal_bests", {})
    if not isinstance(stored_bests, Mapping):
        return []
    records = []
    for goal in goals:
        goal_id = goal.get("id")
        participant = goal.get("participants", {}).get(current_user.get("user_id"), {})
        best = stored_bests.get(goal_id)
        if not isinstance(goal_id, str) or not isinstance(participant, Mapping) or not isinstance(best, Mapping):
            continue
        try:
            target = int(participant.get("target", 1))
            repetitions = int(best.get("repetitions", 0))
        except (TypeError, ValueError):
            continue
        achieved_at = best.get("achieved_at")
        if target <= 1 or repetitions < 1 or not isinstance(achieved_at, str):
            continue
        try:
            achieved = datetime.fromisoformat(achieved_at).astimezone(APP_ZONE)
        except ValueError:
            continue
        records.append(
            {
                "goal": str(goal.get("description") or "Goal"),
                "repetitions": repetitions,
                "achieved": achieved,
            }
        )
    return sorted(records, key=lambda record: (-int(record["repetitions"]), str(record["goal"]).casefold()))


def _ordinal(day: int) -> str:
    suffix = "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def format_personal_best_day(achieved: datetime) -> str:
    return f"{achieved.strftime('%A')} {_ordinal(achieved.day)} of {achieved.strftime('%B %Y')}"


def personal_bests_html(records: list[dict[str, object]]) -> str:
    cards = "".join(
        "<article class='personal-best-card'>"
        "<div class='personal-best-card-heading'>"
        "<span class='personal-best-trophy' aria-hidden='true'>🏆</span>"
        f"<strong class='personal-best-goal'>{escape(str(record['goal']))}</strong>"
        "</div>"
        f"<div class='personal-best-count'>{int(record['repetitions']):,} <span>reps</span></div>"
        f"<div class='personal-best-date'>{escape(format_personal_best_day(record['achieved']))}</div>"
        "<div class='personal-best-cheer'>A personal best — brilliant work!</div>"
        "</article>"
        for record in records
    )
    return (
        "<style>"
        ".personal-bests{margin:1.5rem 0 1.75rem}.personal-bests-heading{display:flex;align-items:center;gap:.45rem;"
        "font-size:1.35rem;font-weight:700;margin-bottom:.2rem}.personal-bests-intro{color:rgba(49,51,63,.72);margin-bottom:.85rem}"
        ".personal-bests-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.75rem}"
        ".personal-best-card{position:relative;overflow:hidden;padding:1rem 1.1rem;border:1px solid #f0c85a;border-radius:16px;"
        "background:linear-gradient(135deg,#fff9df,#fff 62%,#f8edff);box-shadow:0 4px 14px rgba(147,103,9,.12)}"
        ".personal-best-card::after{content:'✦  ✧';position:absolute;right:.7rem;top:.45rem;color:#e7af24;font-size:1.1rem}"
        ".personal-best-card-heading{display:flex;align-items:center;gap:.4rem;padding-right:2.2rem}.personal-best-trophy{font-size:1.35rem}"
        ".personal-best-goal{overflow-wrap:anywhere}.personal-best-count{font-size:1.7rem;font-weight:800;color:#8a5b00;margin:.45rem 0 .1rem}"
        ".personal-best-count span{font-size:.95rem;font-weight:600}.personal-best-date{font-size:.9rem;font-weight:600}"
        ".personal-best-cheer{font-size:.82rem;color:#75612a;margin-top:.5rem}@media(max-width:480px){.personal-bests-grid{grid-template-columns:1fr}}"
        "</style><section class='personal-bests'><div class='personal-bests-heading'>Personal Highlights</div>"
        "<div class='personal-bests-intro'>Your record-breaking moments</div>"
        f"<div class='personal-bests-grid'>{cards}</div></section>"
    )


def render_personal_bests(current_user: Mapping[str, Any], goals: list[dict]) -> None:
    records = personal_best_records(current_user, goals)
    if not records:
        return
    html = personal_bests_html(records)
    if hasattr(st, "html"):
        st.html(html)
    else:
        st.markdown(html, unsafe_allow_html=True)


def render_assistant_settings(
    persistence: Persistence,
    current_user: dict,
    user_id: str,
    *,
    now: datetime | None = None,
) -> None:
    if not debug_info_enabled(current_user):
        return

    st.subheader("Assistant (Prototype)")
    st.caption(
        "Normal runs the guided onboarding and assistant events. "
        "Special runs a selected debug Assistant flow."
    )

    state = AssistantState.from_profile(current_user)
    st.caption("Current assistant state")
    st.json(state.to_dict())
    st.caption("Current assistant transient state")
    st.json(assistant_transient_debug_info(st.session_state))

    widget_key = f"assistant_mode_{user_id}"
    mode_options = [mode.value for mode in AssistantMode]
    selected_mode = st.radio(
        "Assistant mode",
        mode_options,
        index=mode_options.index(state.mode.value),
        format_func=str.title,
        horizontal=True,
        key=widget_key,
    )
    if selected_mode != state.mode.value:
        updated_state = state.with_mode(AssistantMode(selected_mode))
        stored_state = persistence.save_assistant_state(
            user_id,
            updated_state.to_dict(),
            now=now,
        )
        current_user["assistant_state"] = stored_state
        clear_transient_assistant_state(st.session_state, user_id)
        st.rerun()

    if st.button("Reset assistant", key=f"reset_assistant_{user_id}"):
        reset_state = persistence.reset_assistant_state(user_id, now=now)
        current_user["assistant_state"] = reset_state
        reset_assistant_session_state(st.session_state, user_id)
        st.rerun()

    if st.button("Clear greeting session", key=f"clear_greeting_session_{user_id}"):
        clear_greeting_session(st.session_state)
        st.rerun()

    if st.button("Clear smalltalk", key=f"clear_smalltalk_session_{user_id}"):
        clear_smalltalk_session(st.session_state)
        st.rerun()


def greeting_debug_info(session_state: MutableMapping[str, object]) -> dict[str, object]:
    """Expose transient greeting state without adding it to assistant persistence."""
    session = story_session(session_state, GREETINGS_STORY_ID)
    current_greeting = session.get(GREETING_SELECTION_KEY)
    return {
        "greeting": current_greeting,
        "current_greeting_variable": current_greeting,
        "randomized_at": session.get(GREETING_RANDOMIZED_AT_KEY),
        "pending_interaction": session.get(GREETING_PENDING_KEY),
    }


def assistant_transient_debug_info(
    session_state: Mapping[str, object],
) -> dict[str, object]:
    """Return every session value owned by the assistant, ready for JSON debug output."""
    keys = sorted(
        key
        for key in session_state
        if _is_assistant_transient_key(key)
    )
    return {key: _json_debug_value(session_state[key]) for key in keys}


def _is_assistant_transient_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    return key == "help_assistant_dummy_input" or key.startswith(
        (
            "assistant.",
            "assistant_choice_",
            "assistant_mode_",
            "assistant_send_input_",
        )
    )


def _json_debug_value(value: Any) -> object:
    """Make transcript cards and other assistant objects visible in ``st.json``."""
    if is_dataclass(value) and not isinstance(value, type):
        return _json_debug_value(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_debug_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_debug_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def clear_greeting_session(session_state: MutableMapping[str, object]) -> None:
    """Reset only the session-scoped greeting keys used for Help testing."""
    story_session(session_state, GREETINGS_STORY_ID).clear()


def clear_smalltalk_session(session_state: MutableMapping[str, object]) -> None:
    """Reset only the Smalltalk opener and cooldown session values."""
    story_session(session_state, SMALLTALK_STORY_ID).clear()


def reset_assistant_session_state(
    session_state: MutableMapping[str, object], user_id: str
) -> None:
    """Clear every session-scoped assistant value for a fresh assistant reset."""
    clear_transient_assistant_state(session_state, user_id)
    clear_story_sessions(session_state)
    for key in list(session_state):
        if _is_assistant_transient_key(key):
            session_state.pop(key, None)


def render_activity_diagram(
    activity_days: dict,
    now: datetime | None = None,
    *,
    days: int = 365,
    months: int | None = None,
) -> None:
    html = activity_diagram_html(activity_days, now=now, days=days, months=months)
    if hasattr(st, "html"):
        st.html(html)
    else:
        st.markdown(html, unsafe_allow_html=True)


def activity_diagram_html(
    activity_days: dict,
    now: datetime | None = None,
    *,
    days: int = 365,
    months: int | None = None,
) -> str:
    today = _local_date(now)
    if months is not None:
        months = max(1, int(months))
        first_day = _shift_month(today.replace(day=1), -(months - 1))
    else:
        first_day = today - timedelta(days=max(1, int(days)) - 1)
    end_day = today
    grid_start = first_day - timedelta(days=first_day.weekday())
    grid_end = today + timedelta(days=6 - today.weekday())
    total_days = (grid_end - grid_start).days + 1
    week_count = total_days // 7

    month_labels = []
    month_cursor = first_day.replace(day=1)
    while month_cursor <= end_day:
        label_day = max(month_cursor, first_day)
        column = ((label_day - grid_start).days // 7) + 2
        month_labels.append(
            f"<div class='activity-month' style='grid-column:{column};'>{escape(month_cursor.strftime('%b'))}</div>"
        )
        month_cursor = _shift_month(month_cursor, 1)

    weekday_labels = {
        0: "M",
        2: "W",
        4: "F",
    }
    weekday_nodes = [
        f"<div class='activity-weekday' style='grid-row:{weekday + 2};'>{label}</div>"
        for weekday, label in weekday_labels.items()
    ]

    day_nodes = []
    current_day = grid_start
    while current_day <= grid_end:
        week = ((current_day - grid_start).days // 7) + 2
        weekday = current_day.weekday() + 2
        is_visible_day = first_day <= current_day <= end_day
        stats = activity_days.get(current_day.isoformat(), {}) if is_visible_day else {}
        active_goals = int(stats.get("active_goals", 0) or 0)
        fulfilled_goals = int(stats.get("fulfilled_goals", 0) or 0)
        percent = float(stats.get("percent", 0.0) or 0.0)
        color = activity_color_for_percent(percent, active=active_goals > 0) if is_visible_day else "transparent"
        title = escape(
            f"{current_day.isoformat()}: {fulfilled_goals} / {active_goals} goals fulfilled ({percent}%)",
            quote=True,
        )
        day_nodes.append(
            (
                f"<div class='activity-day' title='{title}' "
                f"style='grid-column:{week};grid-row:{weekday};background:{color};'></div>"
            )
        )
        current_day += timedelta(days=1)

    legend_nodes = "".join(f"<span style='background:{color}'></span>" for color in ACTIVITY_COLORS)
    return (
        "<style>"
        f".activity-shell{{--cell:{ACTIVITY_CELL_SIZE};--gap:{ACTIVITY_CELL_GAP};"
        "color:#57606a;max-width:100%;overflow-x:auto;"
        "padding:0.15rem 0 0.35rem;}"
        ".activity-grid{display:grid;grid-template-columns:22px repeat("
        f"{week_count},var(--cell));grid-template-rows:18px repeat(7,var(--cell));"
        "grid-auto-flow:column;gap:var(--gap);align-items:center;}"
        ".activity-month{grid-row:1;font-size:0.76rem;line-height:1;color:#6e7781;white-space:nowrap;}"
        ".activity-weekday{grid-column:1;font-size:0.68rem;line-height:1;color:#6e7781;}"
        ".activity-day{width:var(--cell);height:var(--cell);border-radius:2px;box-shadow:inset 0 0 0 1px rgba(27,31,36,0.06);}"
        ".activity-legend{display:flex;align-items:center;justify-content:flex-end;gap:0.35rem;"
        "font-size:0.72rem;color:#6e7781;margin-top:0.55rem;}"
        ".activity-legend span{width:var(--cell);height:var(--cell);border-radius:2px;"
        "box-shadow:inset 0 0 0 1px rgba(27,31,36,0.06);}"
        "</style>"
        "<div class='activity-shell'>"
        f"<div class='activity-grid'>{''.join(month_labels)}{''.join(weekday_nodes)}{''.join(day_nodes)}</div>"
        f"<div class='activity-legend'>Less{legend_nodes}More</div>"
        "</div>"
    )


def _local_date(now: datetime | None = None) -> date:
    if now is None:
        return datetime.now().date()
    return now.date()


def _shift_month(day: date, offset: int) -> date:
    month_index = day.year * 12 + day.month - 1 + offset
    year, month_zero = divmod(month_index, 12)
    return date(year, month_zero + 1, 1)
