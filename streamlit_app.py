import streamlit as st

from src.db.persistence import get_configured_persistence
from src.pages.login_page import login_screen

st.set_page_config(page_title="Hello World Counter", page_icon=":wave:")


# Without an [auth] section in the deployed secrets, Streamlit leaves st.user
# empty and does not add the is_logged_in attribute.
if "is_logged_in" not in st.user:
    st.error(
        "Authentication is not configured for this deployment. Add the "
        "[auth] settings to the app's secrets and restart it."
    )
    st.stop()

if not st.user.is_logged_in:
    login_screen()
    st.stop()

st.button("Log out", on_click=st.logout)

user_id = st.user.get("sub")
if not user_id:
    st.error("The login provider did not return a unique user ID (`sub`).")
    st.stop()

try:
    persistence = get_configured_persistence()
    if st.session_state.get("loaded_user_id") != user_id:
        stored_state = persistence.get_user(user_id)
        st.session_state.count = stored_state["count"]
        st.session_state.committed_text = stored_state["text"]
        st.session_state.text_draft = stored_state["text"]
        st.session_state.loaded_user_id = user_id
except Exception as error:
    st.error(f"Could not load your saved state: {error}")
    st.stop()


def save_state(*, count: int, text: str) -> bool:
    try:
        persistence.save_user(user_id, {"count": count, "text": text})
        return True
    except Exception as error:
        st.error(f"Could not save your state: {error}")
        return False

st.title("Hello, World!")
st.write("A tiny Streamlit demo with a button-powered counter.")

if st.button("Click me"):
    new_count = st.session_state.count + 1
    if save_state(count=new_count, text=st.session_state.committed_text):
        st.session_state.count = new_count

st.metric("Counter", st.session_state.count)
st.text_input("Text", key="text_draft", placeholder="Write something to save")
if st.button("Commit") and save_state(
    count=st.session_state.count, text=st.session_state.text_draft
):
    st.session_state.committed_text = st.session_state.text_draft
    st.success("State committed.")
