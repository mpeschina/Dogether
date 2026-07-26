from src.assistant.state import AssistantMode
from src.assistant.stories.push_reminder import PushReminderStory
from src.assistant.stories.special_examples import SpecialExampleStory
from src.assistant.stories.standard import StandardStory
from src.assistant.stories.tutorial import InitialTutorialStory


def default_stories():
    return {
        AssistantMode.NORMAL: StandardStory(),
        AssistantMode.SPECIAL: SpecialExampleStory(),
        "tutorial": InitialTutorialStory(),
        "push_reminder": PushReminderStory(),
    }


__all__ = ["InitialTutorialStory", "PushReminderStory", "SpecialExampleStory", "StandardStory", "default_stories"]
