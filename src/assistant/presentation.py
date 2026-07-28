from __future__ import annotations

import random
import re
import time
from collections.abc import Iterator, MutableMapping
from html import escape
from typing import Any

import streamlit as st

from src.assistant.core import (
    AssistantCard,
    AssistantLine,
    AssistantSelection,
    AssistantTurn,
    ProgressEntry,
)
from src.pages.common_helpers import mini_activity_styles


WORD_DELAY_SECONDS = 0.01
TYPING_DELAY_MIN = 0.6
TYPING_DELAY_MAX = 2.5
CHOICE_FADE_IN_DURATION_MS = 1000
TRANSCRIPT_KEY = "assistant.transcript"
ACTIVE_CONTROL_KEY = "assistant.active_control"
PENDING_SELECTION_KEY = "assistant.pending_selection"
CONTROL_ROUND_KEY = "assistant.control_round"
ASSISTANT_LEFT_THIS_VISIT_KEY = "assistant.left_this_visit"
PERSIST_TRANSCRIPT_ACROSS_PAGE_HOPS_KEY = "assistant.persist_transcript_across_page_hops"
LEGACY_EXPLANATION_STEP_KEYS = (
    "assistant.friends_explanation_step",
    "assistant.goals_explanation_step",
    "assistant.push_explanation_step",
)


def clear_transcript_for_new_help_visit(
    session_state: MutableMapping[str, Any], previous_page_key: str | None
) -> None:
    """Discard transient conversation UI after leaving Help unless retained."""
    if previous_page_key == "help":
        return
    if session_state.pop(PERSIST_TRANSCRIPT_ACROSS_PAGE_HOPS_KEY, False):
        return
    session_state.pop(TRANSCRIPT_KEY, None)
    session_state.pop(ACTIVE_CONTROL_KEY, None)
    session_state.pop(PENDING_SELECTION_KEY, None)
    session_state.pop(CONTROL_ROUND_KEY, None)
    session_state.pop(ASSISTANT_LEFT_THIS_VISIT_KEY, None)
    for key in LEGACY_EXPLANATION_STEP_KEYS:
        session_state.pop(key, None)


def response_generator(
    response: str,
    *,
    delay_seconds: float = WORD_DELAY_SECONDS,
) -> Iterator[str]:
    for word in response.split():
        yield f"{word} "
        time.sleep(delay_seconds)


