from __future__ import annotations

import streamlit as st


def render_notifications(persistence, current_user: dict, user_id: str) -> None:
    st.title("Pending Notifications")
    invites = persistence.incoming_friend_invites(current_user["email"])
    if not invites:
        st.info("No pending notifications.")
        return

    for invite in invites:
        st.subheader("Friend request")
        st.write(f"{invite['from_email']} wants to add you as a friend.")
        cols = st.columns([1, 1, 5])
        if cols[0].button("Yes", key=f"accept_{invite['id']}"):
            persistence.respond_friend_invite(invite["id"], user_id, current_user["email"], approve=True)
            st.success("Friend request accepted.")
            st.rerun()
        if cols[1].button("No", key=f"decline_{invite['id']}"):
            persistence.respond_friend_invite(invite["id"], user_id, current_user["email"], approve=False)
            st.info("Friend request declined.")
            st.rerun()
        st.divider()
