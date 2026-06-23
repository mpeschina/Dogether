import streamlit as st

st.set_page_config(page_title="Hello World Counter", page_icon=":wave:")


def login_screen():
    st.header("This app is private.")
    st.subheader("Please log in.")
    st.button("Log in with Google", on_click=st.login)


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

if "count" not in st.session_state:
    st.session_state.count = 0

st.title("Hello, World!")
st.write("A tiny Streamlit demo with a button-powered counter.")

if st.button("Click me"):
    st.session_state.count += 1

st.metric("Counter", st.session_state.count)
