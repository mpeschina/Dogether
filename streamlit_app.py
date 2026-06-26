from __future__ import annotations

import streamlit as st

from src.db.persistence import JsonPersistence, get_persistence, persistence_settings
from src.pages.account_page import render_account
from src.pages.friends_page import render_friends
from src.pages.goals_page import render_goals
from src.pages.login_page import login_screen
from src.pages.main_page import render_main

st.set_page_config(page_title="Dogether", page_icon=":white_check_mark:", layout="wide")

try:
    configured_persistence = persistence_settings()
    json_mode = configured_persistence["backend"].strip().lower() == "json"
    persistence = get_persistence(**configured_persistence)
except Exception as error:
    st.error(f"Could not load Dogether: {error}")
    st.stop()


debug_user_id = st.session_state.get("debug_user_id") if json_mode else None
if debug_user_id and isinstance(persistence, JsonPersistence):
    debug_user = persistence.get_user(debug_user_id)
    if not debug_user:
        st.session_state.pop("debug_user_id", None)
        st.rerun()
else:
    debug_user = None

if "is_logged_in" not in st.user and not json_mode:
    st.error(
        "Authentication is not configured for this deployment. Add the "
        "[auth] settings to the app's secrets and restart it."
    )
    st.stop()

if not debug_user and not st.user.get("is_logged_in", False):
    login_screen(persistence, json_mode)
    st.stop()

if debug_user:
    user_id = debug_user["user_id"]
    user_email = debug_user.get("email", "")
    user_name = debug_user.get("name", user_email)
else:
    user_id = st.user.get("sub")
    user_email = st.user.get("email", "")
    user_name = st.user.get("name", user_email)

if not user_id:
    st.error("The login provider did not return a unique user ID (`sub`).")
    st.stop()
if not user_email:
    st.error("The login provider did not return an email address.")
    st.stop()

try:
    current_user = persistence.upsert_user(user_id, user_email, user_name)
except Exception as error:
    st.error(f"Could not load Dogether: {error}")
    st.stop()


st.sidebar.title("Dogether")
st.sidebar.caption(current_user["email"])
if st.sidebar.button("Log out", use_container_width=True):
    st.session_state.pop("debug_user_id", None)
    st.session_state.pop("friend_request_alert_signature", None)
    if debug_user:
        st.rerun()
    st.logout()


def main_page() -> None:
    render_main(persistence, user_id)


def friends_page() -> None:
    render_friends(persistence, current_user, user_id)


def goals_page() -> None:
    render_goals(persistence, user_id)


def account_page() -> None:
    render_account(persistence, current_user, user_id)


goals_page_entry = st.Page(main_page, title="Goals", default=True, icon=":material/dashboard:")
friends_page_entry = st.Page(friends_page, title="Friends", icon=":material/group:")
manage_goals_page_entry = st.Page(goals_page, title="Manage Goals", icon=":material/flag:")
account_page_entry = st.Page(account_page, title="Account", icon=":material/account_circle:")

page = st.navigation(
    [
        goals_page_entry,
        friends_page_entry,
        manage_goals_page_entry,
        account_page_entry,
    ]
)


@st.dialog("New Friend Requests")
def friend_request_alert(invite_count: int, signature: str) -> None:
    request_word = "request" if invite_count == 1 else "requests"
    st.write(f"You have {invite_count} new friend {request_word}.")

    cols = st.columns(2)
    if cols[0].button("Ok", key="friend_request_alert_ok", use_container_width=True):
        st.session_state["friend_request_alert_signature"] = signature
        st.rerun()
    if cols[1].button("Show Friend Requests", key="friend_request_alert_show", use_container_width=True):
        st.session_state["friend_request_alert_signature"] = signature
        st.switch_page(friends_page_entry)


incoming_friend_requests = persistence.incoming_friend_invites(current_user["email"])
if incoming_friend_requests:
    friend_request_signature = "|".join(invite["id"] for invite in incoming_friend_requests)
    if st.session_state.get("friend_request_alert_signature") != friend_request_signature:
        friend_request_alert(len(incoming_friend_requests), friend_request_signature)

page.run()
