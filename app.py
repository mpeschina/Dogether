import streamlit as st


st.set_page_config(page_title="Hello World Counter", page_icon="👋")

if "count" not in st.session_state:
    st.session_state.count = 0

st.title("Hello, World!")
st.write("A tiny Streamlit demo with a button-powered counter.")

if st.button("Click me"):
    st.session_state.count += 1

st.metric("Counter", st.session_state.count)
