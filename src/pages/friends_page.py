from __future__ import annotations

import streamlit as st


def render_friends(persistence, current_user: dict, user_id: str) -> None:
    st.title("Friends")
    with st.form("add_friend"):
        email = st.text_input("Add friend by email")
        submitted = st.form_submit_button("Send invite")
        if submitted:
            try:
                persistence.create_friend_invite(user_id, current_user["email"], email)
                st.success("Friend invite created.")
            except ValueError as error:
                st.error(str(error))

    friends = persistence.list_friends(user_id)
    st.subheader("Current friends")
    if not friends:
        st.info("No friends yet.")
    for friend in friends:
        cols = st.columns([3, 3, 1])
        cols[0].write(friend.get("name", friend["email"]))
        cols[1].write(friend.get("email", ""))
        if cols[2].button("Remove", key=f"remove_friend_{friend['user_id']}"):
            persistence.remove_friend(user_id, friend["user_id"])
            st.rerun()

    st.subheader("Incoming pending invites")
    incoming = persistence.incoming_friend_invites(current_user["email"])
    if not incoming:
        st.caption("None")
    for invite in incoming:
        st.write(f"From {invite['from_email']}")

    st.subheader("Outgoing pending invites")
    outgoing = persistence.outgoing_friend_invites(user_id)
    if not outgoing:
        st.caption("None")
    for invite in outgoing:
        st.write(f"To {invite['to_email']}")
