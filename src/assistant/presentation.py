from __future__ import annotations

import time
from collections.abc import Iterator, MutableMapping
from typing import Any

import streamlit as st


WORD_DELAY_SECONDS = 0.05
TRANSCRIPT_KEY = "assistant.transcript"
# Events that deliberately span page hops can set this session flag before the
# user leaves Help.  It is consumed on the next entry to Help.
PERSIST_TRANSCRIPT_ACROSS_PAGE_HOPS_KEY = "assistant.persist_transcript_across_page_hops"


def clear_transcript_for_new_help_visit(
    session_state: MutableMapping[str, Any], previous_page_key: str | None
) -> None:
    """Discard transient chat history after leaving Help, unless explicitly retained."""
    if previous_page_key == "help":
        return
    if session_state.pop(PERSIST_TRANSCRIPT_ACROSS_PAGE_HOPS_KEY, False):
        return
    session_state.pop(TRANSCRIPT_KEY, None)


def response_generator(
    response: str,
    *,
    delay_seconds: float = WORD_DELAY_SECONDS,
) -> Iterator[str]:
    """Yield an assistant response at a constant delay between words."""

    for word in response.split():
        yield f"{word} "
        time.sleep(delay_seconds)


class StreamlitAssistantView:
    def __init__(self) -> None:
        self.input_rendered = False
        self._transcript: list[tuple[str, str]] = st.session_state.setdefault(TRANSCRIPT_KEY, [])
        for kind, content in self._transcript:
            if kind == "say":
                with st.chat_message("assistant", avatar="✨"):
                    st.markdown(content)
            else:
                st.markdown(f"<div class='assistant-status'>{content}</div>", unsafe_allow_html=True)

    def say(self, message: str) -> None:
        self._transcript.append(("say", message))
        with st.chat_message("assistant", avatar="✨"):
            st.write_stream(response_generator(message))

    def typing_indicator(self, duration_seconds: float) -> None:
        placeholder = st.empty()
        placeholder.markdown(
            "<div class='assistant-typing' aria-label='Assistant is typing'>"
            "<span></span><span></span><span></span></div>",
            unsafe_allow_html=True,
        )
        time.sleep(duration_seconds)
        placeholder.empty()

    def wait(self, duration_seconds: float) -> None:
        if duration_seconds < 0:
            raise ValueError("Wait duration must not be negative.")
        time.sleep(duration_seconds)

    def assistant_leave(self) -> None:
        self.status("Assistant left the chat")

    def go_to(self, destination: str) -> None:
        """Switch screens on the next app rerun after an assistant action."""
        st.session_state["assistant.destination"] = destination

    def status(self, message: str) -> None:
        self._transcript.append(("status", message))
        st.markdown(f"<div class='assistant-status'>{message}</div>", unsafe_allow_html=True)

    def selected_choice(self, event_id: str, *options: str) -> str | None:
        """Read a previous-run button click without rendering that button again."""
        for index, option in enumerate(options):
            if st.session_state.get(f"assistant_choice_{event_id}_{index}", False):
                return option
        return None

    def choices(self, event_id: str, label: str, *options: str) -> str | None:
        st.markdown(f"<div class='assistant-choice-label'>{label}</div>", unsafe_allow_html=True)
        columns = st.columns(len(options))
        for index, (column, option) in enumerate(zip(columns, options)):
            if column.button(
                option,
                key=f"assistant_choice_{event_id}_{index}",
                use_container_width=True,
            ):
                return option
        return None

    def send_control(self, event_id: str) -> bool:
        self.input_rendered = True
        with st.form(f"assistant_send_control_{event_id}", clear_on_submit=True):
            st.text_input(
                "Message the assistant",
                label_visibility="collapsed",
                placeholder="Message the assistant",
            )
            return st.form_submit_button("Send", use_container_width=True)

    def progress(self, value: float, text: str) -> None:
        st.progress(value, text=text)

    def rerun(self) -> None:
        st.rerun()
