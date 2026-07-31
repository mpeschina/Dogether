from src.assistant.story_session import ASSISTANT_STORY_SESSION_KEY, story_session


def test_story_sessions_are_isolated_and_pruned_after_their_last_value_is_removed() -> None:
    session_state = {}
    greetings = story_session(session_state, "greetings")
    smalltalk = story_session(session_state, "smalltalk")

    greetings.set("selection", "cowboy")
    smalltalk.set("opener", "How are the vibes?")

    assert session_state == {
        ASSISTANT_STORY_SESSION_KEY: {
            "greetings": {"selection": "cowboy"},
            "smalltalk": {"opener": "How are the vibes?"},
        }
    }

    greetings.pop("selection")
    assert session_state[ASSISTANT_STORY_SESSION_KEY] == {
        "smalltalk": {"opener": "How are the vibes?"}
    }

    smalltalk.clear()
    assert session_state == {}
