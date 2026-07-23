from __future__ import annotations

from datetime import datetime
from html import escape

import streamlit as st

from src.db.persistence import Persistence
from src.db.persistence_helpers import REACTION_EMOTES, STANDARD_REACTION_EMOTES, _participant_period_key
from src.pages.account_page import render_activity_diagram
from src.pages.common_helpers import (
    DONE_BUTTON_GREEN,
    DONE_BUTTON_GREEN_ACTIVE,
    DONE_BUTTON_GREEN_HOVER,
    MINI_ACTIVITY_NAME_MAX_LENGTH,
    compact_goal_activity_html,
    mini_activity_styles,
    participant_sparkline_html,
)
from src.pages.health_data_import_page import (
    apple_steps_shortcut_run_url,
    data_import_available_for_viewport,
    health_data_import_settings,
    health_data_import_enabled,
)
from src.pages.page_helpers import participant_name, schedule_label
from src.reaction_component import participant_reaction_row
from src.push.notifications import set_goal_completion_reaction_with_push, update_goal_progress_with_push
from src.push.storage import PushStorage
from src.viewport_component import viewport_info


def ordered_active_participant_ids(goal: dict, current_user_id: str) -> list[str]:
    participants = goal.get("participants", {})
    ordered_ids = [
        uid
        for uid in goal.get("participant_user_ids", [])
        if uid in participants and not participants.get(uid, {}).get("left_at")
    ]
    ordered_id_set = set(ordered_ids)
    ordered_ids.extend(
        sorted(
            uid
            for uid, participant in participants.items()
            if uid not in ordered_id_set and not participant.get("left_at")
        )
    )
    if current_user_id not in ordered_ids:
        return ordered_ids
    return [current_user_id, *[uid for uid in ordered_ids if uid != current_user_id]]


def visible_participant_ids(goal: dict, current_user_id: str, friend_ids: set[str]) -> list[str]:
    return [
        participant_id
        for participant_id in ordered_active_participant_ids(goal, current_user_id)
        if participant_id == current_user_id or participant_id in friend_ids
    ]


def participant_progress_label(current: int, target: int, skipped: bool) -> str:
    if skipped:
        return "skipped"
    return f"{current}/{max(1, target)}"


def truncate_participant_name(name: str, max_length: int = MINI_ACTIVITY_NAME_MAX_LENGTH) -> str:
    if len(name) <= max_length:
        return name
    return f"{name[: max(0, max_length - 3)]}..."


def participant_name_with_progress_html(
    name: str,
    progress_label: str,
    goal: dict | None = None,
    participant: dict | None = None,
    now: datetime | None = None,
) -> str:
    if goal is not None and participant is not None:
        sparkline_html = participant_sparkline_html(goal, participant, now=now)
        dots_html = compact_goal_activity_html(goal, participant, now=now)
    else:
        sparkline_html = ""
        dots_html = ""
    return (
        "<div class='participant-progress-row'>"
        f"<span class='participant-progress-name' title='{escape(name, quote=True)}'>"
        f"<span class='participant-progress-name-text'>{escape(truncate_participant_name(name))}</span>"
        f"{sparkline_html}</span>"
        f"<span class='participant-progress-count'>{escape(progress_label)}</span>"
        f"{dots_html}"
        "</div>"
    )




def participant_goal_is_completed(participant: dict) -> bool:
    if participant.get("skipped"):
        return False
    current = max(0, int(participant.get("current", 0) or 0))
    target = max(1, int(participant.get("target", 1) or 1))
    return current >= target


def participant_period_reactions(participant: dict, goal: dict, now: datetime | None = None) -> dict:
    reactions = participant.get("completion_reactions", {})
    if not isinstance(reactions, dict):
        return {}
    period_key = _participant_period_key(participant, goal, now)
    period_reactions = reactions.get(period_key, {})
    return period_reactions if isinstance(period_reactions, dict) else {}


def current_user_reaction_emote(
    participant: dict,
    goal: dict,
    current_user_id: str | None,
    now: datetime | None = None,
) -> str:
    if not current_user_id:
        return ""
    reaction = participant_period_reactions(participant, goal, now).get(current_user_id)
    if not isinstance(reaction, dict):
        return ""
    emote = reaction.get("emote")
    return str(emote) if emote in REACTION_EMOTES and str(emote).strip() else ""


def participant_reaction_summary(participant: dict, goal: dict, now: datetime | None = None) -> list[tuple[str, int]]:
    counts = {emote: 0 for emote in REACTION_EMOTES}
    for reaction in participant_period_reactions(participant, goal, now).values():
        if not isinstance(reaction, dict):
            continue
        emote = reaction.get("emote")
        if emote in counts:
            counts[emote] += 1
    return [(emote, count) for emote, count in counts.items() if count]


