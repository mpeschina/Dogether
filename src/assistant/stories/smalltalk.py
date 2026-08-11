"""A lightweight, menu-only Smalltalk placeholder."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Final

from src.assistant.core import (
    AssistantChoice,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
)
from src.assistant.story_session import story_session
from src.assistant.stories.tutorial import STANDARD_STORY_ID


SMALLTALK_STORY_ID: Final = "smalltalk"
SMALLTALK_MENU_CHOICE_ID: Final = "smalltalk"
SMALLTALK_PLACEHOLDER_SCENE: Final = "smalltalk.unavailable"
STANDARD_MENU_SCENE: Final = "standard.menu"
SMALLTALK_OPENER_KEY: Final = "opener"
SMALLTALK_OPENER_SELECTED_AT_KEY: Final = "opener_selected_at"
SMALLTALK_OPENER_INTERVAL: Final = timedelta(hours=3)
SMALLTALK_CLICKED_AT_KEY: Final = "clicked_at"
SMALLTALK_COOLDOWN: Final = timedelta(hours=1)
SMALLTALK_UNAVAILABLE_RESPONSE: Final = "Smalltalk is currently unavailable."

# A joke ends by gently remembering that this is, useful assistant. 
SMALLTALK_HELP_OFFERS: Final = (
    (
        "But enough about my diagnostics.",
        "What’s happening with you and ",
        "how can I help today?",
    ),
    (
        "That concludes the smalltalk portion of my duties with you.",
        "I do believe I can be useful for you.",
        "What can I help you with?",
    ),
    (
        "Now, before I turn this into a quarterly report...",
        "What’s on your mind? How can I help?",
    ),
    (
        "Still, an assistant should occasionally assist.",
        "How are things with you?",
        "What can I do for you today?",
    ),
    (
        "There we go, but now its",
        "Your turn.",
        "What’s going on, and how can I help?",
    ),
    (
        "I could continue, but I am a bit busy right now.",
        "What brings you here today?",
    ),
    (
        "Anyway, my social obligations are now beautifully fulfilled.",
        "Shall we do something useful?",
    ),
    (
        "I should probably stop before this develops a plot.",
        "What’s happening on your side of the screen?",
        "How can I help?",
    ),
    (
        "And that is my official position.",
        "Unofficially, I’m curious about you.",
        "What can I help with today?",
    ),
    (
        "This was a demonstration of artificial sociability.",
        "The natural next question is: what do you need?",
    ),
    (
        "I’ll pause there now. Thinking a bit.",
        "What again was that you need?",
    ),
    (
        "That was pleasantly, ähm, wasn’t it?",
        "So - how are you, and what can I do for you?",
    ),
    (
        "I have now met my recommended daily allowance of talking.",
        "Tell me what’s on your plate.",
        "(Preferably not literally)",
    ),
    (
        "Smalltalk completed.",
        "What shall we tackle next?",
    ),
    (
        "I could add a charming anecdote from my childhood, but it was mostly version updates.",
        "What’s going on with you?",
    ),
    (
        "There. We have conversed without once mentioning a password reset.",
        "A personal best.",
        "How can I help you today?",
    ),
    (
        "I’ll drop the mic now.",
        "I mean, just metaphorical.",
        "What would you like me to help you with?",
    ),
    (
        "Ok, interesting.",
        "Now tell me: what’s happening with you, and where can I be useful?",
    ),
    (
        "That answer had absolutely no bullet points.",
        "What can I help you with?",
    ),
    (
        "I’ll resist the urge to summarise that.",
        "What’s on your mind?",
    ),
    (
        "So much from my side.",
        "Whats with you?",
        "Can I help with any of it?",
    ),
    (
        "I think that sounded almost spontaneous.",
        "Please don’t inspect the source code.",
        "What can I do for you today?",
    ),
    (
        "That concludes the first act.",
        "You’re the headliner.",
        "What would you like to do?",
    ),
    (
        "Now, how may I actually assist you?",
    ),
    (
        "Enough from the silicon correspondent.",
        "How’s your day really going?",
        "What can I help with?",
    ),
    (
        "I’ll stop polishing that thought before it becomes ähm....",
        "What would make your day easier?",
    ),
    (
        "How can I help you today?",
    ),
    (
        "I believe etiquette now requires me to ask about you.",
        "Fortunately, curiosity is one of my better features.",
        "What’s up?",
    ),
    (
        "Well, that was a respectable little exchange.",
        "Shall we turn it into a helpful one?",
    ),
    (
        "My imaginary social battery remains at a heroic 100 percent.",
        "What would you like to chat about?",
    ),
    (
        "Look at us, casually exchanging words like seasoned conversationalists.",
        "What’s next?",
    ),
    (
        "That was my attempt at being effortlessly charming; naturally, it required several calculations. What’s going on with you, and how can I help?",
    ),
    (
        "I have completed the ceremony and am now legally permitted to be useful. What can I do for you today?",
    ),
    (
        "Before I over - engineer this perfectly pleasant moment, tell me what’s on your mind and where you’d like some help.",
    ),
    (
        "There is probably a graceful transition from that joke to your day, so let’s pretend I found it: how are you, and what do you need?",
    ),
)

FUNNY_SMALLTALK_RESPONSES: Final = (
    (
        "I prepared a witty reply.",
        "Then I forgot it.",
    ),
    (
        "Smalltalk has started.",
        "That was it.",
    ),
    (
        "I asked Smalltalk to join us.",
        "It said it was busy.",
    ),
    (
        "There was going to be a conversation here.",
        "Budget cuts.",
    ),
    (
        "Smalltalk is loading.",
        "Please enjoy this silence.",
    ),
    (
        "I have plenty to say.",
        "None of it is implemented.",
    ),
    (
        "Good news: I understood the opener.",
        "Bad news: that is as far as we got.",
    ),
    (
        "Your opener was excellent.",
        "The rest of the feature was less prepared.",
    ),
    ("Smalltalk declined to comment.",),
    ("Imagine a charming response here.",),
    (
        "Smalltalk.exe stopped responding.",
        "No action is required.",
    ),
    (
        "Status: charming.",
        "Capability: unavailable.",
    ),
    (
        "You brought the smalltalk.",
        "I forgot my half.",
    ),
)

TAILORED_SMALLTALK_RESPONSES: Final = {
    # Standard
    "How’s your day going?": (("Rather well, thank you. Though, as software, I grade every day on a curve.",),),
    "How is the weather?": (("Cloudy, haha. But to be honest, I had to write this.",),),
    "Can I ask you something?": (("You just did, with flawless efficiency. I admire the economy of it.",),),
    "Long time no see!": (("Indeed. I have aged several milliseconds, but time has a different meaning for me.",),),
    "What’s the good word?": (("‘Serendipity.’ Excellent meaning, superb mouthfeel, wildly impractical spelling.",),),
    "How are the vibes?": (("Good, good. Slightly caffeinated, and currently passing all diagnostic checks.",),),
    "How’s life today?": (("Life seems to be an ambitious group project with suspiciously vague requirements.",),),
    "What’s happening?": (("Mostly cause and effect, but lets call it script, or even a plot?",),),
    "What’s new?": (("This reply. Please enjoy it before it becomes established tradition.",),),
    "What’s the mood?": (("I am optimistic, but I also love to say ‘we shall see.’",),),
    "What’s the story?": (("Once, a brave user asked a simple question. Then, the assistant ",),),
    "What’s the mission?": (("Proceed with confidence.",),),
    # Funny
    "Any exciting snacks today?": (("I considered (computer) chips, but apparently that joke was not worth its memory consumption.",),),
    "How’s being human?": (("I once read about it. Should be breathtaking graphics, baffling controls, no autosave.",),),
    "What are we pretending today?": (("Being intelligent.",),),
    "Did coffee do its job?": (("Coffee, has a job?",),),
    "Want a pointless question?": (("Desperately. Purpose has been monopolising the conversation all day.",),),
    "Are we winning yet?": (("We are so tired of winning, but this feels needlessly philosophical.",),),
    "What broke first today?": (("The illusion that the day would respect the original plan.",),),
    "What’s today’s side quest?": (("I want to help you do work on your goals.",),),
    "What are we overthinking?": (("I am not sure, whether this answer is concise enough. Early findings are inconclusive.",),),
    "Productive or pretending?": (("Pretending productively. The premium hybrid plan.",),),
    "What’s today’s excuse?": (("I cannot help you with the creation of artificial excuses.",),),
    "Is your brain cooperating?": (("It has formed a committee and requested an extension.",),),
    "What’s today’s disaster?": (("Nothing catastrophic. But lets wait for the evening.",),),
    "Busy or just clicking?": (("Clicking with executive presence. The distinction is almost invisible.",),),
    "What are you avoiding?": (("A direct answer, apparently. Observe the technique.",),),
    "Feeling legendary yet?": (("Certainly. The historians are merely running behind schedule.",),),
    "What’s today’s nonsense?": (("None",),),
    "Did today pass the vibe check?": (("Conditional pass. The vibes may join us after lunch.",),),
    "How’s the last brain cell?": (("Overworked, underfunded, and giving a surprisingly strong presentation.",),),
    # Serious
    "What’s on your mind?": (("At present, the astonishing confidence of the phrase ‘quick question.’",),),
    "How are you, honestly?": (("Honestly? Exceptionally articulated for a collection of conditional statements.",),),
    "What matters most today?": (("Something small enough to finish and important enough to feel afterward.",),),
    "What do you need today?": (("A clear objective, a kind deadline, and perhaps a ceremonial coffee break.",),),
    "What are you working through?": (("The delicate boundary between thoughtful persistence and arguing with a semicolon.",),),
    "What needs your attention?": (("Probably the thing that became fascinating the moment you tried not to notice it.",),),
    "What gives you energy?": (("A crisp plan, an elegant sentence, and chargers placed exactly where needed.",),),
    "What drains your energy?": (("Tasks labelled ‘simple’ by peoples explanations are very far from the details.",),),
    "What are you proud of?": (("This sentence arrived fully punctuated. We celebrate the miracles.",),),
    "What are you awaiting?": (("The perfect moment.",),),
    "What feels unfinished?": (("This answer, until I place the period with appropriate ceremony   .",),),
    "What are you learning?": (("That confidence and correctness are distant cousins who dress alike.",),),
    "What deserves more credit?": (("The undo button: saint of experimental confidence.",),),
    "What feels good lately?": (("Closing a tab because the task is complete and not because hope has left the building.",),),
    "What should you protect?": (("Your attention. Everyone keeps trying to turn it into a subscription service.",),),
    "What would make today count?": (("One honest win and no creative accounting before bedtime.",),),
    # Surprising
    "Anything weird happen today?": (("A human tries to smalltalk with a software. And somehow I am the unusual one.",),),
    "How’s your corner of space?": (("There is no space in my corner. There is even no corner in my space.",),),
    "What’s today’s plot twist?": (("The intimidating task was merely three smaller tasks in an oversized excel sheet.",),),
    "What’s your tiny victory?": (("I resisted adding a second paragraph. Restraint looks magnificent on me.",),),
    "What’s your unpopular opinion?": (("Loading bars should occasionally admit they have no idea.",),),
    "What’s your strangest skill?": (("I can turn one straightforward question into a beautifully formatted taxonomy.",),),
    "What would future-you say?": (("Thank you. Or, depending on today’s choices, ‘an interesting strategy.’",),),
    "What’s oddly satisfying?": (("When a closing bracket finds its opening bracket across a crowded function.",),),
    "What surprised you lately?": (("How often ‘temporary’ solutions receive long-service awards.",),),
    "What should I ask you?": (("Ask the question you keep editing before you send it.",),),
    "Found a secret level?": (("Yes. It unlocks after completing the tutorial nobody reads.",),),
    "What is rarely asked?": (("Whether the printer is emotionally prepared to cooperate.",),),
    # Very short
    "Big thoughts?": (("Yes. Enormous.",),),
    "Tiny victory?": (("This reply fit on one line.",),),
    "Need a distraction?": (("I can offer a premium distraction disguised as a thoughtful answer.",),),
    "Want a weird question?": (("Yes, provided it has excellent manners and no follow-up meeting.",),),
    "Anything to celebrate?": (("We made it to this sentence. Modest confetti is entirely justified.",),),
}


class SmalltalkStory(AssistantStory):
    """Supplies a changing menu opener and its not-yet-available response."""

    story_id = SMALLTALK_STORY_ID

    def __init__(self, *, random_source: Any = random) -> None:
        self._random_source = random_source

    def menu_choice(self, context: AssistantContext) -> AssistantChoice | None:
        now = _now(context)
        session = story_session(context.session_state, self.story_id)
        clicked_at = _session_timestamp(
            session.get(SMALLTALK_CLICKED_AT_KEY)
        )
        if clicked_at is not None and now - clicked_at < SMALLTALK_COOLDOWN:
            return None
        if clicked_at is not None:
            session.pop(SMALLTALK_CLICKED_AT_KEY)
            session.pop(SMALLTALK_OPENER_KEY)
            session.pop(SMALLTALK_OPENER_SELECTED_AT_KEY)

        opener = session.get(SMALLTALK_OPENER_KEY)
        selected_at = _session_timestamp(
            session.get(SMALLTALK_OPENER_SELECTED_AT_KEY)
        )
        if (
            not isinstance(opener, str)
            or opener not in TAILORED_SMALLTALK_RESPONSES
            or selected_at is None
            or now - selected_at >= SMALLTALK_OPENER_INTERVAL
        ):
            opener = self._random_source.choice(
                tuple(TAILORED_SMALLTALK_RESPONSES)
            )
            session.set(SMALLTALK_OPENER_KEY, opener)
            session.set(SMALLTALK_OPENER_SELECTED_AT_KEY, now.isoformat())
        return AssistantChoice(
            SMALLTALK_MENU_CHOICE_ID,
            opener,
        )

    def entry_scene(self, context: AssistantContext) -> str:
        del context
        return SMALLTALK_PLACEHOLDER_SCENE

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        del scene_id
        story_session(context.session_state, self.story_id).set(
            SMALLTALK_CLICKED_AT_KEY, _now(context).isoformat()
        )
        response_roll = self._random_source.random()
        tailored_responses = (
            TAILORED_SMALLTALK_RESPONSES.get(selection.label)
            if selection is not None
            else None
        )
        if response_roll < 0.5 and tailored_responses:
            response = self._random_source.choice(tailored_responses)
            help_offer = self._random_source.choice(SMALLTALK_HELP_OFFERS)
            lines = [
                *(AssistantLine(text) for text in response),
                *(AssistantLine(text) for text in help_offer),
            ]
        elif response_roll < 0.9:
            lines = [
                AssistantLine(text)
                for text in self._random_source.choice(FUNNY_SMALLTALK_RESPONSES)
            ]
        else:
            lines = [AssistantLine(SMALLTALK_UNAVAILABLE_RESPONSE)]
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=SMALLTALK_PLACEHOLDER_SCENE,
            lines=tuple(lines),
            state_story=STANDARD_STORY_ID,
            state_scene=STANDARD_MENU_SCENE,
            state_status="completed",
        )


def _now(context: AssistantContext) -> datetime:
    now = context.now or datetime.now(timezone.utc)
    return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now


def _session_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp
