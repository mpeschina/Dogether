from __future__ import annotations

import streamlit as st

from src.data_imports.health_data_import import handle_health_data_import
from src.db.persistence import Persistence, get_persistence, persistence_settings
from src.friends.alerts import pending_friend_request_alert_items
from src.pages.account_page import render_account
from src.pages.historical_data_repair import (
    READY_OPTION_SESSION_KEY,
    READY_SESSION_KEY,
    render_historical_data_repair,
)
from src.pages.debug_page import DebugMechanics, render_debug
from src.pages.friends_page import render_friends
from src.pages.goals_page import render_goals
from src.pages.health_data_import_page import render_health_data_import
from src.pages.login_page import login_screen
from src.pages.main_page import render_main
from src.pages.push_notifications_page import render_push_notifications
from src.push.sender import push_config
from src.push.storage import get_push_storage, push_storage_settings

st.set_page_config(page_title="Dogether", page_icon=":white_check_mark:", layout="wide")

st.markdown(
    """
    <link rel="manifest" href="./app/static/manifest.json">
    <meta name="theme-color" content="#1F2937">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-title" content="Dogether">
    <link rel="apple-touch-icon" href="./app/static/icon-192.png">
    """,
    unsafe_allow_html=True,
)

try:
    configured_persistence = persistence_settings()
    persistence: Persistence = get_persistence(**configured_persistence)
    configured_push_storage = push_storage_settings()
    push_storage = get_push_storage(**configured_push_storage)
    configured_push = push_config()
    debug = DebugMechanics.from_secrets(persistence)
    app_now = debug.effective_now
except Exception as error:
    st.error(f"Could not load Dogether: {error}")
    st.stop()


debug_user = debug.current_debug_user()
debug_login = debug.debug_login_enabled

if "is_logged_in" not in st.user and not debug_login:
    st.error(
        "Authentication is not configured for this deployment. Add the "
        "[auth] settings to the app's secrets and restart it."
    )
    st.stop()


#
# Login 
#
if not debug_user and not st.user.get("is_logged_in", False):
    login_screen(persistence, debug_login, now=app_now)
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
    current_user = persistence.upsert_user(user_id, user_email, user_name, now=app_now)
except Exception as error:
    st.error(f"Could not load Dogether: {error}")
    st.stop()


handle_health_data_import(
    persistence,
    user_id,
    push_storage,
    configured_push,
    now=app_now,
)

st.sidebar.title("Dogether")
st.sidebar.caption(current_user["email"])
if st.sidebar.button("Log out", use_container_width=True):
    debug.clear_debug_user()
    st.session_state.pop("friend_request_alert_signature", None)
    st.session_state.pop("goals_pending_leave_id", None)
    st.session_state.pop("friends_pending_removals", None)
    if debug_user:
        st.rerun()
    st.logout()


def mark_current_page(page_key: str) -> None:
    previous_page_key = st.session_state.get("current_page_key")
    if page_key != "manage_goals" or previous_page_key != "manage_goals":
        st.session_state.pop("goals_pending_leave_id", None)
    if page_key != "friends" or previous_page_key != "friends":
        st.session_state.pop("friends_pending_removals", None)
    if page_key == "friends" and previous_page_key != "friends":
        st.session_state.pop("show_invite_friend_form", None)
    if page_key == "historical_data_repair" and previous_page_key != "historical_data_repair":
        st.session_state.pop(READY_SESSION_KEY, None)
        st.session_state.pop(READY_OPTION_SESSION_KEY, None)
    st.session_state["current_page_key"] = page_key


def main_page() -> None:
    mark_current_page("goals")
    render_main(persistence, current_user, user_id, push_storage, configured_push, now=app_now)


def friends_page() -> None:
    mark_current_page("friends")
    render_friends(persistence, current_user, user_id, push_storage, configured_push, now=app_now)


def goals_page() -> None:
    mark_current_page("manage_goals")
    render_goals(persistence, user_id, now=app_now)


def historical_data_repair_page() -> None:
    mark_current_page("historical_data_repair")
    render_historical_data_repair(persistence, user_id, now=app_now)


def account_page() -> None:
    mark_current_page("account")
    render_account(persistence, current_user, user_id, now=app_now)


def health_data_import_page() -> None:
    mark_current_page("health_data_import")
    render_health_data_import(persistence, user_id, now=app_now)


def push_notifications_page() -> None:
    mark_current_page("push_notifications")
    render_push_notifications(current_user, user_id, push_storage, configured_push, now=app_now)


def debug_page() -> None:
    mark_current_page("debug")
    render_debug(persistence, push_storage, configured_push)


goals_page_entry = st.Page(main_page, title="Goals", default=True, icon=":material/dashboard:")
friends_page_entry = st.Page(friends_page, title="Friends", icon=":material/group:")
manage_goals_page_entry = st.Page(goals_page, title="Manage Goals", icon=":material/flag:")
historical_data_repair_page_entry = st.Page(historical_data_repair_page, title="Historical Data Repair", icon=":material/edit_calendar:")
health_data_import_page_entry = st.Page(
    health_data_import_page, title="Health Data Import", icon=":material/health_and_safety:"
)
account_page_entry = st.Page(account_page, title="Account", icon=":material/account_circle:")
push_notifications_page_entry = st.Page(
    push_notifications_page, title="Push Notifications", icon=":material/notifications:"
)
debug_page_entry = st.Page(debug_page, title="Debug", icon=":material/bug_report:")
page_entries = [
    goals_page_entry,
    friends_page_entry,
    manage_goals_page_entry,
    historical_data_repair_page_entry,
    health_data_import_page_entry,
    push_notifications_page_entry,
    account_page_entry,
]
if debug.enabled:
    page_entries.append(debug_page_entry)

page = st.navigation(
    page_entries
)


@st.dialog("New Friend Requests")
def friend_request_alert(invite_count: int, signature: str) -> None:
    request_word = "request" if invite_count == 1 else "requests"
    st.write(f"You have {invite_count} new friend {request_word}.")

    cols = st.columns(2)
    if cols[0].button("Show Friend Requests", key="friend_request_alert_show", type="primary", use_container_width=True):
        st.session_state["friend_request_alert_signature"] = signature
        st.switch_page(friends_page_entry)
    if cols[1].button("Ok", key="friend_request_alert_ok", use_container_width=True):
        st.session_state["friend_request_alert_signature"] = signature
        st.rerun()


incoming_friend_requests = pending_friend_request_alert_items(
    persistence,
    current_user["email"],
    user_id,
)
if incoming_friend_requests:
    friend_request_signature = "|".join(
        f"{request_type}:{request_id}"
        for request_type, request_id in incoming_friend_requests
    )
    if st.session_state.get("friend_request_alert_signature") != friend_request_signature:
        friend_request_alert(len(incoming_friend_requests), friend_request_signature)

page.run()
