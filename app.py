import streamlit as st


def login_screen():
    st.header("This app is private.")
    st.subheader("Please log in.")
    if st.button("Log in with Google"):
        st.login()




if not st.user.is_logged_in:
    login_screen()
else:
    st.user


    st.set_page_config(page_title="Hello World Counter", page_icon=":wave:")

    if "count" not in st.session_state:
        st.session_state.count = 0

    st.title("Hello, World!")
    st.write("A tiny Streamlit demo with a button-powered counter.")

    if st.button("Click me"):
        st.session_state.count += 1

    st.metric("Counter", st.session_state.count)