def participant_reaction_details(
    participant: dict,
    goal: dict,
    users: dict[str, dict],
    now: datetime | None = None,
) -> list[dict[str, str]]:
    emote_order = {emote: index for index, emote in enumerate(REACTION_EMOTES)}
    details = []
    for reacting_user_id, reaction in participant_period_reactions(participant, goal, now).items():
        if not isinstance(reaction, dict):
            continue
        emote = reaction.get("emote")
        if emote not in emote_order:
            continue
        name = participant_name(users, str(reacting_user_id))
        details.append({"emote": str(emote), "name": name})
    return sorted(details, key=lambda detail: (emote_order.get(detail["emote"], len(emote_order)), detail["name"].lower()))


def render_goal_actions(
    persistence: Persistence,
    goal: dict,
    participant: dict,
    user_id: str,
    push_storage: PushStorage | None,
    push_settings: dict[str, str] | None,
    now: datetime | None,
    viewport: dict | None = None,
) -> None:
    current = int(participant.get("current", 0))
    target = int(participant.get("target", 1))
    skipped = bool(participant.get("skipped", False))
    actions = st.container(horizontal=True)
    goal_is_done = current >= max(1, target)
    health_data_settings = health_data_import_settings()
    uses_health_data = health_data_import_enabled(goal, user_id)
    can_use_apple_steps_shortcut = uses_health_data and data_import_available_for_viewport(
        health_data_settings.get("apple_steps_shortcut_availability", "ios"),
        viewport,
    )
    if goal_is_done or skipped:
        if skipped and actions.button("Reset", key=f"reset_{goal['id']}", use_container_width=True):
            update_goal_progress_with_push(
                persistence,
                push_storage,
                push_settings or {},
                goal_id=goal["id"],
                user_id=user_id,
                current=0,
                skipped=False,
                now=now,
            )
            st.rerun()
    elif can_use_apple_steps_shortcut:
        shortcut_name = health_data_settings.get("apple_steps_shortcut_name", "Dogether Steps")
        actions.link_button(
            "Input Data",
            apple_steps_shortcut_run_url(shortcut_name),
            type="primary",
            use_container_width=True,
        )
    elif actions.button(
        "Done",
        key=f"done_{goal['id']}",
        type="primary",
        icon=":material/check_circle:",
        use_container_width=True,
    ):
        update_goal_progress_with_push(
            persistence,
            push_storage,
            push_settings or {},
            goal_id=goal["id"],
            user_id=user_id,
            current=max(1, target),
            now=now,
        )
        st.rerun()
    if not skipped:
        with actions.popover("", icon=":material/edit:", help="Edit progress", use_container_width=True):
            
            current_key = f"current_{goal['id']}"
            current = st.number_input(
                "Current",
                min_value=0,
                value=int(participant.get("current", 0)),
                key=current_key,
            )
            manage_actions = st.container(horizontal=True)
            if manage_actions.button("Skip", key=f"skip_{goal['id']}", use_container_width=True):
                            update_goal_progress_with_push(
                                persistence,
                                push_storage,
                                push_settings or {},
                                goal_id=goal["id"],
                                user_id=user_id,
                                skipped=True,
                                now=now,
                            )
                            st.rerun()
            if manage_actions.button("Save", key=f"save_{goal['id']}", type="primary", use_container_width=True):
                update_goal_progress_with_push(
                    persistence,
                    push_storage,
                    push_settings or {},
                    goal_id=goal["id"],
                    user_id=user_id,
                    current=current,
                    now=now,
                )
                st.rerun()


