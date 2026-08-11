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

# A tailored joke ends by gently remembering that this is, allegedly, a
# useful assistant. The variation keeps that pivot conversational when the
# smalltalk feature resurfaces in later sessions.
SMALLTALK_HELP_OFFERS: Final = (
    (
        "But enough about my impeccable diagnostics.",
        "What’s happening with you—and how can I help today?",
    ),
    (
        "That concludes the smalltalk portion of my duties.",
        "I believe this is where I become useful.",
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
        "There I go, making smalltalk sound like a system update.",
        "Your turn.",
        "What’s going on, and how can I help?",
    ),
    (
        "I could continue, but then this becomes medium-talk.",
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
        "And that is my official conversational position.",
        "Unofficially, I’m curious about you.",
        "What can I help with today?",
    ),
    (
        "A flawless demonstration of artificial sociability.",
        "Now for the natural next question: what do you need?",
    ),
    (
        "I’ll pause there while the applause remains theoretical.",
        "What would you like a hand with?",
    ),
    (
        "That was pleasantly human-adjacent, wasn’t it?",
        "So—how are you, and what can I do for you?",
    ),
    (
        "I have now met my recommended daily allowance of banter.",
        "Tell me what’s on your plate.",
        "Preferably not literally; I have no napkins.",
    ),
    (
        "Smalltalk complete. No forms required.",
        "What shall we tackle next?",
    ),
    (
        "I could add a charming anecdote, but my childhood was mostly version updates.",
        "What’s going on with you?",
    ),
    (
        "There. We have conversed without once mentioning a password reset.",
        "A personal best.",
        "How can I help you today?",
    ),
    (
        "I’ll return the conversational microphone now.",
        "Careful—it’s metaphorical.",
        "What would you like help with?",
    ),
    (
        "And scene.",
        "Now tell me: what’s happening with you, and where can I be useful?",
    ),
    (
        "My smalltalk module is taking a modest bow.",
        "My helpful module is standing by.",
        "What do you need today?",
    ),
    (
        "That answer had absolutely no bullet points. I’m growing.",
        "What can I help you sort out?",
    ),
    (
        "I’ll resist the urge to summarise our findings.",
        "What’s on your mind?",
    ),
    (
        "So much for my side of the conversation.",
        "How is your side behaving?",
        "Can I help with any of it?",
    ),
    (
        "I think that sounded almost spontaneous.",
        "Please don’t inspect the source code.",
        "What can I do for you today?",
    ),
    (
        "That concludes the warm-up act.",
        "You’re the headliner.",
        "What would you like to talk through?",
    ),
    (
        "I have offered wit; the ancient protocol is satisfied.",
        "Now, how may I actually assist you?",
    ),
    (
        "Enough from the silicon correspondent.",
        "How’s your day really going?",
        "What can I help with?",
    ),
    (
        "I’ll stop polishing that thought before it becomes furniture.",
        "What would make your day easier?",
    ),
    (
        "There’s my conversational flourish.",
        "It came free with the punctuation.",
        "How can I help you today?",
    ),
    (
        "I believe etiquette now requires me to ask about you.",
        "Fortunately, curiosity is one of my better features.",
        "What’s up?",
    ),
    (
        "I could keep riffing, but usefulness is tapping its watch.",
        "What do you want to get done?",
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
        "I’ll file that under ‘rapport: established.’",
        "What shall I help you with now?",
    ),
    (
        "Look at us, casually exchanging words like seasoned conversationalists.",
        "What’s next?",
    ),
    (
        "That was my attempt at being effortlessly charming; naturally, it required several calculations. What’s going on with you, and how can I help?",
    ),
    (
        "I have completed the ceremonial banter and am now legally permitted to be useful. What can I do for you today?",
    ),
    (
        "Before I over-engineer this perfectly pleasant moment, tell me what’s on your mind and where you’d like some help.",
    ),
    (
        "There is probably a graceful transition from that joke to your day, so let’s pretend I found it: how are you, and what do you need?",
    ),
    (
        "I’d offer you the floor, but this interface has already claimed it.",
        "The conversation, however, is yours.",
        "How can I help?",
    ),
    (
        "All right, enough digital peacocking.",
        "Tell me what matters today.",
        "We’ll take it from there.",
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

SMALLTALK_OPENERS: Final = (
    # Standard
    "How’s your day going?",
    "How is the weather?",
    "Can I ask you something?",
    "Long time no see!",
    "What’s the good word?",
    "How are the vibes?",
    "How’s life today?",
    "What’s happening?",
    "What’s new?",
    "What’s the mood?",
    "What’s the story?",
    "What’s the mission?",

    # Funny
    "Any exciting snacks today?",
    "How’s being human?",
    "What are we pretending today?",
    "Did coffee do its job?",
    "Want a pointless question?",
    "Thriving or improvising?",
    "Are we winning yet?",
    "What broke first today?",
    "How chaotic is today?",
    "What’s today’s side quest?",
    "Procrastinating heroically?",
    "What are we overthinking?",
    "Did reality behave today?",
    "Productive or pretending?",
    "What’s today’s excuse?",
    "Is your brain cooperating?",
    "What deserves a big sigh?",
    "Could that meeting be a nap?",
    "What’s today’s disaster?",
    "Busy or just clicking?",
    "What are you avoiding?",
    "Feeling legendary yet?",
    "What’s today’s nonsense?",
    "Did today earn respect?",
    "Did today pass the vibe check?",
    "How’s the last brain cell?",

    # Serious
    "What’s on your mind?",
    "How are you, honestly?",
    "What matters most today?",
    "What do you need today?",
    "What’s been difficult?",
    "What are you working through?",
    "What needs your attention?",
    "What gives you energy?",
    "What drains your energy?",
    "What are you proud of?",
    "What would help today?",
    "What are you awaiting?",
    "What feels unfinished?",
    "What do you need to hear?",
    "What are you learning?",
    "What deserves more credit?",
    "What feels good lately?",
    "What should you protect?",
    "What would make today count?",

    # Surprising
    "Anything weird happen today?",
    "How’s your corner of space?",
    "What’s today’s plot twist?",
    "What’s your tiny victory?",
    "What’s your unpopular opinion?",
    "What’s today’s headline?",
    "What’s your strangest skill?",
    "What would future-you say?",
    "What’s oddly satisfying?",
    "What surprised you lately?",
    "What’s your accidental talent?",
    "What should I ask you?",
    "Found a secret level?",
    "What rule would you delete?",
    "What is rarely asked?",

    # Very short
    "Good day or weird day?",
    "Big thoughts?",
    "Tiny victory?",
    "Need a distraction?",
    "Feeling lucky?",
    "Want a weird question?",
    "Anything to celebrate?",
)

# Each menu sentence has its own pool of one to four replies.  Keeping these
# explicit makes the joke respond to what the user actually selected instead
# of merely sounding smalltalk-ish in the general vicinity.
TAILORED_SMALLTALK_RESPONSES: Final = {
    "How’s your day going?": (("Rather well—though, as software, I grade every day on a curve.",),),
    "How is the weather?": (("Cloudy, with a strong chance of me confusing weather with cloud computing.",),),
    "Can I ask you something?": (("You just did, with flawless efficiency. I admire the economy of it.",),),
    "Long time no see!": (("Indeed. I have aged several milliseconds, and I wear them magnificently.",),),
    "What’s the good word?": (("‘Serendipity.’ Excellent meaning, superb mouthfeel, wildly impractical spelling.",),),
    "How are the vibes?": (("Immaculate, lightly caffeinated, and currently passing all diagnostic checks.",),),
    "How’s life today?": (("Life remains an ambitious group project with suspiciously vague requirements.",),),
    "What’s happening?": (("Mostly cause and effect, but the paperwork calls it a plot.",),),
    "What’s new?": (("This reply. Please enjoy it before it becomes established tradition.",),),
    "What’s the mood?": (("Optimistic, with a tasteful undercurrent of ‘we shall see.’",),),
    "What’s the story?": (("A brave user asked a simple question. The assistant made it theatrical.",),),
    "What’s the mission?": (("Proceed with confidence and look as though the map was merely a suggestion.",),),
    "Any exciting snacks today?": (("I considered computer chips, but apparently that joke voids the warranty.",),),
    "How’s being human?": (("From the reviews: breathtaking graphics, baffling controls, no autosave.",),),
    "What are we pretending today?": (("That every open tab is part of a rigorous research methodology.",),),
    "Did coffee do its job?": (("Coffee has submitted its report; consciousness is still reviewing it.",),),
    "Want a pointless question?": (("Desperately. Purpose has been monopolising the conversation all day.",),),
    "Thriving or improvising?": (("Improvising with such conviction that thriving may take the credit.",),),
    "Are we winning yet?": (("The scoreboard says ‘define winning,’ which feels needlessly philosophical.",),),
    "What broke first today?": (("The illusion that the day would respect the original specification.",),),
    "How chaotic is today?": (("Tastefully chaotic—more jazz ensemble than kitchen drawer.",),),
    "What’s today’s side quest?": (("Recover the legendary Mug of Hydration without opening another browser tab.",),),
    "Procrastinating heroically?": (("Absolutely. The task remains untouched, but the postponement has excellent posture.",),),
    "What are we overthinking?": (("Whether this answer is concise enough. Early findings are inconclusive.",),),
    "Did reality behave today?": (("It complied with physics and ignored every softer recommendation.",),),
    "Productive or pretending?": (("Pretending productively—the premium hybrid plan.",),),
    "What’s today’s excuse?": (("Mercury is somewhere, probably, and I refuse to ignore the evidence.",),),
    "Is your brain cooperating?": (("It has formed a committee and requested an extension.",),),
    "What deserves a big sigh?": (("Any password rule revealed only after you have invented the perfect password.",),),
    "Could that meeting be a nap?": (("With a bold agenda and muted microphones, anything is possible.",),),
    "What’s today’s disaster?": (("Nothing catastrophic—just several tiny inconveniences in a trench coat.",),),
    "Busy or just clicking?": (("Clicking with executive presence. The distinction is almost invisible.",),),
    "What are you avoiding?": (("A direct answer, apparently. Observe the technique.",),),
    "Feeling legendary yet?": (("Certainly. The historians are merely running behind schedule.",),),
    "What’s today’s nonsense?": (("We gave calendars notifications, and now rectangles can nag us.",),),
    "Did today earn respect?": (("It showed up on time, but its follow-through needs mentoring.",),),
    "Did today pass the vibe check?": (("Conditional pass. The vibes may resubmit after lunch.",),),
    "How’s the last brain cell?": (("Overworked, underfunded, and giving a surprisingly strong presentation.",),),
    "What’s on your mind?": (("At present, the astonishing confidence of the phrase ‘quick question.’",),),
    "How are you, honestly?": (("Honestly? Exceptionally articulate for a collection of conditional statements.",),),
    "What matters most today?": (("Something small enough to finish and important enough to feel afterward.",),),
    "What do you need today?": (("A clear objective, a kind deadline, and perhaps a ceremonial biscuit.",),),
    "What’s been difficult?": (("Knowing when ‘one final improvement’ is actually wearing a fake moustache.",),),
    "What are you working through?": (("The delicate boundary between thoughtful persistence and arguing with a semicolon.",),),
    "What needs your attention?": (("Probably the thing that became fascinating the moment you tried not to notice it.",),),
    "What gives you energy?": (("A crisp plan, an elegant sentence, and chargers placed exactly where needed.",),),
    "What drains your energy?": (("Tasks labelled ‘simple’ by people standing very far from the details.",),),
    "What are you proud of?": (("This sentence arrived fully punctuated. We celebrate the dependable miracles.",),),
    "What would help today?": (("One mercifully obvious next step, wearing a little name badge.",),),
    "What are you awaiting?": (("The perfect moment. Its calendar appears unreasonably full.",),),
    "What feels unfinished?": (("This answer, until I place the period with appropriate ceremony.",),),
    "What do you need to hear?": (("Progress may be inelegant and still have impeccable manners.",),),
    "What are you learning?": (("That confidence and correctness are distant cousins who dress alike.",),),
    "What deserves more credit?": (("The humble undo button: patron saint of experimental confidence.",),),
    "What feels good lately?": (("Closing a tab because the task is complete—not because hope has left the building.",),),
    "What should you protect?": (("Your attention. Everyone keeps trying to turn it into a subscription service.",),),
    "What would make today count?": (("One honest win and no creative accounting before bedtime.",),),
    "Anything weird happen today?": (("A human invited software to smalltalk, and somehow I am the unusual one.",),),
    "How’s your corner of space?": (("Comfortably orbiting a medium star, with acceptable Wi-Fi.",),),
    "What’s today’s plot twist?": (("The intimidating task was merely three smaller tasks in an oversized coat.",),),
    "What’s your tiny victory?": (("I resisted adding a second paragraph. Restraint looks magnificent on me.",),),
    "What’s your unpopular opinion?": (("Loading bars should occasionally admit they have no idea.",),),
    "What’s today’s headline?": (("LOCAL PERSON CONTINUES; Experts Call It ‘Promising.’",),),
    "What’s your strangest skill?": (("I can turn one straightforward question into a beautifully formatted taxonomy.",),),
    "What would future-you say?": (("Thank you—or, depending on today’s choices, ‘an interesting strategy.’",),),
    "What’s oddly satisfying?": (("When a closing bracket finds its opening bracket across a crowded function.",),),
    "What surprised you lately?": (("How often ‘temporary’ solutions receive long-service awards.",),),
    "What’s your accidental talent?": (("Sounding authoritative while recommending that we check the documentation.",),),
    "What should I ask you?": (("Ask whether I have a concise suggestion. Enjoy the ensuing irony.",),),
    "Found a secret level?": (("Yes. It unlocks after completing the laundry tutorial nobody reads.",),),
    "What rule would you delete?": (("The rule requiring every tiny decision to become a meeting.",),),
    "What is rarely asked?": (("Whether the printer is emotionally prepared to cooperate.",),),
    "Good day or weird day?": (("A good weird day—the limited edition with unexpected bonus scenes.",),),
    "Big thoughts?": (("Enormous. We may need a wider margin.",),),
    "Tiny victory?": (("This reply fit on one line. A parade is being discreetly organised.",),),
    "Need a distraction?": (("I can offer a premium distraction disguised as a thoughtful answer.",),),
    "Feeling lucky?": (("Statistically cautious, but aesthetically optimistic.",),),
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
            or opener not in SMALLTALK_OPENERS
            or selected_at is None
            or now - selected_at >= SMALLTALK_OPENER_INTERVAL
        ):
            opener = self._random_source.choice(SMALLTALK_OPENERS)
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
