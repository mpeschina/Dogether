"""Namespaced, session-only values owned by assistant stories."""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any, Final


ASSISTANT_STORY_SESSION_KEY: Final = "assistant.story_session"


class StorySession:
    """A mutable namespace inside the shared Streamlit session mapping."""

    def __init__(self, session_state: MutableMapping[str, object], story_id: str) -> None:
        if not story_id:
            raise ValueError("Story session namespaces require a story ID.")
        self._session_state = session_state
        self._story_id = story_id

    def get(self, key: str, default: Any = None) -> Any:
        return self._values(create=False).get(key, default)

    def set(self, key: str, value: object) -> None:
        self._values(create=True)[key] = value

    def pop(self, key: str, default: Any = None) -> Any:
        values = self._values(create=False)
        value = values.pop(key, default)
        self._prune_if_empty(values)
        return value

    def clear(self) -> None:
        root = self._root(create=False)
        root.pop(self._story_id, None)
        if not root:
            self._session_state.pop(ASSISTANT_STORY_SESSION_KEY, None)

    def values(self) -> Mapping[str, object]:
        """Expose a read-only view suitable for inspection and debugging."""
        return dict(self._values(create=False))

    def _values(self, *, create: bool) -> MutableMapping[str, object]:
        root = self._root(create=create)
        values = root.get(self._story_id)
        if isinstance(values, MutableMapping):
            return values
        if create:
            created: dict[str, object] = {}
            root[self._story_id] = created
            return created
        return {}

    def _root(self, *, create: bool) -> MutableMapping[str, object]:
        root = self._session_state.get(ASSISTANT_STORY_SESSION_KEY)
        if isinstance(root, MutableMapping):
            return root
        if create:
            created: dict[str, object] = {}
            self._session_state[ASSISTANT_STORY_SESSION_KEY] = created
            return created
        return {}

    def _prune_if_empty(self, values: Mapping[str, object]) -> None:
        if values:
            return
        root = self._root(create=False)
        root.pop(self._story_id, None)
        if not root:
            self._session_state.pop(ASSISTANT_STORY_SESSION_KEY, None)


def story_session(
    session_state: MutableMapping[str, object], story_id: str
) -> StorySession:
    return StorySession(session_state, story_id)


def clear_story_sessions(session_state: MutableMapping[str, object]) -> None:
    """Remove all session-only state owned by assistant stories."""
    session_state.pop(ASSISTANT_STORY_SESSION_KEY, None)
