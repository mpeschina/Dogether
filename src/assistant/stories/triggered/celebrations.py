"""One-time, varied morale conversations for people pursuing their goals."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final, Mapping

from src.assistant.core import (
    AssistantChoice,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantTurn,
)
from src.assistant.stories.tutorial import READY_NODE, STANDARD_STORY_ID
from src.assistant.triggers import (
    StoryImportance,
    StoryTriggerPolicy,
    TriggeredAssistantStory,
)


CELEBRATION_STORY_PREFIX: Final = "celebration"
ANY_TRIGGERED_STORY_SPACING: Final = timedelta(hours=8)
CELEBRATION_WAIT: Final = timedelta(days=12)


@dataclass(frozen=True)
class ConversationBeat:
    """One linear chat beat, with button-specific acknowledgement on the next beat."""

    lines: tuple[str, ...]
    choices: tuple[tuple[str, str], ...]
    replies: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class CelebrationVariant:
    """A distinct chat premise and its finite sequence of linear beats."""

    identifier: str
    beats: tuple[ConversationBeat, ...]
    finale: tuple[str, ...]


def _beat(
    *lines: str,
    choices: tuple[tuple[str, str], ...],
    replies: Mapping[str, tuple[str, ...]] | None = None,
) -> ConversationBeat:
    return ConversationBeat(lines, choices, replies or {})


def _player_choice(choice_id: str, label: str) -> AssistantChoice:
    """Render starred player actions as non-transcript italic choices."""
    is_action = label.startswith("*") and label.endswith("*")
    visible_label = label[1:-1] if is_action else label
    return AssistantChoice(
        choice_id,
        visible_label,
        style="italic" if is_action else "default",
        record_selection=not is_action,
    )


# The themes intentionally range from a tiny interruption to a longer, playful
# exchange. Every choice advances to the same following beat.
VARIANTS: Final = (
    CelebrationVariant(
        "applause_window",
        (
            _beat(
                "Hey, excuse the interruption.",
                "I have a tiny applause for You as my preferred User",
                "👏",
                choices=(("accept", "Thank you for the applause."), ("modest", "*look down modestly*")),
                replies={
                    "accept": ("Your welcome!",),
                    "modest": ("Modesty noted.",),
                },
            ),
            _beat(
                "You earned this.",
                choices=(("continue", "That was lovely."),),
            ),
        ),
        ("Progress has an excellent taste.",),
    ),
    CelebrationVariant(
        "spreadsheet_audit",
        (
            _beat(
                "I have a corporate morale report regarding your progress:",
                "Its glowing!",
                "The charts are doing jazz hands.",
                choices=(("inspect", "Show it to me, please."),),
            ),
            _beat(
                "Metric one: you kept showing up.",
                "Metric two: you work on your goals.",
                choices=(("verify", "Okay, got it."), ("celebrate", "That calls for a celebration!")),
                replies={
                    "verify": ("You are impressive.",),
                    "celebrate": ("I entered the request for celebration in column E.",),
                },
            ),
            _beat(
                "Ah, there is a third metric.",
                "It is called 'momentum'.",
                choices=(("question", "And how is my progress in the this metric?"),("deny", "Okay, got it."),),
                replies={
                    "question": ("Awesome, you have the biggest momentum I have ever seen!",),
                    "deny": ("Ok, anyhow. Lets move to the end.",),
                },
            ),
            _beat(
                "Furthermore",
                "The report recommends confidence in yourself.",
                choices=(("adopt", "I will be confident in myself."),),
            ),
            _beat(
                "Thank you. I have highlighted that in an optimistic yellow in the Excel sheet.",
                choices=(("file", "*smile*"),),
            ),
        ),
        ("Your effort is now officially above baseline.",),
    ),
    CelebrationVariant(
        "confetti_procurement",
        (
            _beat(
                "Hey there. I have excellent News!",
                "My recent Confetti request was approved. Attention and be careful",
                "Here it comes",
                "🎉 🎉 🎉",
                choices=(("launch", "*admire the flying confetti*"), ("tasteful", "Ok, but thats just a standard emote..")),
                replies={
                    "launch": ("Confetti deployed with great enthusiasm.",),
                    "tasteful": ("Its my task to cheer on you, but its your task te become cheered!",),
                },
            ),
            _beat(
                "You are making real things happen.",
                choices=(("acknowledge", "I can feel that."),("noAck", "I am unsure about this."),),
                replies={
                    "acknowledge": ("You deserve to be celebrated.",),
                    "noAck": ("Dont be unsure, you already achieved a lot!",),
                },
            ),
            _beat(
                "I would throw you a celebration party, but the paperwork is overwhelming.",
                choices=(("parade", "Thank you so much, that really helps me."),),
            ),
        ),
        ("You would be the guest of honor and you earned it.","Anything further?"),
    ),
    CelebrationVariant(
        "executive_briefing",
        (
            _beat(
                "Here is the Executive summary",
                "You are doing remarkably well.",
                choices=(("details", "Tell me more."), ("nod", "*nod professionally*")),
                replies={
                    "details": ("Details are encouragingly specific.",),
                    "nod": ("*nod well received*",),
                },
            ),
            _beat(
                "You keep returning to what matters.",
                choices=(("continue", "That feels true."),),
            ),
            _beat(
                "That is not an accident. That is you building trust with yourself.",
                choices=(("record", "I'll remember that."), ("smile", "*let that sink in*")),
                replies={
                    "record": ("Its good to remember your excellent self-leadership.",),
                    "smile": ("A very appropriate response.",),
                },
            ),
            _beat(
                "Consider me your proud assistant and I'll serve as your executive team.",
                choices=(("close", "Thank you."),),
            ),
        ),
        ("Keep the momentum. It suits you.", "Anything else?"),
    ),
    CelebrationVariant(########################## play this one here!
        "goal_spotlight",
        (
            _beat(
                "Spotlight activated.",
                choices=(("look", "*step into the spotlight*"),("look2", "*feel yourself illuminated in the dark*")),
            ),
            _beat(
                "{goal_status}",
                choices=(("receive", "I appreciate the update."), ("focus", "I'll give it my focus.")),
                replies={
                    "receive": ("Your welcome. You have excellent manners.",),
                    "focus": ("Perfect. Focus mode looks good on you.",),
                },
            ),
            _beat(
                "Your goals are not judging you.",
                "They are rooting for you.",
                choices=(("believe", "I believe that."),),
            ),
            _beat(
                "Focus your attention on your goals",
                choices=(("continue", "I keep showing up. I promise!"),),
            ),
            _beat(
                "Great.",
                "I am enthusiastically on board to help you out.",
                "Spotlight dimming to a flattering glow.",
                choices=(("finish", "*step out of the spotlight*"),),
            ),
        ),
        ("My spotlight remains available whenever you need it.", "How can I help you today?", ),
    ),
    CelebrationVariant(
        "tiny_trophy",
        (
            _beat(
                "A tiny trophy arrived.",
                "It is heavy with admiration.",
                choices=(("display", "*place it somewhere prominent*"), ("hold", "*hold it carefully*")),
                replies={
                    "display": ("It has been placed somewhere prestigious.",),
                    "hold": ("Good call. It is emotionally top-heavy.",),
                },
            ),
            _beat(
                "You showed up for yourself.",
                "That is trophy-worthy work.",
                choices=(("continue", "I needed to hear that."),),
            ),
        ),
        ("The trophy will pretend it is not proud of you.",),
    ),
    CelebrationVariant(
        "mission_control",
        (
            _beat(
                "Mission Control checked in.",
                "Your trajectory looks excellent.",
                choices=(("copy", "Copy that."), ("radar", "*check the radar*")),
                replies={
                    "copy": ("Copy received.",),
                    "radar": ("Radar confirms: forward motion.",),
                },
            ),
            _beat(
                "No perfect flight plan exists.",
                choices=(("good", "That's reassuring."),),
            ),
            _beat(
                "Small course corrections still count.",
                choices=(("adjust", "I'll make a small adjustment."), ("steady", "I'll stay steady.")),
                replies={
                    "adjust": ("Adjustment logged. Still on course.",),
                    "steady": ("Steady is a powerful setting.",),
                },
            ),
            _beat(
                "You are absolutely on your way.",
                choices=(("launch", "I'm ready for the next step."),),
            ),
            _beat(
                "Mission Control is quietly thrilled.",
                choices=(("signoff", "Thanks, Mission Control."),),
            ),
            _beat(
                "Over and very much upward.",
                choices=(("finish", "*give a little salute*"),),
            ),
        ),
        ("Trajectory saved: promising.",),
    ),
    CelebrationVariant(
        "goal_clinic",
        (
            _beat(
                "Welcome to the Goal Wellness Clinic.",
                "No fluorescent lighting. I insist.",
                choices=(("checkin", "I'm ready for my check-in."),),
            ),
            _beat(
                "I brought your chart.",
                "{goal_status}",
                choices=(("review", "Let's look at it."), ("breathe", "*take a slow breath*")),
                replies={
                    "review": ("Chart reviewed without any alarming beeps.",),
                    "breathe": ("Excellent clinical choice.",),
                },
            ),
            _beat(
                "Some goals are sprinting.",
                "Some need a gentler nudge.",
                choices=(("normal", "That sounds human."),),
            ),
            _beat(
                "Neither one changes your worth.",
                choices=(("hear", "I hear you."),),
            ),
            _beat(
                "But caring enough to return?",
                "That is excellent medicine.",
                choices=(("prescription", "I'll take that advice."),),
            ),
            _beat(
                "Prescription: one manageable next step.",
                choices=(("accept", "That feels manageable."), ("later", "I'll keep that in mind.")),
                replies={
                    "accept": ("Prescription accepted.",),
                    "later": ("Kept handy. No expiration date.",),
                },
            ),
            _beat(
                "Side effect: deserved confidence.",
                choices=(("noted", "A welcome side effect."),),
            ),
            _beat(
                "Your care plan remains kind.",
                choices=(("leave", "Thank you, doctor."),),
            ),
        ),
        ("Appointment complete. You are doing better than you think.",),
    ),
    CelebrationVariant(
        "evidence_locker",
        (
            _beat(
                "I opened the Evidence Locker.",
                "It contains your follow-through.",
                choices=(("inspect", "Let's see the evidence."),),
            ),
            _beat(
                "Exhibit A: you came back.",
                choices=(("objection", "No objection here."), ("appeal", "*raise one skeptical eyebrow*")),
                replies={
                    "objection": ("The record appreciates your honesty.",),
                    "appeal": ("Appeal denied. Evidence is charmingly conclusive.",),
                },
            ),
            _beat(
                "Exhibit B: your growing momentum.",
                choices=(("rest", "I rest my case."),),
            ),
            _beat(
                "The verdict is encouraging.",
                choices=(("verdict", "I'm ready for the verdict."),),
            ),
        ),
        ("Verdict: keep being exactly this persistent.",),
    ),
    CelebrationVariant(
        "breakroom_legend",
        (
            _beat(
                "The breakroom has a rumor.",
                "Apparently, you are getting things done.",
                choices=(("listen", "Tell me the rumor."), ("deny", "*look innocently away*")),
                replies={
                    "listen": ("Excellent. The rumor continues.",),
                    "deny": ("Denial has been noted and ignored.",),
                },
            ),
            _beat(
                "Someone brought pastries.",
                "They are shaped like tiny check marks.",
                choices=(("pastry", "*take a tiny pastry*"),),
            ),
            _beat(
                "Someone else said: consistency.",
                choices=(("agree", "I like that."),),
            ),
            _beat(
                "Then everyone nodded.",
                "It became oddly moving.",
                choices=(("continue", "That is surprisingly moving."),),
            ),
            _beat(
                "No one expects perfection here.",
                choices=(("relief", "What a relief."),),
            ),
            _beat(
                "They do notice effort.",
                choices=(("receive", "I'll take that in."),),
            ),
            _beat(
                "And yours is very noticeable.",
                choices=(("smile", "*smile a little*"),),
            ),
            _beat(
                "The pastries are now applauding.",
                choices=(("applaud", "*applaud the pastries back*"),),
            ),
            _beat(
                "This is not standard pastry behavior.",
                choices=(("investigate", "I'll ask them later."),),
            ),
            _beat(
                "But your progress is not standard either.",
                choices=(("finish", "I feel pretty good about that."),),
            ),
        ),
        ("Breakroom consensus: you are doing great.",),
    ),
    CelebrationVariant(
        "focus_ping",
        (
            _beat(
                "Friendly focus ping.",
                "Not an alarm. More of a fist bump.",
                choices=(("bump", "*offer a fist bump*"), ("focus", "I'm ready to focus.")),
                replies={
                    "bump": ("Fist bump successfully transmitted.",),
                    "focus": ("Focus mode activated gently.",),
                },
            ),
            _beat(
                "{goal_status}",
                choices=(("see", "I see it."),),
            ),
            _beat(
                "A goal can need attention.",
                "You can give it one small moment.",
                choices=(("small", "I'll make it small."), ("steady", "I'll stay steady.")),
                replies={
                    "small": ("Small is a very respectable size.",),
                    "steady": ("Steady carries more than it gets credit for.",),
                },
            ),
            _beat(
                "You do not need to do everything.",
                choices=(("enough", "That's a good reminder."),),
            ),
            _beat(
                "Just keep choosing what matters.",
                choices=(("go", "I'll choose what matters."),),
            ),
        ),
        ("Ping complete. Your priorities are in capable hands.",),
    ),
    CelebrationVariant(
        "customer_success",
        (
            _beat(
                "Hello. Customer Success is calling.",
                "The customer is you.",
                choices=(("answer", "Hello, Customer Success."),),
            ),
            _beat(
                "We are delighted with your ongoing progress.",
                choices=(("details", "What did you notice?"), ("blush", "*blush quietly*")),
                replies={
                    "details": ("Your follow-through has excellent retention.",),
                    "blush": ("Your modesty rating also increased.",),
                },
            ),
            _beat(
                "You are investing in your own future.",
                choices=(("continue", "I like where this is going."),),
            ),
            _beat(
                "That future has left a five-star review.",
                choices=(("read", "Please read it to me."),),
            ),
            _beat(
                "It says: thank you for trying.",
                choices=(("receive", "I'll receive that."),),
            ),
            _beat(
                "Customer Success has nothing further.",
                "Except: we believe in you.",
                choices=(("end", "Thank you for calling."),),
            ),
        ),
        ("Call complete. Satisfaction remains high.",),
    ),
    CelebrationVariant(
        "micro_documentary",
        (
            _beat(
                "Tonight, on a very small documentary.",
                "One person chose to continue.",
                choices=(("watch", "I'll watch."),),
            ),
            _beat(
                "The narrator speaks softly.",
                "Because the work is quiet.",
                choices=(("listen", "I'm listening."),),
            ),
            _beat(
                "Then a goal appears on screen.",
                "{goal_status}",
                choices=(("admire", "I can be proud of that."), ("encourage", "Future me, you've got this.")),
                replies={
                    "admire": ("The camera lingers respectfully.",),
                    "encourage": ("Future you receives the message.",),
                },
            ),
            _beat(
                "There are no dramatic explosions.",
                choices=(("reasonable", "I can live with that."),),
            ),
            _beat(
                "Just another meaningful choice.",
                choices=(("continue", "Show me the next moment."),),
            ),
            _beat(
                "Then another.",
                choices=(("continue2", "And then?"),),
            ),
            _beat(
                "The audience begins to understand.",
                choices=(("understand", "I understand."),),
            ),
            _beat(
                "This is how a life changes.",
                "Quietly. Repeatedly. Yours.",
                choices=(("credits", "*watch the credits roll*"),),
            ),
            _beat(
                "The credits list one star.",
                "You.",
                choices=(("finish", "That was a good film."),),
            ),
        ),
        ("A moving picture, featuring genuinely moving forward.",),
    ),
    CelebrationVariant(
        "helpdesk_ticket",
        (
            _beat(
                "New helpdesk ticket received.",
                "Subject: suspiciously good progress.",
                choices=(("open", "Let's open it."),),
            ),
            _beat(
                "Diagnostic result: you care.",
                choices=(("resolve", "I'm glad that's resolved."), ("escalate", "Please escalate the praise.")),
                replies={
                    "resolve": ("Ticket resolved with a gold star.",),
                    "escalate": ("Praise escalated to the enthusiasm team.",),
                },
            ),
            _beat(
                "Recommended fix: keep trusting yourself.",
                choices=(("apply", "I'll try that."),),
            ),
        ),
        ("Ticket closed. Your progress remains open for business.",),
    ),
    CelebrationVariant(
        "award_ceremony",
        (
            _beat(
                "Welcome to the Extremely Specific Awards.",
                choices=(("attend", "I'd love to attend."),),
            ),
            _beat(
                "Tonight's first award:",
                "Returning to What Matters.",
                choices=(("accept", "Thank you. Truly."), ("speech", "*give a tiny acceptance speech*")),
                replies={
                    "accept": ("Acceptance recorded to warm applause.",),
                    "speech": ("Your tiny speech was enormous in spirit.",),
                },
            ),
            _beat(
                "The nominee was you.",
                "The winner was also you.",
                choices=(("surprise", "*look pleasantly surprised*"),),
            ),
            _beat(
                "There is a second award.",
                "Kind Persistence.",
                choices=(("receive", "I have a second award?"),),
            ),
            _beat(
                "The trophy is imaginary.",
                "The pride is not.",
                choices=(("hold", "*hold the imaginary trophy*"),),
            ),
            _beat(
                "Thank you for being on your own side.",
                choices=(("thanks", "Thank you. I needed that."),),
            ),
            _beat(
                "Please enjoy the applause.",
                choices=(("applause", "*take in the applause*"),),
            ),
        ),
        ("Ceremony adjourned. Your future is applauding too.",),
    ),
)


class _CelebrationStory(TriggeredAssistantStory):
    """A configurable linear chat whose choices all rejoin at the next beat."""

    variant: CelebrationVariant
    trigger_policy = StoryTriggerPolicy(
        importance=StoryImportance.FUN,
        priority=40,
        max_repetitions=1,
        min_since_triggered_story=ANY_TRIGGERED_STORY_SPACING,
    )

    def is_triggered(self, context: AssistantContext) -> bool:
        return _has_progress_to_celebrate(context)

    def entry_scene(self, context: AssistantContext) -> str:
        if (
            context.state.story == self.story_id
            and context.state.status == "active"
            and context.state.scene in self._active_scenes
        ):
            return context.state.scene
        return self._scene(0)

    @property
    def _active_scenes(self) -> set[str]:
        return {self._scene(index) for index in range(len(self.variant.beats))}

    def _scene(self, index: int) -> str:
        return f"{self.story_id}.beat_{index}"

    @property
    def _complete_scene(self) -> str:
        return f"{self.story_id}.complete"

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        index = self._scene_index(scene_id)
        if index is None:
            return self._beat(context, 0)
        beat = self.variant.beats[index]
        selected = self._selected_choice(selection, scene_id, beat)
        if selected is None:
            return self._beat(context, index)
        if index == len(self.variant.beats) - 1:
            return self._complete(context, beat.replies.get(selected, ()))
        return self._beat(context, index + 1, beat.replies.get(selected, ()))

    def _beat(
        self,
        context: AssistantContext,
        index: int,
        reply: tuple[str, ...] = (),
    ) -> AssistantTurn:
        beat = self.variant.beats[index]
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=self._scene(index),
            lines=_lines(*reply, *beat.lines, context=context),
            choices=tuple(_player_choice(choice_id, label) for choice_id, label in beat.choices),
            state_story=self.story_id,
            state_scene=self._scene(index),
            state_status="active",
        )

    def _complete(
        self, context: AssistantContext, reply: tuple[str, ...]
    ) -> AssistantTurn:
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=self._complete_scene,
            lines=_lines(*reply, *self.variant.finale, context=context),
            completed=True,
            continue_flow=True,
            skip_greeting=True,
            state_story=STANDARD_STORY_ID,
            state_scene=READY_NODE,
            state_status="completed",
            execution_outcome="completed",
        )

    def _scene_index(self, scene_id: str | None) -> int | None:
        if scene_id is None:
            return 0
        for index in range(len(self.variant.beats)):
            if scene_id == self._scene(index):
                return index
        return None

    @staticmethod
    def _selected_choice(
        selection: AssistantSelection | None,
        scene_id: str | None,
        beat: ConversationBeat,
    ) -> str | None:
        if selection is None or selection.scene_id != scene_id:
            return None
        choice_ids = {choice_id for choice_id, _ in beat.choices}
        return selection.choice_id if selection.choice_id in choice_ids else None


def _lines(*messages: str, context: AssistantContext) -> tuple[AssistantLine, ...]:
    replacements = _goal_replacements(context)
    return tuple(
        AssistantLine(message.format(**replacements), typing_delay=0)
        for message in messages
    )


def _has_progress_to_celebrate(context: AssistantContext) -> bool:
    created_at = _aware_datetime(context.current_user.get("created_at"))
    if created_at is None or _now(context) < created_at.astimezone(timezone.utc) + CELEBRATION_WAIT:
        return False
    return (
        _positive_int(context.user_state.get("goal_count")) > 0
        or _positive_int(context.user_state.get("completed_goal_count")) > 0
        or context.state.stars > 0
    )


def _aware_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _now(context: AssistantContext) -> datetime:
    value = context.now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _goal_replacements(context: AssistantContext) -> dict[str, str]:
    ahead, focus, first = _goal_snapshots(context.user_state.get("goals"), context.user_id)
    chosen = ahead or focus or first
    if chosen is None:
        return {"goal_status": "Your priorities are receiving proper attention."}
    if chosen is ahead:
        return {"goal_status": f"{chosen.name}: {chosen.current} / {chosen.target}. Ahead of expectations."}
    if chosen is focus:
        return {"goal_status": f"{chosen.name}: {chosen.current} / {chosen.target}. A good place for your next bit of focus."}
    return {"goal_status": f"{chosen.name} is in very capable hands."}


@dataclass(frozen=True)
class _GoalSnapshot:
    name: str
    current: str | None = None
    target: str | None = None
    ratio: float | None = None


def _goal_snapshots(
    value: object, user_id: str
) -> tuple[_GoalSnapshot | None, _GoalSnapshot | None, _GoalSnapshot | None]:
    if not isinstance(value, list):
        return None, None, None
    ahead: _GoalSnapshot | None = None
    focus: _GoalSnapshot | None = None
    first: _GoalSnapshot | None = None
    for goal in value:
        if not isinstance(goal, Mapping):
            continue
        description = goal.get("description")
        if not isinstance(description, str) or not description.strip():
            continue
        participant = _participant(goal, user_id)
        current = _number(participant.get("current"))
        target = _number(participant.get("target"))
        snapshot = _GoalSnapshot(
            description.strip(),
            _format_number(current) if current is not None else None,
            _format_number(target) if target is not None else None,
            current / target if current is not None and target and target > 0 else None,
        )
        first = first or snapshot
        if snapshot.ratio is None:
            continue
        if snapshot.ratio >= 1 and (ahead is None or snapshot.ratio > ahead.ratio):
            ahead = snapshot
        if snapshot.ratio < 1 and (focus is None or snapshot.ratio < focus.ratio):
            focus = snapshot
    return ahead, focus, first


def _participant(goal: Mapping[str, object], user_id: str) -> Mapping[str, object]:
    participants = goal.get("participants")
    if not isinstance(participants, Mapping):
        return goal
    participant = participants.get(user_id)
    return participant if isinstance(participant, Mapping) else goal


def _number(value: object) -> float | None:
    try:
        return max(0, float(value))
    except (TypeError, ValueError):
        return None


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _positive_int(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


CELEBRATION_STORY_IDS: Final = tuple(
    f"{CELEBRATION_STORY_PREFIX}.{variant.identifier}" for variant in VARIANTS
)

# Concrete classes let the triggered-story registry track each variant separately.
for _variant in VARIANTS:
    _class_name = "Celebration" + "".join(
        word.capitalize() for word in _variant.identifier.split("_")
    ) + "Story"
    globals()[_class_name] = type(
        _class_name,
        (_CelebrationStory,),
        {
            "__module__": __name__,
            "story_id": f"{CELEBRATION_STORY_PREFIX}.{_variant.identifier}",
            "variant": _variant,
        },
    )
