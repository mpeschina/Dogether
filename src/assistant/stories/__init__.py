from collections.abc import Mapping

from src.assistant.core import AssistantStory
from src.assistant.state import AssistantMode
from src.assistant.stories.greetings import GreetingsStory
from src.assistant.stories.information import InformationStory
from src.assistant.stories.night import NightStory
from src.assistant.stories.push_reminder import PushReminderStory
from src.assistant.stories.special_examples import SpecialExampleStory
from src.assistant.stories.smalltalk import SmalltalkStory
from src.assistant.stories.standard import StandardStory
from src.assistant.stories.weekly_summary import WeeklySummaryStory
from src.assistant.stories.weekly_summary_ready import WeeklySummaryReadyStory
from src.assistant.stories.tutorial import InitialTutorialStory


def default_stories() -> Mapping[AssistantMode | str, AssistantStory]:
    standard = StandardStory()
    special = SpecialExampleStory()
    night = NightStory()
    weekly = WeeklySummaryStory()
    return {
        AssistantMode.NORMAL: standard,
        "standard": standard,
        "weekly_summary": weekly,
        "weekly_summary_ready": WeeklySummaryReadyStory(),
        "greetings": GreetingsStory(),
        "information": InformationStory(),
        "night": night,
        AssistantMode.SPECIAL: special,
        "special_examples": special,
        "tutorial": InitialTutorialStory(),
        "push_reminder": PushReminderStory(),
    }


__all__ = ["GreetingsStory", "InformationStory", "InitialTutorialStory", "NightStory", "PushReminderStory", "SmalltalkStory", "SpecialExampleStory", "StandardStory", "WeeklySummaryStory", "WeeklySummaryReadyStory", "default_stories"]
