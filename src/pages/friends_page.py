from __future__ import annotations

from datetime import datetime
import html
from typing import Any

import streamlit as st

from src.db.persistence import Persistence
from src.friends.suggestions import friend_suggestion_candidates, manual_friend_suggestion_options
from src.push.notifications import create_friend_invite_with_push, create_friend_suggestion_with_push
from src.push.storage import PushStorage


def _friend_request_action_styles() -> None:
    st.markdown(
        """
        <style>
            div[data-testid="stElementContainer"]:has(.friend-request-actions)
                ~ div[data-testid="stHorizontalBlock"] div[data-testid="stColumn"]:nth-of-type(2) button,
            div[data-testid="stElementContainer"]:has(.friend-request-actions)
                ~ div[data-testid="stHorizontalBlock"] div[data-testid="column"]:nth-of-type(2) button {
                    background: #dc2626 !important;
                    border-color: #dc2626 !important;
                    color: #ffffff !important;
            }

            div[data-testid="stElementContainer"]:has(.friend-request-actions)
                ~ div[data-testid="stHorizontalBlock"] div[data-testid="stColumn"]:nth-of-type(2) button:hover,
            div[data-testid="stElementContainer"]:has(.friend-request-actions)
                ~ div[data-testid="stHorizontalBlock"] div[data-testid="column"]:nth-of-type(2) button:hover {
                    background: #b91c1c !important;
                    border-color: #b91c1c !important;
                    color: #ffffff !important;
            }

            .friends-mobile-separator {
                display: none;
            }

            @media (max-width: 640px) {
                .friends-mobile-separator {
                    display: block;
                    border: 0;
                    border-top: 1px solid #e5e7eb;
                    margin: 1rem 0;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _friend_display_name(friend: dict[str, Any]) -> str:
    return str(friend.get("name") or friend.get("email") or friend["user_id"])


def _render_friend_suggestion_candidate(
    candidate: dict[str, Any],
    persistence: Persistence,
    push_storage: PushStorage | None,
    push_settings: dict[str, str] | None,
    user_id: str,
    now: datetime | None,
) -> None:
    first_user = candidate["first_user"]
    second_user = candidate["second_user"]
    first_name = _friend_display_name(first_user)
    second_name = _friend_display_name(second_user)
    with st.container(border=True):
        st.markdown(
            f"""
            <article>
                <h3 style="font-size: 1.05rem; margin: 0 0 0.85rem;">
                    {html.escape(first_name)} and {html.escape(second_name)} could be friends.
                    <span style="color: #4b5563; font-weight: 400; font-size: 0.8rem;">
                        (shared goal: {html.escape(candidate["goal_description"])})
                    </span>
                </h3>
            </article>
            """,
            unsafe_allow_html=True,
        )
        cols = st.columns([1, 1, 4])
        if cols[0].button(
            "Suggest friendship",
            key=(
                f"suggest_friendship_{candidate['goal_id']}"
                f"_{first_user['user_id']}_{second_user['user_id']}"
            ),
        ):
            try:
                create_friend_suggestion_with_push(
                    persistence,
                    push_storage,
                    push_settings or {},
                    suggested_by_user_id=user_id,
                    suggested_user_ids=[first_user["user_id"], second_user["user_id"]],
                    source_goal_id=candidate["goal_id"],
                    now=now,
                )
                st.success("Friend suggestion sent.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))
        if cols[1].button(
            "Dismiss",
            key=(
                f"dismiss_friendship_{candidate['goal_id']}"
                f"_{first_user['user_id']}_{second_user['user_id']}"
            ),
        ):
            try:
                persistence.dismiss_friend_suggestion_pair(
                    user_id,
                    first_user["user_id"],
                    second_user["user_id"],
                    now=now,
                )
                st.info("Suggestion dismissed.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))


def render_friends(
    persistence: Persistence,
    current_user: dict,
    user_id: str,
    push_storage: PushStorage | None = None,
    push_settings: dict[str, str] | None = None,
    now: datetime | None = None,
) -> None:
    _friend_request_action_styles()

    st.title("Friends")

    #
    # Incoming Invites Section
    #
    show_invite_form = st.session_state.get("show_invite_friend_form", False)
    if show_invite_form:
        with st.form("add_friend"):
            email = st.text_input("Add friend by email")
            submitted = st.form_submit_button("Send invite")
            if submitted:
                try:
                    create_friend_invite_with_push(
                        persistence,
                        push_storage,
                        push_settings or {},
                        from_user_id=user_id,
                        from_email=current_user["email"],
                        to_email=email,
                        now=now,
                    )
                    st.session_state["show_invite_friend_form"] = False
                    st.success("Friend invite created.")
                except ValueError as error:
                    st.error(str(error))
    elif st.button("Invite friend", type="primary"):
        st.session_state["show_invite_friend_form"] = True
        st.rerun()

    incoming = persistence.incoming_friend_invites(current_user["email"], user_id)
    incoming_suggestions = persistence.incoming_friend_suggestions(user_id)
    if incoming or incoming_suggestions:
        st.subheader("Pending invites")
        for invite in incoming:
            from_user = persistence.get_user(invite["from_user_id"])
            from_name = from_user.get("name") if from_user else invite["from_email"]
            from_email = from_user.get("email", invite["from_email"]) if from_user else invite["from_email"]

            with st.container(border=True):
                st.markdown(
                    f"""
                    <article>
                        <p style="font-size: 0.8rem; letter-spacing: 0; margin: 0 0 0.35rem; text-transform: uppercase; color: #6b7280;">
                            Friend request
                        </p>
                        <h3 style="font-size: 1.05rem; margin: 0 0 0.15rem;">
                            {html.escape(from_name)}
                        </h3>
                        <p style="margin: 0 0 0.85rem; color: #4b5563;">
                            {html.escape(from_email)} wants to add you as a friend.
                        </p>
                    </article>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown('<div class="friend-request-actions"></div>', unsafe_allow_html=True)
                cols = st.columns([1, 1, 5])
                if cols[0].button("Yes", key=f"accept_{invite['id']}", type="primary"):
                    persistence.respond_friend_invite(invite["id"], user_id, current_user["email"], approve=True, now=now)
                    st.success("Friend request accepted.")
                    st.rerun()
                if cols[1].button("No", key=f"decline_{invite['id']}"):
                    persistence.respond_friend_invite(invite["id"], user_id, current_user["email"], approve=False, now=now)
                    st.info("Friend request declined.")
                    st.rerun()

        for suggestion in incoming_suggestions:
            users = persistence.users_by_ids([suggestion["suggested_by_user_id"], *suggestion["suggested_user_ids"]])
            suggester = users.get(suggestion["suggested_by_user_id"], {})
            suggester_name = str(suggester.get("name") or suggester.get("email") or "A friend")
            other_user_id = next(
                candidate_id
                for candidate_id in suggestion["suggested_user_ids"]
                if candidate_id != user_id
            )
            other_user = users.get(other_user_id, {})
            other_name = str(other_user.get("name") or other_user.get("email") or "another friend")

            with st.container(border=True):
                st.markdown(
                    f"""
                    <article>
                        <p style="font-size: 0.8rem; letter-spacing: 0; margin: 0 0 0.35rem; text-transform: uppercase; color: #6b7280;">
                            Friend suggestion
                        </p>
                        <h3 style="font-size: 1.05rem; margin: 0 0 0.15rem;">
                            {html.escape(other_name)}
                        </h3>
                        <p style="margin: 0 0 0.85rem; color: #4b5563;">
                            {html.escape(suggester_name)} suggested you and {html.escape(other_name)} become friends.
                        </p>
                    </article>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown('<div class="friend-request-actions"></div>', unsafe_allow_html=True)
                cols = st.columns([1, 1, 5])
                if cols[0].button(
                    "Yes",
                    key=f"accept_suggestion_{suggestion['id']}",
                    type="primary",
                ):
                    updated = persistence.respond_friend_suggestion(suggestion["id"], user_id, approve=True, now=now)
                    if updated.get("status") == "accepted":
                        st.success("Friend suggestion accepted. You are now friends.")
                    else:
                        st.success("Friend suggestion accepted.")
                    st.rerun()
                if cols[1].button("No", key=f"decline_suggestion_{suggestion['id']}"):
                    persistence.respond_friend_suggestion(suggestion["id"], user_id, approve=False, now=now)
                    st.info("Friend suggestion declined.")
                    st.rerun()

    #
    # Friend Suggestion Section
    #
    friends_for_manual_suggestions, manual_options = manual_friend_suggestion_options(persistence, user_id)
    suggestion_candidates = friend_suggestion_candidates(persistence, user_id, now=now)
    st.subheader("Help your Friends to stay connected!")
    if suggestion_candidates:
        if len(suggestion_candidates) > 3:
            with st.container(height=390):
                for candidate in suggestion_candidates:
                    _render_friend_suggestion_candidate(
                        candidate,
                        persistence,
                        push_storage,
                        push_settings,
                        user_id,
                        now,
                    )
        else:
            for candidate in suggestion_candidates:
                _render_friend_suggestion_candidate(
                    candidate,
                    persistence,
                    push_storage,
                    push_settings,
                    user_id,
                    now,
                )

    with st.expander("Manually choose two friends connect", expanded=False):
        if len(friends_for_manual_suggestions) < 2:
            st.info("Add at least two friends before suggesting a friendship.")
        else:
            friend_by_id = {
                friend["user_id"]: friend
                for friend in friends_for_manual_suggestions
            }
            first_options = [friend["user_id"] for friend in friends_for_manual_suggestions]
            if st.session_state.get("manual_suggest_first_friend") not in first_options:
                st.session_state.pop("manual_suggest_first_friend", None)

            first_user_id = st.selectbox(
                "First friend",
                first_options,
                format_func=lambda candidate_id: _friend_display_name(friend_by_id[candidate_id]),
                key="manual_suggest_first_friend",
            )
            second_options = [
                friend["user_id"]
                for friend in manual_options.get(first_user_id, [])
            ]
            if not second_options:
                first_name = _friend_display_name(friend_by_id[first_user_id])
                st.info(f"{first_name} has no available friends to connect right now.")
            else:
                if st.session_state.get("manual_suggest_second_friend") not in second_options:
                    st.session_state.pop("manual_suggest_second_friend", None)

                second_user_id = st.selectbox(
                    "Second friend",
                    second_options,
                    format_func=lambda candidate_id: _friend_display_name(friend_by_id[candidate_id]),
                    key="manual_suggest_second_friend",
                )
                if st.button("Suggest friendship", key="manual_suggest_friendship_submit", type="primary"):
                    try:
                        create_friend_suggestion_with_push(
                            persistence,
                            push_storage,
                            push_settings or {},
                            suggested_by_user_id=user_id,
                            suggested_user_ids=[first_user_id, second_user_id],
                            source_goal_id=None,
                            now=now,
                        )
                        st.success("Friend suggestion sent.")
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))

    outgoing = persistence.outgoing_friend_invites(user_id)
    outgoing_suggestions = persistence.outgoing_friend_suggestions(user_id)
    if outgoing or outgoing_suggestions:
        st.subheader("Outgoing pending invites")
        for invite in outgoing:
            st.write(f"To {invite['to_email']}")
        for suggestion in outgoing_suggestions:
            suggested_users = persistence.users_by_ids(suggestion["suggested_user_ids"])
            names = [
                suggested_users.get(suggested_user_id, {}).get("name")
                or suggested_users.get(suggested_user_id, {}).get("email")
                or suggested_user_id
                for suggested_user_id in suggestion["suggested_user_ids"]
            ]
            st.write(f"Suggested {names[0]} and {names[1]}")

    #
    # Expandable Friendlist Section
    #
    friends = persistence.list_friends(user_id)
    pending_removals = set(st.session_state.get("friends_pending_removals", []))
    pending_removals &= {friend["user_id"] for friend in friends}
    st.session_state["friends_pending_removals"] = sorted(pending_removals)

    with st.expander("Current friends", expanded=False):
        if not friends:
            st.info("No friends yet.")
        for friend_index, friend in enumerate(friends):
            friend_id = friend["user_id"]
            confirm_remove = friend_id in pending_removals
            remove_label = "Confirm Remove" if confirm_remove else "Remove"
            remove_type = "primary" if confirm_remove else "secondary"

            cols = st.columns([3, 3, 1])
            cols[0].write(friend.get("name", friend["email"]))
            cols[1].write(friend.get("email", ""))
            if cols[2].button(remove_label, key=f"remove_friend_{friend_id}", type=remove_type):
                if confirm_remove:
                    persistence.remove_friend(user_id, friend_id, now=now)
                    pending_removals.discard(friend_id)
                else:
                    pending_removals.add(friend_id)
                st.session_state["friends_pending_removals"] = sorted(pending_removals)
                st.rerun()
            if friend_index < len(friends) - 1:
                st.markdown('<hr class="friends-mobile-separator">', unsafe_allow_html=True)
