from collections.abc import Mapping

from src.assistant.core import AssistantStory
from src.assistant.state import AssistantMode
from src.assistant.stories.greetings import GreetingsStory
from src.assistant.stories.information import InformationStory
from src.assistant.stories.night import NightStory
from src.assistant.stories.personal_highlight_tutorial import PersonalHighlightTutorialStory
from src.assistant.stories.push_reminder import PushReminderStory
from src.assistant.stories.special_examples import SpecialExampleStory
from src.assistant.stories.smalltalk import SmalltalkStory
from src.assistant.stories.standard import StandardStory
from src.assistant.stories.weekly_summary import WeeklySummaryStory
from src.assistant.stories.weekly_summary_ready import WeeklySummaryReadyStory
from src.assistant.stories.tutorial import InitialTutorialStory
from src.assistant.stories.triggered import TRIGGERED_STORY_TYPES, triggered_stories


for _triggered_story_type in TRIGGERED_STORY_TYPES:
    globals()[_triggered_story_type.__name__] = _triggered_story_type


def default_stories() -> Mapping[AssistantMode | str, AssistantStory]:
    standard = StandardStory()
    special = SpecialExampleStory()
    night = NightStory()
    weekly = WeeklySummaryStory()
    stories: dict[AssistantMode | str, AssistantStory] = {
        AssistantMode.NORMAL: standard,
        "standard": standard,
        "weekly_summary": weekly,
        "weekly_summary_ready": WeeklySummaryReadyStory(),
        "greetings": GreetingsStory(),
        "information": InformationStory(),
        "personal_highlight_tutorial": PersonalHighlightTutorialStory(),
        "night": night,
        AssistantMode.SPECIAL: special,
        "special_examples": special,
        "tutorial": InitialTutorialStory(),
        "push_reminder": PushReminderStory(),
    }
    stories.update(triggered_stories())
    return stories


__all__ = [
    "GreetingsStory",
    "InformationStory",
    "InitialTutorialStory",
    "NightStory",
    "PersonalHighlightTutorialStory",
    "PushReminderStory",
    "SmalltalkStory",
    "SpecialExampleStory",
    "StandardStory",
    "WeeklySummaryStory",
    "WeeklySummaryReadyStory",
    "default_stories",
    *(story_type.__name__ for story_type in TRIGGERED_STORY_TYPES),
]
