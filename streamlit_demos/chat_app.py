import streamlit as st
import random
import time
from html import escape


MESSAGES_KEY = "rpg_chat.messages"
ROUND_KEY = "rpg_chat.round"
CHOICES_KEY = "rpg_chat.choices"
TYPING_DELAY_MIN = 0.6
TYPING_DELAY_MAX = 2.5

REPLY_TEMPLATES = (
    "You chose {choice}. A bold move.",
    "{choice} it is. The path opens ahead.",
    "The old machine hums at the number {choice}.",
)

SCENE_MESSAGES = (
    "The room grows quiet.",
    "A distant bell rings once.",
    "Something shifts beyond the doorway.",
    "The map flickers with new light.",
    "A small clock begins to tick.",
)


def render_styles():
    """Apply the same chat visual language used by the assistant presentation."""
    st.markdown(
        """
        <style>
          [data-testid="stMainBlockContainer"] {
            max-width: 760px;
            padding-top: 2.75rem;
            padding-bottom: 9rem;
          }
          .assistant-page-heading {
            align-items: center;
            color: #101828;
            display: flex;
            font-size: 1.75rem;
            font-weight: 650;
            gap: 0.6rem;
            letter-spacing: -0.025em;
            line-height: 1.2;
          }
          .assistant-page-icon {
            align-items: center;
            background: #f2f4f7;
            border-radius: 50%;
            display: inline-flex;
            font-size: 1.1rem;
            height: 2.25rem;
            justify-content: center;
            width: 2.25rem;
          }
          .assistant-message {
            background: #f2f4f7;
            border-radius: 0.35rem 1.25rem 1.25rem;
            color: #101828;
            margin: 0.35rem 0;
            max-width: min(80%, 30rem);
            overflow-wrap: anywhere;
            padding: 0.6rem 0.95rem;
          }
          .assistant-message p { margin: 0; }
          .assistant-typing {
            align-items: center;
            background: #f2f4f7;
            border-radius: 1rem;
            display: inline-flex;
            gap: 0.25rem;
            margin: 0.3rem 0 0.8rem;
            padding: 0.55rem 0.75rem;
          }
          .assistant-typing span {
            animation: assistant-dot-pulse 1.15s infinite ease-in-out;
            background: #98a2b3;
            border-radius: 50%;
            display: inline-block;
            height: 0.38rem;
            width: 0.38rem;
          }
          .assistant-typing span:nth-child(2) { animation-delay: 0.16s; }
          .assistant-typing span:nth-child(3) { animation-delay: 0.32s; }
          .assistant-user-choice {
            display: flex;
            justify-content: flex-end;
            margin: 0.8rem 0;
          }
          .assistant-user-choice span {
            background: var(--primary-color, #1f2937);
            border-radius: 1.4rem 0.35rem 1.4rem 1.4rem;
            color: #ffffff;
            display: inline-block;
            max-width: min(80%, 30rem);
            overflow-wrap: anywhere;
            padding: 0.6rem 0.95rem;
          }
          .st-key-rpg-choice-bar {
            background: var(--background-color, #ffffff);
            bottom: 4.75rem;
            box-sizing: border-box;
            left: 50%;
            padding: 0.5rem 0 0.25rem;
            position: fixed;
            transform: translateX(-50%);
            width: min(calc(100% - 2rem), 760px);
            z-index: 999;
          }
          @keyframes assistant-dot-pulse {
            0%, 60%, 100% { opacity: 0.35; transform: translateY(0); }
            30% { opacity: 1; transform: translateY(-0.18rem); }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_message(role, content, *, placeholder=None):
    """Render a message with the bubbles used by StreamlitAssistantView."""
    target = st if placeholder is None else placeholder
    safe_content = escape(content).replace("\n", "<br>")
    if role == "assistant":
        target.markdown(
            f"<div class='assistant-message'><p>{safe_content}</p></div>",
            unsafe_allow_html=True,
        )
    else:
        target.markdown(
            f"<div class='assistant-user-choice'><span>{safe_content}</span></div>",
            unsafe_allow_html=True,
        )


def scroll_to_latest_message():
    """Keep the browser viewport aligned with the bottom of the transcript."""
    st.iframe(
        """
        <script>
          const positionChoiceBar = () => {
            const choiceBar = window.parent.document.querySelector(
              '.st-key-rpg-choice-bar'
            );
            const chatInput = window.parent.document.querySelector(
              '[data-testid="stChatInput"]'
            );
            if (!choiceBar || !chatInput) return;

            const chatBounds = chatInput.getBoundingClientRect();
            choiceBar.style.position = 'fixed';
            choiceBar.style.left = `${chatBounds.left}px`;
            choiceBar.style.width = `${chatBounds.width}px`;
            choiceBar.style.bottom = `${window.parent.innerHeight - chatBounds.top}px`;
            choiceBar.style.transform = 'none';
          };
          const scrollToBottom = () => {
            const parentWindow = window.parent;
            const scrollContainer = parentWindow.document.querySelector(
              '[data-testid="stAppViewContainer"]'
            );
            if (scrollContainer) {
              scrollContainer.scrollTo({ top: scrollContainer.scrollHeight });
            }
            parentWindow.scrollTo({ top: parentWindow.document.body.scrollHeight });
          };
          requestAnimationFrame(() => setTimeout(() => {
            positionChoiceBar();
            scrollToBottom();
          }, 50));
        </script>
        """,
        height=1,
        tab_index=-1,
    )


def typing_indicator():
    """Show the presentation-style typing dots for a random short pause."""
    placeholder = st.empty()
    duration_seconds = random.uniform(TYPING_DELAY_MIN, TYPING_DELAY_MAX)
    placeholder.markdown(
        "<div class='assistant-typing' aria-label='Assistant is typing'>"
        "<span></span><span></span><span></span></div>",
        unsafe_allow_html=True,
    )
    time.sleep(duration_seconds)
    placeholder.empty()


def new_choices():
    """Create one round of unique numeric choices."""
    return random.sample(range(1, 100), k=random.randint(1, 5))


def add_assistant_messages(choice=None, *, animate=False):
    """Add one to three assistant bubbles before presenting a choice."""
    messages = st.session_state[MESSAGES_KEY]
    message_count = random.randint(1, 3)
    new_messages = []

    if choice is not None:
        new_messages.append(
            random.choice(REPLY_TEMPLATES).format(choice=choice)
        )
        message_count -= 1

    new_messages.extend(random.choices(SCENE_MESSAGES, k=message_count))
    for message in new_messages:
        messages.append({"role": "assistant", "content": message})
        if animate:
            typing_indicator()
            render_message("assistant", message)


def start_next_round(choice=None, *, animate=False):
    st.session_state[ROUND_KEY] += 1
    add_assistant_messages(choice, animate=animate)
    st.session_state[CHOICES_KEY] = new_choices()


def select_choice(choice):
    """Record one player action, then create the next narrated round."""
    messages = st.session_state[MESSAGES_KEY]
    messages.append({"role": "user", "content": str(choice)})
    render_message("user", str(choice))
    start_next_round(choice, animate=True)


render_styles()
st.markdown(
    "<div class='assistant-page-heading'>"
    "<span class='assistant-page-icon' aria-hidden='true'>✨</span>"
    "<span>Simple chat</span>"
    "</div>",
    unsafe_allow_html=True,
)
st.caption("Dogether Assistant")

# Initialize the buffered transcript and the first narrated button round.
if MESSAGES_KEY not in st.session_state:
    st.session_state[MESSAGES_KEY] = []
    st.session_state[ROUND_KEY] = -1
    start_next_round()

# Display every message exclusively from the transcript buffer.
for message in st.session_state[MESSAGES_KEY]:
    render_message(message["role"], message["content"])

# New messages produced by a click are animated here, before the choice bar.
live_transcript = st.container()

choice_bar = st.empty()
with choice_bar.container():
    with st.container(key="rpg-choice-bar"):
        # st.caption("Choose a number")  # --> we dont want to have additional captions build it. They are later to be configured, if needed from the chat flow
        choices = st.session_state[CHOICES_KEY]
        columns = st.columns(len(choices))
        for index, (column, choice) in enumerate(zip(columns, choices)):
            if column.button(
                str(choice),
                key=f"rpg_chat_choice_{st.session_state[ROUND_KEY]}_{index}",
                use_container_width=True,
            ):
                choice_bar.empty()
                with live_transcript:
                    select_choice(choice)
                st.rerun()

# Retain the normal chat layout while choices remain the only enabled input.
st.chat_input(
    "Message the assistant",
    disabled=True,
    key="rpg_chat_disabled_input",
)
scroll_to_latest_message()
