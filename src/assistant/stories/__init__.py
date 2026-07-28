from collections.abc import Mapping

from src.assistant.core import AssistantStory
from src.assistant.state import AssistantMode
from src.assistant.stories.greetings import GreetingsStory
from src.assistant.stories.push_reminder import PushReminderStory
from src.assistant.stories.special_examples import SpecialExampleStory
from src.assistant.stories.standard import StandardStory
from src.assistant.stories.weekly_summary import WeeklySummaryStory
from src.assistant.stories.tutorial import InitialTutorialStory


def default_stories() -> Mapping[AssistantMode | str, AssistantStory]:
    standard = StandardStory()
    special = SpecialExampleStory()
    weekly = WeeklySummaryStory()
    return {
        AssistantMode.NORMAL: standard,
        "standard": standard,
        "weekly_summary": weekly,
        "greetings": GreetingsStory(),
        AssistantMode.SPECIAL: special,
        "special_examples": special,
        "tutorial": InitialTutorialStory(),
        "push_reminder": PushReminderStory(),
    }


__all__ = ["GreetingsStory", "InitialTutorialStory", "PushReminderStory", "SpecialExampleStory", "StandardStory", "WeeklySummaryStory", "default_stories"]