def render_participant_progress(
    goal: dict,
    participant_id: str,
    participant: dict,
    users: dict[str, dict],
    now: datetime | None,
    persistence: Persistence | None = None,
    current_user_id: str | None = None,
    push_storage: PushStorage | None = None,
    push_settings: dict[str, str] | None = None,
) -> None:
    current = int(participant.get("current", 0))
    target = int(participant.get("target", 1))
    skipped = bool(participant.get("skipped", False))
    name = participant_name(users, participant_id)
    progress_label = participant_progress_label(current, target, skipped)
    sparkline_html = participant_sparkline_html(goal, participant, now=now)
    dots_html = compact_goal_activity_html(goal, participant, now=now)
    row_id = f"{goal['id']}:{participant_id}:{_participant_period_key(participant, goal, now)}"
    can_react = (
        persistence is not None
        and current_user_id is not None
        and participant_id != current_user_id
        and not skipped
    )
    reaction = participant_reaction_row(
        row_id=row_id,
        name=name,
        name_html=escape(truncate_participant_name(name)),
        sparkline_html=sparkline_html,
        dots_html=dots_html,
        progress_label=progress_label,
        current=current,
        target=target,
        skipped=skipped,
        reaction_summary=participant_reaction_summary(participant, goal, now),
        reaction_details=participant_reaction_details(participant, goal, users, now),
        standard_emotes=STANDARD_REACTION_EMOTES,
        emotes=REACTION_EMOTES,
        current_user_reaction_emote=current_user_reaction_emote(participant, goal, current_user_id, now),
        can_react=can_react,
        open_picker=st.session_state.get("participant_reaction_open_row") == row_id,
        key=f"participant_reaction_row_{goal['id']}_{participant_id}",
    )
    if not (can_react and isinstance(reaction, dict)):
        return
    action = reaction.get("action")
    emote = reaction.get("emote")
    nonce = reaction.get("nonce")
    processed_key = f"participant_reaction_processed_{row_id}_{action}_{emote}_{nonce}"
    if st.session_state.get(processed_key):
        return
    st.session_state[processed_key] = True
    if action == "toggle":
        st.session_state["participant_reaction_open_row"] = (
            None if st.session_state.get("participant_reaction_open_row") == row_id else row_id
        )
        st.rerun()
    if action == "close":
        if st.session_state.get("participant_reaction_open_row") == row_id:
            st.session_state["participant_reaction_open_row"] = None
            st.rerun()
        return
    if action == "react" and emote in REACTION_EMOTES:
        try:
            set_goal_completion_reaction_with_push(
                persistence,
                push_storage,
                push_settings or {},
                goal_id=goal["id"],
                completed_user_id=participant_id,
                reacting_user_id=current_user_id or "",
                emote=emote,
                now=now,
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state["participant_reaction_open_row"] = None
            st.rerun()


def render_main(
    persistence: Persistence,
    current_user: dict,
    user_id: str,
    push_storage: PushStorage | None = None,
    push_settings: dict[str, str] | None = None,
    now: datetime | None = None,
) -> None:
    st.markdown(
        f"""
        <style>
        div[class*="st-key-done_"] button {{
            background-color: {DONE_BUTTON_GREEN};
            border-color: {DONE_BUTTON_GREEN};
            color: #ffffff;
        }}
        div[class*="st-key-done_"] button:hover {{
            background-color: {DONE_BUTTON_GREEN_HOVER};
            border-color: {DONE_BUTTON_GREEN_HOVER};
            color: #ffffff;
        }}
        div[class*="st-key-done_"] button:active {{
            background-color: {DONE_BUTTON_GREEN_ACTIVE};
            border-color: {DONE_BUTTON_GREEN_ACTIVE};
            color: #ffffff;
        }}
        {mini_activity_styles()}
        </style>
        """,
        unsafe_allow_html=True,
    )

    viewport = viewport_info(require_ready=False) # ensure mobile first, correct on re-run, when necessary
    render_path = "mobile_portrait"
    if isinstance(viewport, dict) and viewport.get("renderPath") == "widescreen":
        render_path = "widescreen"

    stats = persistence.account_stats(user_id, now=now)
    render_activity_diagram(stats.get("activity_days", {}), now=now, days=90)

    goals = persistence.list_goals_for_user(user_id, now=now)
    if not goals:
        st.info("Create a shared goal with a friend to get started.")
        return

    all_participant_ids = sorted({uid for goal in goals for uid in goal.get("participants", {})})
    users = persistence.users_by_ids(all_participant_ids)
    friend_ids = {friend["user_id"] for friend in persistence.list_friends(user_id)}
    for goal in goals:
        with st.container(border=True):
            st.markdown(
                (
                    "<div style='display:flex;align-items:baseline;gap:0.65rem;"
                    "flex-wrap:wrap;margin:0.15rem 0 0.65rem;'>"
                    f"<h3 style='margin:0;'>{escape(goal['description'])}</h3>"
                    "<span style='color:#6b7280;font-size:0.86rem;'>"
                    f"{escape(schedule_label(goal))}"
                    "</span>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            if render_path == "mobile_portrait" and user_id in goal.get("participants", {}):
                render_goal_actions(
                    persistence,
                    goal,
                    goal["participants"][user_id],
                    user_id,
                    push_storage,
                    push_settings,
                    now,
                    viewport,
                )
            participant_ids = visible_participant_ids(goal, user_id, friend_ids)
            for participant_id in participant_ids:
                participant = goal["participants"][participant_id]
                if render_path == "mobile_portrait":
                    render_participant_progress(goal, participant_id, participant, users, now, persistence, user_id, push_storage, push_settings)
                    continue

                cols = st.columns([6, 2])
                with cols[0]:
                    render_participant_progress(goal, participant_id, participant, users, now, persistence, user_id, push_storage, push_settings)
                if participant_id == user_id:
                    with cols[1]:
                        render_goal_actions(
                            persistence,
                            goal,
                            participant,
                            user_id,
                            push_storage,
                            push_settings,
                            now,
                            viewport,
                        )
