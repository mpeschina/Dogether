"""Declarative onboarding and reusable tutorial scenes."""
from __future__ import annotations

from typing import Final

from src.assistant.core import (
    AssistantChoice,
    AssistantContext,
    AssistantLine,
    AssistantSelection,
    AssistantStory,
    AssistantTurn,
)


TUTORIAL_STORY_ID: Final = "tutorial"
STANDARD_STORY_ID: Final = "standard"

WELCOME_NODE: Final = "onboarding.welcome"
RESUME_NODE: Final = "onboarding.resume"
FRIENDS_NODE: Final = "friends.offer_invite"
FRIENDS_EXPLANATION_NODE: Final = "friends.explain.intro"
FRIENDS_EXPLANATION_OPTIONS_NODE: Final = "friends.explain.options"
FRIENDS_EXPLANATION_LINK_NODE: Final = "friends.explain.link"
FRIENDS_EXPLANATION_GOODBYE_NODE: Final = "friends.explain.goodbye"
GOALS_NODE: Final = "goals.offer_create"
GOALS_EXPLANATION_NODE: Final = "goals.explain.intro"
GOALS_EXPLANATION_HOW_NODE: Final = "goals.explain.how"
GOALS_EXPLANATION_PROGRESS_NODE: Final = "goals.explain.progress"
GOALS_EXPLANATION_FRIENDS_NODE: Final = "goals.explain.friends"
GOALS_EXPLANATION_REACTIONS_NODE: Final = "goals.explain.reactions"
GOALS_EXPLANATION_FINISH_NODE: Final = "goals.explain.finish"
PUSH_NODE: Final = "push.offer_enable"
PUSH_EXPLANATION_NODE: Final = "push.explain.intro"
PUSH_EXPLANATION_SHARED_NODE: Final = "push.explain.shared_goals"
PUSH_EXPLANATION_MOBILE_NODE: Final = "push.explain.mobile_installation"
PUSH_EXPLANATION_CONSENT_NODE: Final = "push.explain.os_consent"
PUSH_EXPLANATION_CONTROLS_NODE: Final = "push.explain.goal_controls"
PUSH_EXPLANATION_SETTINGS_NODE: Final = "push.explain.available_settings"
PUSH_EXPLANATION_FINISH_NODE: Final = "push.explain.finish"
ANALYSIS_COMPLETE_NODE: Final = "analysis.complete"
TOUR_NODE: Final = "tour"
READY_NODE: Final = "ready"

FRIENDS_EVENT_ID: Final = "friends_check"
GOALS_EVENT_ID: Final = "goals_check"
PUSH_EVENT_ID: Final = "push_check"


def _lines(*items: str | tuple[str, float]) -> tuple[AssistantLine, ...]:
    result: list[AssistantLine] = []
    for item in items:
        if isinstance(item, tuple):
            result.append(AssistantLine(item[0], typing_delay=item[1]))
        else:
            result.append(AssistantLine(item))
    return tuple(result)


def _choices(*labels: str) -> tuple[AssistantChoice, ...]:
    return tuple(AssistantChoice.from_label(label) for label in labels)


def _scene(
    owner: str,
    scene_id: str,
    *,
    lines: tuple[AssistantLine, ...] = (),
    choices: tuple[AssistantChoice, ...] = (),
    label: str = "",
    status: str = "paused",
    **changes,
) -> AssistantTurn:
    return AssistantTurn(
        story_id=owner,
        scene_id=scene_id,
        lines=lines,
        choices=choices,
        choice_label=label,
        state_story=owner,
        state_scene=scene_id,
        state_status=status,
        **changes,
    )


def _transition(
    owner: str,
    scene_id: str,
    *,
    status: str = "active",
    **changes,
) -> AssistantTurn:
    return AssistantTurn(
        story_id=owner,
        scene_id=scene_id,
        state_story=owner,
        state_scene=scene_id,
        state_status=status,
        continue_flow=True,
        **changes,
    )


def _complete(
    scene_id: str,
    *,
    owner: str = STANDARD_STORY_ID,
    status: str = "completed",
    **changes,
) -> AssistantTurn:
    return AssistantTurn(
        story_id=owner,
        scene_id=scene_id,
        state_story=STANDARD_STORY_ID,
        state_scene=READY_NODE,
        state_status=status,
        completed=True,
        **changes,
    )


def _selected(selection: AssistantSelection | None) -> str | None:
    return selection.choice_id if selection is not None else None