class StreamlitAssistantView:
    """Transcript renderer and owner of the single active control round."""

    def __init__(self) -> None:
        self.input_rendered = False
        self.selection = self._take_pending_selection()
        self._finished = False
        self._transcript: list[tuple[str, Any]] = st.session_state.setdefault(
            TRANSCRIPT_KEY, []
        )

        self._render_control_styles()
        for kind, content in self._transcript:
            # A submitted control may replace these entries in this same run.
            # Avoid rendering stale live UI before `present` updates it.
            if (
                self.selection is not None
                and kind in {"live_status", "live_progress"}
            ):
                continue
            self._render_transcript_entry(kind, content)

        self._live_transcript = st.container()
        self._control_bar = st.empty()
        active_control = st.session_state.get(ACTIVE_CONTROL_KEY)
        if isinstance(active_control, dict):
            self._render_control(active_control)

    @property
    def waiting_for_input(self) -> bool:
        return (
            isinstance(st.session_state.get(ACTIVE_CONTROL_KEY), dict)
            and self.selection is None
        )

    def present(self, turn: AssistantTurn) -> None:
        """Commit and animate one turn, then expose its next control."""
        self.clear_control()
        if turn.lines:
            self._transcript[:] = [
                entry
                for entry in self._transcript
                if entry[0] != "live_status"
            ]
        if turn.progress:
            self._transcript[:] = [
                entry
                for entry in self._transcript
                if entry[0] != "live_progress"
            ]
        with self._live_transcript:
            if turn.content:
                for item in turn.content:
                    if isinstance(item, AssistantLine):
                        self._present_line(item)
                    else:
                        self._append_and_render("card", item)
            else:
                for line in turn.lines:
                    self._present_line(line)
                for card in turn.cards:
                    self._append_and_render("card", card)
            for message in turn.statuses:
                self._append_and_render(
                    "status" if turn.keep_statuses_in_history else "live_status",
                    message,
                )
            for progress in turn.progress:
                self._append_and_render(
                    "live_progress",
                    {"value": progress.value, "text": progress.text},
                )
            if turn.assistant_leaves:
                self._append_and_render("live_status", "Assistant left the chat")
                st.session_state[ASSISTANT_LEFT_THIS_VISIT_KEY] = True

        if turn.destination:
            st.session_state["assistant.destination"] = turn.destination
        if turn.has_control:
            self._set_control(turn)

    def clear_control(self) -> None:
        st.session_state.pop(ACTIVE_CONTROL_KEY, None)
        self._control_bar.empty()

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        if not self.input_rendered:
            st.chat_input(
                "Message the assistant",
                disabled=True,
                key="help_assistant_dummy_input",
            )
            self.input_rendered = True
        self._scroll_and_position_controls()

    def _present_line(self, line: AssistantLine) -> None:
        if line.wait_before > 0:
            time.sleep(line.wait_before)
        self._transcript.append(("assistant", line.text))
        if line.typing_delay is not None:
            self._typing_indicator(line.typing_delay)
        placeholder = st.empty()
        response = ""
        for part in response_generator(line.text):
            response += part
            self._render_assistant_message(response, placeholder=placeholder)
        if not response:
            self._render_assistant_message(line.text, placeholder=placeholder)
        if line.wait_after > 0:
            time.sleep(line.wait_after)

    def _typing_indicator(self, duration_seconds: float) -> None:
        duration = (
            random.uniform(TYPING_DELAY_MIN, TYPING_DELAY_MAX)
            if duration_seconds == 0
            else duration_seconds
        )
        placeholder = st.empty()
        placeholder.markdown(
            "<div class='assistant-typing' aria-label='Assistant is typing'>"
            "<span></span><span></span><span></span></div>",
            unsafe_allow_html=True,
        )
        time.sleep(max(0, duration))
        placeholder.empty()

    def _set_control(self, turn: AssistantTurn) -> None:
        round_id = int(st.session_state.get(CONTROL_ROUND_KEY, 0)) + 1
        st.session_state[CONTROL_ROUND_KEY] = round_id
        control = {
            "story_id": turn.story_id,
            "scene_id": turn.scene_id,
            "round_id": round_id,
            "kind": turn.control_kind,
            "label": turn.choice_label,
            "record_selection": turn.record_selection,
            "send_placeholder": turn.send_placeholder,
            "choices": [
                {"id": choice.id, "label": choice.label} for choice in turn.choices
            ],
        }
        st.session_state[ACTIVE_CONTROL_KEY] = control
        self._render_control(control)

    def _render_control(self, control: dict[str, Any]) -> None:
        if control.get("kind") == "send":
            self._render_send_control(control)
            return

        choices = control.get("choices")
        if not isinstance(choices, list) or not choices:
            return
        with self._control_bar.container():
            with st.container(
                key=f"assistant-choice-bar-{control.get('round_id')}"
            ):
                label = str(control.get("label", ""))
                if label:
                    st.markdown(
                        f"<div class='assistant-choice-label'>{escape(label)}</div>",
                        unsafe_allow_html=True,
                    )
                columns = st.columns(len(choices))
                for index, (column, raw_choice) in enumerate(zip(columns, choices)):
                    if not isinstance(raw_choice, dict):
                        continue
                    choice_id = str(raw_choice.get("id", ""))
                    choice_label = str(raw_choice.get("label", choice_id))
                    column.button(
                        choice_label,
                        key=f"assistant_choice_{control.get('round_id')}_{index}",
                        type="primary",
                        use_container_width=True,
                        on_click=self._queue_selection,
                        args=(control, choice_id, choice_label),
                    )

    def _render_send_control(self, control: dict[str, Any]) -> None:
        self.input_rendered = True
        round_id = control.get("round_id")
        input_key = f"assistant_send_input_{round_id}"
        placeholder = str(control.get("send_placeholder", "Message the assistant"))
        with self._control_bar.container():
            with st.container(
                key=f"assistant-send-bar-{round_id}"
            ):
                with st.form(
                    f"assistant_send_{round_id}",
                    clear_on_submit=True,
                ):
                    st.text_input(
                        "Message the assistant",
                        label_visibility="collapsed",
                        placeholder=placeholder,
                        key=input_key,
                    )
                    st.form_submit_button(
                        "Send",
                        type="primary",
                        use_container_width=True,
                        on_click=self._queue_selection,
                        args=(control, "send", "Send", input_key),
                    )

    def _queue_selection(
        self,
        control: dict[str, Any],
        choice_id: str,
        label: str,
        input_key: str | None = None,
    ) -> None:
        if input_key is not None:
            submitted = str(st.session_state.get(input_key, "")).strip()
            if submitted:
                label = submitted
        st.session_state.pop(ACTIVE_CONTROL_KEY, None)
        st.session_state[PENDING_SELECTION_KEY] = {
            "story_id": str(control.get("story_id", "")),
            "scene_id": str(control.get("scene_id", "")),
            "choice_id": choice_id,
            "label": label,
            "control_kind": str(control.get("kind", "choices")),
        }
        if bool(control.get("record_selection", True)):
            self._transcript.append(("user", label))

    @staticmethod
    def _take_pending_selection() -> AssistantSelection | None:
        raw = st.session_state.pop(PENDING_SELECTION_KEY, None)
        if not isinstance(raw, dict):
            return None
        return AssistantSelection(
            story_id=str(raw.get("story_id", "")),
            scene_id=str(raw.get("scene_id", "")),
            choice_id=str(raw.get("choice_id", "")),
            label=str(raw.get("label", "")),
            control_kind=str(raw.get("control_kind", "choices")),  # type: ignore[arg-type]
        )

    def _append_and_render(self, kind: str, content: Any) -> None:
        self._transcript.append((kind, content))
        self._render_transcript_entry(kind, content)

    def _render_transcript_entry(self, kind: str, content: Any) -> None:
        if kind in {"assistant", "say"}:
            self._render_assistant_message(str(content))
        elif kind in {"user", "user_choice"}:
            self._render_user_choice(str(content))
        elif kind in {"progress", "live_progress"} and isinstance(content, dict):
            st.progress(float(content.get("value", 0)), text=str(content.get("text", "")))
        elif kind == "card" and isinstance(content, AssistantCard):
            self._render_card(content)
        else:
            st.markdown(
                f"<div class='assistant-status'>{escape(str(content))}</div>",
                unsafe_allow_html=True,
            )

    @staticmethod
    def _render_assistant_message(
        message: str, *, placeholder: Any | None = None
    ) -> None:
        target = st if placeholder is None else placeholder
        safe_message = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(message))
        target.markdown(
            f"<div class='assistant-message'><p>{safe_message.replace(chr(10), '<br>')}</p></div>",
            unsafe_allow_html=True,
        )

    @staticmethod
    def _render_user_choice(message: str) -> None:
        st.markdown(
            f"<div class='assistant-user-choice'><span>{escape(message)}</span></div>",
            unsafe_allow_html=True,
        )

    @staticmethod
    def _render_card(card: AssistantCard) -> None:
        recent_activity = (
            f"<span class='assistant-recent-activity'>{card.recent_activity_html}</span>"
            if card.recent_activity_html
            else ""
        )
        rows = ""
        for index, (left, right) in enumerate(card.rows):
            progress = card.row_progress[index] if index < len(card.row_progress) else None
            row_bar = ""
            row_class = "assistant-card-row"
            if progress is not None:
                value = min(100, max(0, progress))
                row_class += " assistant-card-row-with-progress"
                row_bar = (
                    "<span class='assistant-card-row-track'>"
                    f"<span style='width:{value}%'></span></span>"
                )
            rendered_right = recent_activity if left == "Recent" and recent_activity else escape(right)
            rows += (
                f"<div class='{row_class}'><span>{escape(left)}</span>{row_bar}"
                f"<strong>{rendered_right}</strong></div>"
            )
        bar = ""
        if card.progress is not None:
            value = min(100, max(0, card.progress))
            bar = f"<div class='assistant-card-track'><span style='width:{value}%'></span></div>"
        weekly_chart = ""
        if card.weekly_chart:
            bars = "".join(
                "<span "
                f"class='assistant-weekly-chart-bar {'assistant-weekly-chart-bar-current' if selected else 'assistant-weekly-chart-bar-history'}' "
                f"style='height:{min(100, max(0, rate))}%' "
                f"aria-label='Week of {escape(start.isoformat())}: {rate:.0f}% completion{' (selected)' if selected else ''}'></span>"
                for start, rate, selected in card.weekly_chart
            )
            weekly_chart = (
                "<div class='assistant-weekly-chart' role='img' "
                "aria-label='Weekly completion history; each bar is a week'>"
                f"{bars}</div>"
            )
        st.markdown(
            "<div class='assistant-card'>"
            f"<div class='assistant-card-title'>{escape(card.title)}</div>"
            f"<div class='assistant-card-value'>{escape(card.value)}</div>"
            f"<div class='assistant-card-detail'>{escape(card.detail)}</div>{bar}{weekly_chart}{rows}</div>",
            unsafe_allow_html=True,
        )

    @staticmethod
    def _render_control_styles() -> None:
        styles = """
            <style>
              [data-testid="stMainBlockContainer"] { padding-bottom: 9rem; }
              [class*="st-key-assistant-choice-bar-"],
              [class*="st-key-assistant-send-bar-"] {
                background: var(--background-color, #ffffff);
                box-sizing: border-box;
                left: 50%;
                padding: 0.5rem 0 0.25rem;
                position: fixed;
                transform: translateX(-50%);
                width: min(calc(100% - 2rem), 760px);
                z-index: 999;
              }
              [class*="st-key-assistant-choice-bar-"] {
                animation: assistant-choice-fade-in CHOICE_FADE_IN_DURATION_MS ease-out both;
                bottom: 5.25rem;
              }
              [class*="st-key-assistant-send-bar-"] { bottom: 0.5rem; }
              @keyframes assistant-choice-fade-in {
                from { opacity: 0; }
                to { opacity: 1; }
              }
              @media (prefers-reduced-motion: reduce) {
                [class*="st-key-assistant-choice-bar-"] { animation: none; }
              }
              .assistant-card { background:#f8fafc; border:1px solid #e2e8f0; border-radius:14px; color:#1f2937; margin:.55rem 0 1rem; padding:1rem; }
              .assistant-card-title { color:#4b5563; font-size:.72rem; font-weight:700; letter-spacing:.08em; }
              .assistant-card-value { font-size:1.8rem; font-weight:750; line-height:1.2; margin-top:.25rem; }
              .assistant-card-detail { color:#4b5563; font-size:.9rem; margin:.2rem 0 .65rem; }
              .assistant-card-track { background:#ebedf0; border-radius:99px; height:.55rem; overflow:hidden; margin:.5rem 0 .7rem; }
              .assistant-card-track span { background:#216e39; border-radius:99px; display:block; height:100%; }
              .assistant-card-row { border-top:1px solid #e5e7eb; display:flex; font-size:.88rem; justify-content:space-between; padding:.38rem 0 0; margin-top:.38rem; }
              .assistant-card-row-with-progress { align-items:center; column-gap:.5rem; display:grid; grid-template-columns:1fr minmax(2.5rem, 42%) auto; }
              .assistant-card-row-track { background:#ebedf0; border-radius:99px; display:block; height:.25rem; overflow:hidden; }
              .assistant-card-row-track span { background:var(--primary-color, #1f2937); border-radius:99px; display:block; height:100%; }
              .assistant-weekly-chart { align-items:end; display:flex; gap:.28rem; height:2.25rem; margin:.45rem 0 .7rem; }
              .assistant-weekly-chart-bar { box-sizing:border-box; flex:1; min-width:.3rem; }
              .assistant-weekly-chart-bar-current { background:var(--primary-color, #1f2937); border:1px solid var(--primary-color, #1f2937); border-radius:2px 2px 0 0; }
              .assistant-weekly-chart-bar-history { background:transparent; border:1px solid var(--primary-color, #1f2937); border-radius:2px 2px 0 0; }
              .assistant-recent-activity .mini-activity-dots { gap:3px; }
              .assistant-recent-activity .mini-activity-dot { height:12px; width:12px; }
              .assistant-recent-activity .mini-activity-dot-current { box-shadow:inset 0 0 0 1px rgba(27,31,36,0.14); }
              MINI_ACTIVITY_STYLES
            </style>
            """
        st.markdown(
            styles.replace(
                "CHOICE_FADE_IN_DURATION_MS", f"{CHOICE_FADE_IN_DURATION_MS}ms"
            ).replace("MINI_ACTIVITY_STYLES", mini_activity_styles()),
            unsafe_allow_html=True,
        )

    @staticmethod
    def _scroll_and_position_controls() -> None:
        st.iframe(
            """
            <script>
              const parentWindow = window.parent;
              const parentDocument = parentWindow.document;
              const positionControls = () => {
                const choiceBar = parentDocument.querySelector(
                  '[class*="st-key-assistant-choice-bar-"]'
                );
                const sendBar = parentDocument.querySelector(
                  '[class*="st-key-assistant-send-bar-"]'
                );
                const chatInput = parentDocument.querySelector(
                  '[data-testid="stChatInput"]'
                );
                if (choiceBar && chatInput) {
                  const bounds = chatInput.getBoundingClientRect();
                  choiceBar.style.left = `${bounds.left}px`;
                  choiceBar.style.width = `${bounds.width}px`;
                  choiceBar.style.bottom = `calc(${parentWindow.innerHeight - bounds.top}px + 0.5rem)`;
                  choiceBar.style.transform = 'none';
                }
                if (sendBar) {
                  const main = parentDocument.querySelector(
                    '[data-testid="stMainBlockContainer"]'
                  );
                  if (main) {
                    const bounds = main.getBoundingClientRect();
                    sendBar.style.left = `${bounds.left}px`;
                    sendBar.style.width = `${bounds.width}px`;
                    sendBar.style.transform = 'none';
                  }
                }
              };
              const scrollToBottom = () => {
                const container = parentDocument.querySelector(
                  '[data-testid="stAppViewContainer"]'
                );
                if (container) {
                  container.scrollTo({ top: container.scrollHeight });
                }
                parentWindow.scrollTo({
                  top: parentDocument.body.scrollHeight
                });
              };
              requestAnimationFrame(() => setTimeout(() => {
                positionControls();
                scrollToBottom();
              }, 50));
            </script>
            """,
            height=1,
            tab_index=-1,
        )
