from collections.abc import Mapping

from src.assistant.core import AssistantStory
from src.assistant.state import AssistantMode
from src.assistant.stories.greetings import GreetingsStory
from src.assistant.stories.push_reminder import PushReminderStory
from src.assistant.stories.special_examples import SpecialExampleStory
from src.assistant.stories.standard import StandardStory
from src.assistant.stories.tutorial import InitialTutorialStory


def default_stories() -> Mapping[AssistantMode | str, AssistantStory]:
    standard = StandardStory()
    special = SpecialExampleStory()
    return {
        AssistantMode.NORMAL: standard,
        "standard": standard,
        "greetings": GreetingsStory(),
        AssistantMode.SPECIAL: special,
        "special_examples": special,
        "tutorial": InitialTutorialStory(),
        "push_reminder": PushReminderStory(),
    }


__all__ = ["GreetingsStory", "InitialTutorialStory", "PushReminderStory", "SpecialExampleStory", "StandardStory", "default_stories"]
