import streamlit as st


def login_screen():
    st.header("Dogether")
    st.button("Log in with Google", on_click=st.login)