class InitialTutorialStory(AssistantStory):
    """One explicit transition per onboarding scene."""

    story_id = TUTORIAL_STORY_ID

    def entry_scene(self, context: AssistantContext) -> str:
        if (
            context.state.status == "paused"
            and context.state.story == self.story_id
            and context.previous_page_key != "help"
        ):
            return RESUME_NODE
        return context.state.scene or WELCOME_NODE

    def advance(
        self,
        context: AssistantContext,
        scene_id: str | None,
        selection: AssistantSelection | None,
    ) -> AssistantTurn | None:
        scene_id = scene_id or self.entry_scene(context)
        if scene_id == WELCOME_NODE:
            return self._welcome(selection)
        if scene_id == RESUME_NODE:
            return self._resume(context, selection)
        if scene_id == FRIENDS_NODE:
            return self._friends(context, selection)
        if scene_id in FRIEND_SCENES:
            return explanation_turn(context, self.story_id, scene_id, selection)
        if scene_id == GOALS_NODE:
            return self._goals(context, selection)
        if scene_id in GOAL_SCENES:
            return explanation_turn(context, self.story_id, scene_id, selection)
        if scene_id == PUSH_NODE:
            return self._push(context, selection)
        if scene_id in PUSH_SCENES:
            return explanation_turn(context, self.story_id, scene_id, selection)
        if scene_id == ANALYSIS_COMPLETE_NODE:
            return self._analysis_complete(selection)
        if scene_id == TOUR_NODE:
            return self._tour(selection)
        return _transition(self.story_id, WELCOME_NODE)

    def _welcome(self, selection: AssistantSelection | None) -> AssistantTurn:
        choice = _selected(selection)
        if choice is None:
            return _scene(
                self.story_id,
                WELCOME_NODE,
                lines=_lines(
                    "Hi, welcome!",
                    ("Great to have you here.", 1.2),
                    ("Want some help?", 1.5),
                ),
                choices=_choices("Analyse my profile", "Give me a tour", "I'm good"),
            )
        if choice == "Analyse my profile":
            return _transition(self.story_id, FRIENDS_NODE)
        if choice == "Give me a tour":
            return _transition(self.story_id, TOUR_NODE)
        return _complete(
            READY_NODE,
            status="declined",
            lines=_lines("Fair enough.", ("Have fun in there. 👋", 1.2)),
            assistant_leaves=True,
        )

    def _resume(
        self,
        context: AssistantContext,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        choice = _selected(selection)
        if choice is None:
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=RESUME_NODE,
                lines=_lines("Hey, you're back.", ("Continue where we stopped?", 1.2)),
                choices=_choices("Yes", "Start over"),
            )
        if choice == "Start over":
            return _transition(self.story_id, WELCOME_NODE)
        return _transition(
            self.story_id,
            context.state.scene or WELCOME_NODE,
            lines=_lines("Perfect."),
        )

    def _friends(
        self,
        context: AssistantContext,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        count = int(context.user_state.get("friend_count", 0))
        prior = context.state.events.get(FRIENDS_EVENT_ID, {})
        choice = _selected(selection)

        if count >= 2:
            return _transition(
                self.story_id,
                GOALS_NODE,
                lines=_lines("Friends look good. ✓"),
                event_updates={FRIENDS_EVENT_ID: {"outcome": "not_needed"}},
            )

        if count == 1 and prior.get("awaiting") == "invite":
            return _transition(
                self.story_id,
                GOALS_NODE,
                lines=_lines("Nice.", ("Company acquired. ✓", 1.2)),
                event_updates={FRIENDS_EVENT_ID: {"outcome": "completed"}},
            )

        if count == 1:
            if choice is None:
                return _scene(
                    self.story_id,
                    FRIENDS_NODE,
                    lines=_lines("You already found someone.", "Good start."),
                    label="Want another?",
                    choices=_choices("Invite someone", "I'm good"),
                )
            if choice == "Invite someone":
                return self._navigate_to_friends()
            return _transition(
                self.story_id,
                GOALS_NODE,
                event_updates={FRIENDS_EVENT_ID: {"outcome": "completed"}},
            )

        if choice is None:
            return _scene(
                self.story_id,
                FRIENDS_NODE,
                lines=_lines("First: your people.", ("It's quiet in here.", 1.2)),
                label="Invite someone?",
                choices=_choices("Invite a friend", "Explain the Friendlist to me", "Later"),
            )
        if choice == "Invite a friend":
            return self._navigate_to_friends()
        if choice == "Explain the Friendlist to me":
            return _transition(self.story_id, FRIENDS_EXPLANATION_NODE)
        return _transition(
            self.story_id,
            GOALS_NODE,
            event_updates={FRIENDS_EVENT_ID: {"outcome": "skipped"}},
        )

    def _navigate_to_friends(self) -> AssistantTurn:
        return AssistantTurn(
            story_id=self.story_id,
            scene_id=FRIENDS_NODE,
            destination="friends",
            event_updates={
                FRIENDS_EVENT_ID: {"outcome": "interrupted", "awaiting": "invite"}
            },
            state_story=self.story_id,
            state_scene=FRIENDS_NODE,
            state_status="paused",
        )

    def _goals(
        self,
        context: AssistantContext,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        count = int(context.user_state.get("goal_count", 0))
        prior = context.state.events.get(GOALS_EVENT_ID, {})
        choice = _selected(selection)
        if count == 0:
            if choice is None:
                return _scene(
                    self.story_id,
                    GOALS_NODE,
                    lines=_lines(
                        ("Next: goals.", 0),
                        ("You don't have one yet.", 0),
                        ("Let's make that useful.", 0),
                    ),
                    choices=_choices("Create a goal", "Explain Goals to me", "Later"),
                )
            if choice == "Create a goal":
                return AssistantTurn(
                    story_id=self.story_id,
                    scene_id=GOALS_NODE,
                    destination="manage_goals",
                    event_updates={
                        GOALS_EVENT_ID: {"outcome": "interrupted", "awaiting": "create"}
                    },
                    state_story=self.story_id,
                    state_scene=GOALS_NODE,
                    state_status="paused",
                )
            if choice == "Explain Goals to me":
                return _transition(self.story_id, GOALS_EXPLANATION_NODE)
            return _transition(
                self.story_id,
                PUSH_NODE,
                event_updates={GOALS_EVENT_ID: {"outcome": "skipped"}},
            )

        if prior.get("awaiting") == "create":
            lines = _lines(("There we go. ✓", 0))
            outcome = "completed"
        elif count == 1:
            lines = _lines(("You have one goal.", 0), ("Perfect place to start. ✓", 0))
            outcome = "not_needed"
        else:
            lines = _lines(("Goals are looking busy.", 0), ("I like it. ✓", 0))
            outcome = "not_needed"
        return _transition(
            self.story_id,
            PUSH_NODE,
            lines=lines,
            event_updates={GOALS_EVENT_ID: {"outcome": outcome}},
        )

    def _push(
        self,
        context: AssistantContext,
        selection: AssistantSelection | None,
    ) -> AssistantTurn:
        enabled = bool(context.user_state.get("push_enabled", False))
        prior = context.state.events.get(PUSH_EVENT_ID, {})
        choice = _selected(selection)
        if enabled:
            if prior.get("awaiting") == "enable":
                lines = _lines("Perfect. ✓", "I'll be gentle.")
                outcome = "completed"
            else:
                lines = _lines("Notifications are ready. ✓")
                outcome = "not_needed"
            return _transition(
                self.story_id,
                ANALYSIS_COMPLETE_NODE,
                lines=lines,
                event_updates={PUSH_EVENT_ID: {"outcome": outcome}},
            )

        if choice is None:
            return _scene(
                self.story_id,
                PUSH_NODE,
                lines=_lines(
                    "One last thing.",
                    ("I can nudge you.", 0),
                    ("But I need permission.", 0),
                ),
                choices=_choices(
                    "Enable notifications", "Explain notifications to me", "Not now"
                ),
            )
        if choice == "Enable notifications":
            return AssistantTurn(
                story_id=self.story_id,
                scene_id=PUSH_NODE,
                destination="push_notifications",
                event_updates={
                    PUSH_EVENT_ID: {"outcome": "interrupted", "awaiting": "enable"}
                },
                state_story=self.story_id,
                state_scene=PUSH_NODE,
                state_status="paused",
            )
        if choice == "Explain notifications to me":
            return _transition(self.story_id, PUSH_EXPLANATION_NODE)
        return _transition(
            self.story_id,
            ANALYSIS_COMPLETE_NODE,
            event_updates={PUSH_EVENT_ID: {"outcome": "skipped"}},
        )

    def _analysis_complete(
        self, selection: AssistantSelection | None
    ) -> AssistantTurn:
        if selection is None:
            return _scene(
                self.story_id,
                ANALYSIS_COMPLETE_NODE,
                lines=_lines(
                    "That's it.",
                    ("You're ready. ✓", 0),
                    ("I'll get out of your way.", 0),
                ),
                choices=_choices("Thanks!"),
            )
        return _complete(
            READY_NODE,
            assistant_leaves=True,
        )

    def _tour(self, selection: AssistantSelection | None) -> AssistantTurn:
        if selection is None:
            return _scene(
                self.story_id,
                TOUR_NODE,
                lines=_lines(
                    "Sure.",
                    ("Dogether is simple.", 0),
                    ("Pick something worth doing.", 0),
                    ("Bring someone along and Keep each other moving.", 0),
                    ("That's basically it.", 0),
                    ("You'll figure out the rest.", 0),
                ),
                choices=_choices("Got it"),
            )
        return _complete(
            READY_NODE,
            lines=_lines("Enjoy. 👋"),
            assistant_leaves=True,
        )


FRIEND_SCENES = {
    FRIENDS_EXPLANATION_NODE,
    FRIENDS_EXPLANATION_OPTIONS_NODE,
    FRIENDS_EXPLANATION_LINK_NODE,
    FRIENDS_EXPLANATION_GOODBYE_NODE,
}
GOAL_SCENES = {
    GOALS_EXPLANATION_NODE,
    GOALS_EXPLANATION_HOW_NODE,
    GOALS_EXPLANATION_PROGRESS_NODE,
    GOALS_EXPLANATION_FRIENDS_NODE,
    GOALS_EXPLANATION_REACTIONS_NODE,
    GOALS_EXPLANATION_FINISH_NODE,
}
PUSH_SCENES = {
    PUSH_EXPLANATION_NODE,
    PUSH_EXPLANATION_SHARED_NODE,
    PUSH_EXPLANATION_MOBILE_NODE,
    PUSH_EXPLANATION_CONSENT_NODE,
    PUSH_EXPLANATION_CONTROLS_NODE,
    PUSH_EXPLANATION_SETTINGS_NODE,
    PUSH_EXPLANATION_FINISH_NODE,
}
EXPLANATION_SCENES = FRIEND_SCENES | GOAL_SCENES | PUSH_SCENES


def explanation_turn(
    context: AssistantContext,
    owner: str,
    scene_id: str,
    selection: AssistantSelection | None,
) -> AssistantTurn:
    """Render one reusable explanation scene for onboarding or the standard menu."""
    if scene_id in FRIEND_SCENES:
        return _friend_explanation(context, owner, scene_id, selection)
    if scene_id in GOAL_SCENES:
        return _goal_explanation(context, owner, scene_id, selection)
    return _push_explanation(context, owner, scene_id, selection)


def _finish_explanation(
    owner: str,
    *,
    lines: tuple[AssistantLine, ...] = (),
    destination: str | None = None,
    event_updates=None,
    assistant_leaves: bool = False,
) -> AssistantTurn:
    if owner == STANDARD_STORY_ID:
        return _complete(
            READY_NODE,
            lines=lines,
            destination=destination,
            event_updates=event_updates or {},
            assistant_leaves=assistant_leaves,
        )
    return AssistantTurn(
        story_id=owner,
        scene_id=READY_NODE,
        lines=lines,
        destination=destination,
        event_updates=event_updates or {},
        assistant_leaves=assistant_leaves,
        state_story=STANDARD_STORY_ID,
        state_scene=READY_NODE,
        state_status="completed",
        completed=True,
    )


def _friend_explanation(
    context: AssistantContext,
    owner: str,
    scene_id: str,
    selection: AssistantSelection | None,
) -> AssistantTurn:
    choice = _selected(selection)
    if scene_id == FRIENDS_EXPLANATION_NODE:
        if choice is None:
            return _scene(
                owner,
                scene_id,
                lines=_lines(
                    ("Sure, I'll explain it to you:", 0),
                    ("Friends unlock shared goals.", None),
                    ("You have the same goal with your friends and work on it together. Every day. You see each others progress and help to stay on track!", 0),
                ),
                choices=_choices("How do I add friends?", "Got it"),
            )
        return _transition(owner, FRIENDS_EXPLANATION_OPTIONS_NODE)

    if scene_id == FRIENDS_EXPLANATION_OPTIONS_NODE:
        if choice is None:
            return _scene(
                owner,
                scene_id,
                lines=_lines(
                    ("You have two options to add friends here:", 0),
                    ("1. Invite them by email using the Friends menu, or", 0),
                    ("2. Share your invite link.", 0),
                ),
                choices=_choices("How does the link work?", "Makes sense"),
            )
        return _transition(owner, FRIENDS_EXPLANATION_LINK_NODE)

    if scene_id == FRIENDS_EXPLANATION_LINK_NODE:
        if choice is None:
            return _scene(
                owner,
                scene_id,
                lines=_lines(
                    ("Your link belongs to you.", 0),
                    ("Someone opens it.", None),
                    ("You get a friend invite that you can accept or deny.", 0),
                    ("Only Friends can share goals.", 0),
                    ("And it is at the heart of the app..", None),
                    ("to work on a shared goal together with your friends.", 3),
                ),
                choices=_choices(
                    "Create a Link for me", "Show me the Friends Page", "Got it"
                ),
            )
        if choice == "Create a Link for me":
            if context.create_friend_share_link is None:
                return _scene(
                    owner,
                    scene_id,
                    statuses=("I couldn't create a link right now.",),
                    keep_statuses_in_history=True,
                    choices=_choices(
                        "Create a Link for me", "Show me the Friends Page", "Got it"
                    ),
                )
            return _transition(
                owner,
                FRIENDS_EXPLANATION_GOODBYE_NODE,
                lines=_lines(
                    (f"Here’s your invite link:\n\n{context.create_friend_share_link()}", 0)
                ),
            )
        if choice == "Show me the Friends Page":
            if owner == STANDARD_STORY_ID:
                return _finish_explanation(owner, destination="friends")
            return AssistantTurn(
                story_id=owner,
                scene_id=FRIENDS_NODE,
                destination="friends",
                state_story=owner,
                state_scene=FRIENDS_NODE,
                state_status="paused", 
            )
        return _transition(owner, FRIENDS_EXPLANATION_GOODBYE_NODE)

    if choice is None:
        return _scene(
            owner,
            FRIENDS_EXPLANATION_GOODBYE_NODE,
            choices=_choices("Ok, thank you"),
        )
    if owner == TUTORIAL_STORY_ID:
        return _transition(
            owner,
            GOALS_NODE,
            lines=_lines("Ok, no problem. Lets move on."),
            event_updates={FRIENDS_EVENT_ID: {"outcome": "skipped"}},
        )
    return _finish_explanation(owner, assistant_leaves=True)


def _goal_explanation(
    context: AssistantContext,
    owner: str,
    scene_id: str,
    selection: AssistantSelection | None,
) -> AssistantTurn:
    del context
    choice = _selected(selection)
    scenes = {
        GOALS_EXPLANATION_NODE: (
            _lines(
                "Sure.",
                ("Goals are the heart of Dogether.", 0),
                ("You work on them every day.", 0),
                ("And your friends help you stay on track.", 0),
            ),
            _choices("Ok, whats more?", "Got it"),
            GOALS_EXPLANATION_HOW_NODE,
        ),
        GOALS_EXPLANATION_HOW_NODE: (
            _lines(
                ("Every goal has participants.", 0),
                ("Anyone can invite friends.", 0),
                ("But you only see your friends.", 0),
                ("There may be others too.", 0),
            ),
            _choices("Makes sense", "What about progress?"),
            GOALS_EXPLANATION_PROGRESS_NODE,
        ),
        GOALS_EXPLANATION_PROGRESS_NODE: (
            _lines(
                ("Everyone tracks their own progress.", 0),
                ("And everyone can have their own maximum.", 0),
                ("So the goal stays personal.", 0),
            ),
            _choices("Nice", "What do friends do?"),
            GOALS_EXPLANATION_FRIENDS_NODE,
        ),
        GOALS_EXPLANATION_FRIENDS_NODE: (
            _lines(
                ("This is where it gets fun.", 0),
                ("When a friend completes the goal…", 0),
                ("You can get a notification.", 0),
            ),
            _choices("And then?"),
            GOALS_EXPLANATION_REACTIONS_NODE,
        ),
        GOALS_EXPLANATION_REACTIONS_NODE: (
            _lines(
                ("Send them a reaction!", 0),
                ("A little celebration.", 0),
                ("Or some friendly pressure.", 0),
            ),
            _choices("Got it"),
            GOALS_EXPLANATION_FINISH_NODE,
        ),
    }
    if scene_id in scenes:
        lines, choices, next_scene = scenes[scene_id]
        if choice is None:
            return _scene(owner, scene_id, lines=lines, choices=choices)
        return _transition(owner, next_scene)

    if choice is None:
        return _scene(
            owner,
            GOALS_EXPLANATION_FINISH_NODE,
            lines=_lines(("That’s basically goals.", 0)),
            choices=_choices("Create a goal", "Cool, thank you for the explanation."),
        )
    if choice == "Create a goal":
        if owner == STANDARD_STORY_ID:
            return _finish_explanation(owner, destination="manage_goals")
        return AssistantTurn(
            story_id=owner,
            scene_id=GOALS_NODE,
            destination="manage_goals",
            event_updates={
                GOALS_EVENT_ID: {"outcome": "interrupted", "awaiting": "create"}
            },
            state_story=owner,
            state_scene=GOALS_NODE,
            state_status="paused",
        )
    return _finish_explanation(
        owner,
        lines=_lines("Ciao."),
        assistant_leaves=True,
    )


def _push_explanation(
    context: AssistantContext,
    owner: str,
    scene_id: str,
    selection: AssistantSelection | None,
) -> AssistantTurn:
    del context
    choice = _selected(selection)
    scenes = {
        PUSH_EXPLANATION_NODE: (
            _lines(
                "Sure.",
                (
                    "Notifications are an integral part. They keep shared goals moving.",
                    0,
                ),
            ),
            _choices("Why do they matter?", "Got it"),
            PUSH_EXPLANATION_SHARED_NODE,
        ),
        PUSH_EXPLANATION_SHARED_NODE: (
            _lines(
                ("Friends can finish a shared goal.", 0),
                ("You can celebrate right away.", 0),
                ("They can react when you finish too.", 0),
            ),
            _choices("How do I enable them?", "Makes sense"),
            PUSH_EXPLANATION_MOBILE_NODE,
        ),
        PUSH_EXPLANATION_MOBILE_NODE: (
            _lines(
                ("Desktop is straightforward.", 0),
                (
                    "On iPhone and Android, install Dogether to your Home Screen first.",
                    0,
                ),
            ),
            _choices("Why install it?", "Got it"),
            PUSH_EXPLANATION_CONSENT_NODE,
        ),
        PUSH_EXPLANATION_CONSENT_NODE: (
            _lines(
                ("The installed app can ask your phone for permission.", 0),
                (
                    "Your operating system shows the consent prompt. Only you can approve it.",
                    3,
                ),
            ),
            _choices("What can I control?", "Makes sense"),
            PUSH_EXPLANATION_CONTROLS_NODE,
        ),
        PUSH_EXPLANATION_CONTROLS_NODE: (
            _lines(
                ("Notifications are not all-or-nothing.", 0),
                ("Each goal has its own settings.", 0),
            ),
            _choices("Which settings?", "Got it"),
            PUSH_EXPLANATION_SETTINGS_NODE,
        ),
        PUSH_EXPLANATION_SETTINGS_NODE: (
            _lines(
                (
                    "Choose alerts when friends complete it and cap completion alerts per day. Also, choose alerts for reactions.",
                    3.5,
                )
            ),
            _choices("Where are those controls?", "Makes sense"),
            PUSH_EXPLANATION_FINISH_NODE,
        ),
    }
    if scene_id in scenes:
        lines, choices, next_scene = scenes[scene_id]
        if choice is None:
            return _scene(owner, scene_id, lines=lines, choices=choices)
        return _transition(owner, next_scene)

    options = _choices(
        "Enable notifications",
        "Show me Manage Goals",
        "Cool, thank you for the explanation.",
    )
    if choice is None:
        return _scene(
            owner,
            PUSH_EXPLANATION_FINISH_NODE,
            lines=_lines(
                ("They live on Manage Goals.", 0),
                ("Open a goal.", 0),
                ("Adjust what works for you.", 0),
            ),
            choices=options,
        )
    if choice == "Enable notifications":
        if owner == STANDARD_STORY_ID:
            return _finish_explanation(owner, destination="push_notifications")
        return AssistantTurn(
            story_id=owner,
            scene_id=PUSH_NODE,
            destination="push_notifications",
            event_updates={
                PUSH_EVENT_ID: {"outcome": "interrupted", "awaiting": "enable"}
            },
            state_story=owner,
            state_scene=PUSH_NODE,
            state_status="paused",
        )
    if choice == "Show me Manage Goals":
        if owner == STANDARD_STORY_ID:
            return _finish_explanation(owner, destination="manage_goals")
        return AssistantTurn(
            story_id=owner,
            scene_id=PUSH_NODE,
            destination="manage_goals",
            state_story=owner,
            state_scene=PUSH_NODE,
            state_status="paused",
        )
    return _finish_explanation(
        owner,
        lines=_lines(("Ciao.", 0)),
        assistant_leaves=True,
    )
