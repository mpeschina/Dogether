"""Triggered Assistant story implementations and automatic registration."""
from __future__ import annotations

from importlib import import_module
from inspect import getmembers, isabstract, isclass
from pkgutil import walk_packages
from typing import Final

from src.assistant.triggers import TriggeredAssistantStory


def _discover_story_types() -> tuple[type[TriggeredAssistantStory], ...]:
    """Load every concrete triggered story defined in this package."""
    story_types: list[type[TriggeredAssistantStory]] = []
    for module_info in walk_packages(__path__, f"{__name__}."):
        module = import_module(module_info.name)
        for _, candidate in getmembers(module, isclass):
            if (
                candidate.__module__ == module.__name__
                and issubclass(candidate, TriggeredAssistantStory)
                and not isabstract(candidate)
                and not candidate.__name__.startswith("_")
            ):
                story_types.append(candidate)
    return tuple(sorted(story_types, key=lambda story_type: story_type.story_id))


TRIGGERED_STORY_TYPES: Final = _discover_story_types()

# Re-export the discovered implementations for direct story imports.
for _story_type in TRIGGERED_STORY_TYPES:
    globals()[_story_type.__name__] = _story_type


def triggered_stories() -> dict[str, TriggeredAssistantStory]:
    """Build the complete set of triggered stories owned by this package."""
    stories = [story_type() for story_type in TRIGGERED_STORY_TYPES]
    story_ids = [story.story_id for story in stories]
    if len(story_ids) != len(set(story_ids)):
        raise ValueError("Triggered story IDs must be unique.")
    return {story.story_id: story for story in stories}


__all__ = [
    "TRIGGERED_STORY_TYPES",
    "triggered_stories",
    *(story_type.__name__ for story_type in TRIGGERED_STORY_TYPES),
]
