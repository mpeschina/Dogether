from __future__ import annotations

import streamlit as st

from src.db.persistence import get_configured_persistence
from src.pages.account_page import render_account
from src.pages.friends_page import render_friends
from src.pages.goals_page import render_goals
from src.pages.login_page import login_screen
from src.pages.main_page import render_main
from src.pages.notifications_page import render_notifications

st.set_page_config(page_title="Dogether", page_icon=":white_check_mark:", layout="wide")


if "is_logged_in" not in st.user:
    st.error(
        "Authentication is not configured for this deployment. Add the "
        "[auth] settings to the app's secrets and restart it."
    )
    st.stop()

if not st.user.is_logged_in:
    login_screen()
    st.stop()

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
    persistence = get_configured_persistence()
    current_user = persistence.upsert_user(user_id, user_email, user_name)
except Exception as error:
    st.error(f"Could not load Dogether: {error}")
    st.stop()


st.sidebar.title("Dogether")
st.sidebar.caption(current_user["email"])
if st.sidebar.button("Log out", use_container_width=True):
    st.logout()

view = st.sidebar.radio(
    "View",
    ["Main", "Notifications", "Friends", "Goals", "Account"],
    label_visibility="collapsed",
)


if view == "Main":
    render_main(persistence, user_id)
elif view == "Notifications":
    render_notifications(persistence, current_user, user_id)
elif view == "Friends":
    render_friends(persistence, current_user, user_id)
elif view == "Goals":
    render_goals(persistence, user_id)
elif view == "Account":
    render_account(persistence, current_user, user_id)
