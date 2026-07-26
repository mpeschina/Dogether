from src.assistant.state import AssistantMode
from src.assistant.stories.special_examples import SpecialExampleStory
from src.assistant.stories.tutorial import InitialTutorialStory


def default_stories():
    return {
        AssistantMode.NORMAL: InitialTutorialStory(),
        AssistantMode.SPECIAL: SpecialExampleStory(),
    }


__all__ = ["InitialTutorialStory", "SpecialExampleStory", "default_stories"]
