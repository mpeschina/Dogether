from __future__ import annotations

from datetime import datetime
import html

import streamlit as st

from src.db.persistence import Persistence
from src.push.notifications import create_friend_invite_with_push
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
        </style>
        """,
        unsafe_allow_html=True,
    )


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
    if incoming:
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

    friends = persistence.list_friends(user_id)
    pending_removals = set(st.session_state.get("friends_pending_removals", []))
    pending_removals &= {friend["user_id"] for friend in friends}
    st.session_state["friends_pending_removals"] = sorted(pending_removals)

    st.subheader("Current friends")
    if not friends:
        st.info("No friends yet.")
    for friend in friends:
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

    outgoing = persistence.outgoing_friend_invites(user_id)
    if outgoing:
        st.subheader("Outgoing pending invites")
        for invite in outgoing:
            st.write(f"To {invite['to_email']}")
