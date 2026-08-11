"""A short, evidence-based weekly progress story."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from math import ceil
import random
from typing import Final

from src.assistant.core import AssistantCard, AssistantChoice, AssistantContext, AssistantLine, AssistantSelection, AssistantStory, AssistantTurn
from src.assistant.state import AssistantState, WEEKLY_STAR_EVENT_ID
from src.assistant.stories.star_tutorial import (
    STAR_TUTORIAL_INTRO_SCENE,
    STAR_TUTORIAL_SCENES,
    star_tutorial_turn,
)
from src.assistant.stories.personal_highlight_tutorial import record_first_weekly_summary_view
from src.assistant.stories.weekly_summary_analysis import GoalResult, WeekResult, _analyse, _date, _datetime, _momentum_halves, _now, _week_start
from src.assistant.stories.weekly_summary_insights import _additional_insights, _shared_insights, _used_existing_insights
from src.assistant.stories.tutorial import READY_NODE, STANDARD_STORY_ID
from src.db.persistence_helpers import APP_ZONE
from src.db.persistence_helpers import debug_info_enabled
from src.pages.common_helpers import compact_goal_activity_html

WEEKLY_SUMMARY_STORY_ID: Final = "weekly_summary"
WEEK_SELECTION_EVENT_ID: Final = "weekly_summary.selection"
SELECT_SCENE: Final = "weekly.select"
SUMMARY_SCENE: Final = "weekly.summary"
DETAILS_SCENE: Final = "weekly.details"
STAR_AWARD_SCENE: Final = "weekly.star_award"
STAR_TUTORIAL_RETURN_SCENE: Final = "weekly.star_tutorial.return"
UNAVAILABLE_PREFACE_SCENE: Final = "weekly.unavailable_preface"
UNAVAILABLE_HINT_SCENE: Final = "weekly.unavailable_hint"
WEEK_TO_WEEK_CHART_WEEKS: Final = 20
WEEKLY_SUMMARY_UNAVAILABLE_MESSAGE: Final = "Currently Unavailable"
WEEKLY_STAR_REWARD_UNLOCKED_KNOWLEDGE_KEY: Final = "stars.weekly_rewarded"
STAR_TUTORIAL_MAX_STARS: Final = 5

# Development-only switch: each displayed report earns a STAR, includin
# repeated views of the same partial or final week.
DEBUG_AWARD_STAR_EVERY_REPORT: Final = False


def _weekly_star_evaluation(state: AssistantState, start: date, rate: float) -> tuple[dict[str, object], int]:
    """Return a persisted-once weekly STAR decision and its STAR increment."""
    week = start.isoformat()
    previous = state.events.get(WEEKLY_STAR_EVENT_ID, {})
    if isinstance(previous, dict) and previous.get("evaluated_week") == week:
        return previous, 0
    first_star = state.stars == 0
    probability = 0.9 if rate > 80 else 0.5 if rate > 50 else 0
    awarded = first_star or (probability > 0 and random.random() < probability)
    result: dict[str, object] = {
        "evaluated_week": week,
        "awarded": awarded,
        "first_star": first_star and awarded,
    }
    if first_star and rate < 50:
        # This lets the presentation note remain tied to this one exceptional
        # award, rather than appearing for later low-completion weeks.
        result["low_completion_note"] = True
    if awarded:
        result["last_claimed_week"] = week
    return result, int(awarded)


def _debug_star_awards_enabled(context: AssistantContext) -> bool:
    """Keep the source-level test switch restricted to debug profiles."""
    return DEBUG_AWARD_STAR_EVERY_REPORT and debug_info_enabled(context.current_user)


def _star_award_choices(state: AssistantState) -> tuple[AssistantChoice, ...]:
    choices = [AssistantChoice("acknowledge_star", "Nice!")]
    if state.stars < STAR_TUTORIAL_MAX_STARS:
        choices.append(AssistantChoice("explain_stars", "What are STARs?"))
    return tuple(choices)


def _weekly_summary_unlock_at(context: AssistantContext) -> datetime | None:
    """Return the precise time a new account qualifies for analysis.

    Older account records and lightweight test contexts may not have a creation
    timestamp, so they remain eligible for the established summary behavior.
    """
    created_at = _datetime(context.current_user.get("created_at"))
    if created_at is None:
        return None
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=APP_ZONE)
    else:
        created_at = created_at.astimezone(APP_ZONE)
    return created_at + timedelta(days=6)


def weekly_summary_is_available(current_user: dict, now: datetime) -> bool:
    """Whether the account has completed the six-day wait for analysis."""
    context = AssistantContext(
        user_id="",
        current_user=current_user,
        state=AssistantState(),
        session_state={},
        current_page_key="assistant",
        now=now,
    )
    unlock_at = _weekly_summary_unlock_at(context)
    return unlock_at is None or _now(context) >= unlock_at


class WeeklySummaryStory(AssistantStory):
    story_id = WEEKLY_SUMMARY_STORY_ID

    def entry_scene(self, context: AssistantContext) -> str:
        # Reports are intentionally non-resumable.  The STAR tutorial is the
        # one in-visit exception because it must return to its open report.
        if (
            context.state.story == self.story_id
            and context.state.status == "active"
            and context.state.scene in (*STAR_TUTORIAL_SCENES, STAR_TUTORIAL_RETURN_SCENE)
        ):
            return context.state.scene
        return SELECT_SCENE

    def advance(self, context: AssistantContext, scene_id: str | None, selection: AssistantSelection | None) -> AssistantTurn:
        scene = scene_id or self.entry_scene(context)
        unlock_at = _weekly_summary_unlock_at(context)
        if unlock_at is not None and _now(context) < unlock_at:
            if scene == UNAVAILABLE_PREFACE_SCENE:
                return AssistantTurn(
                    self.story_id,
                    scene,
                    lines=(AssistantLine("I give you a small hint", wait_before=1, typing_delay=3),),
                    state_story=self.story_id,
                    state_scene=UNAVAILABLE_HINT_SCENE,
                    state_status="active",
                    continue_flow=True,
                )
            if scene == UNAVAILABLE_HINT_SCENE:
                remaining_seconds = max(0, (unlock_at - _now(context)).total_seconds())
                remaining_hours = ceil(remaining_seconds / 3600)
                hint = f"It is unlocked in {remaining_hours} hours"
                return AssistantTurn(
                    self.story_id,
                    scene,
                    lines=(AssistantLine(hint, typing_delay=1.5),),
                    completed=True,
                    state_story=self.story_id,
                    state_scene=scene,
                    state_status="completed",
                )
            return AssistantTurn(
                self.story_id,
                scene,
                statuses=(WEEKLY_SUMMARY_UNAVAILABLE_MESSAGE,),
                keep_statuses_in_history=True,
                state_story=self.story_id,
                state_scene=UNAVAILABLE_PREFACE_SCENE,
                state_status="active",
                continue_flow=True,
            )
        now = _now(context)
        if scene == SELECT_SCENE:
            if (
                selection is None
                and context.state.story == self.story_id
                and context.state.status == "active"
            ):
                # Discard any persisted position from the previous resumable
                # implementation before continuing with the normal Assistant.
                return AssistantTurn(
                    self.story_id,
                    SELECT_SCENE,
                    completed=True,
                    state_story=STANDARD_STORY_ID,
                    state_scene=READY_NODE,
                    state_status="completed",
                    clear_events=(WEEK_SELECTION_EVENT_ID,),
                    continue_flow=True,
                )
            if selection is None or selection.choice_id not in {"this", "last"}:
                if now.weekday() >= 3:
                    return AssistantTurn(self.story_id, SELECT_SCENE, lines=(AssistantLine("Which week should I analyse?"),), choices=(AssistantChoice("this", "Week in progress"), AssistantChoice("last", "Last Final Week")), state_story=self.story_id, state_scene=SELECT_SCENE, state_status="active")
                return self._summary_turn(context, _week_start(now.date() - timedelta(days=7)), False)
            start = _week_start(now.date()) if selection.choice_id == "this" else _week_start(now.date() - timedelta(days=7))
            return self._summary_turn(context, start, selection.choice_id == "this")
        selected = context.state.events.get(WEEK_SELECTION_EVENT_ID, {})
        start = _date(selected.get("start")) if isinstance(selected, dict) else None
        partial = bool(selected.get("partial")) if isinstance(selected, dict) else False
        extra_id = str(selected.get("extra", "")) if isinstance(selected, dict) else ""
        shared_id = str(selected.get("shared", "")) if isinstance(selected, dict) else ""
        if start is None:
            return self.advance(context, SELECT_SCENE, None)
        result = _analyse(context, start, partial)
        if scene in STAR_TUTORIAL_SCENES:
            return star_tutorial_turn(
                context,
                self.story_id,
                scene,
                selection,
                return_scene=STAR_TUTORIAL_RETURN_SCENE,
            )
        if scene == STAR_TUTORIAL_RETURN_SCENE:
            weekly = context.state.events.get(WEEKLY_STAR_EVENT_ID, {})
            return self._week_to_week_turn(
                result,
                weekly_update=dict(weekly) if isinstance(weekly, dict) else {},
            )
        if scene == STAR_AWARD_SCENE or (
            selection is not None
            and selection.choice_id in {"acknowledge_star", "explain_stars"}
        ):
            if selection and selection.choice_id == "acknowledge_star":
                weekly = context.state.events.get(WEEKLY_STAR_EVENT_ID, {})
                acknowledged = dict(weekly) if isinstance(weekly, dict) else {}
                acknowledged["acknowledged"] = True
                return self._week_to_week_turn(
                    result,
                    weekly_update=acknowledged,
                )
            if (
                selection
                and selection.choice_id == "explain_stars"
                and context.state.stars < STAR_TUTORIAL_MAX_STARS
            ):
                weekly = context.state.events.get(WEEKLY_STAR_EVENT_ID, {})
                acknowledged = dict(weekly) if isinstance(weekly, dict) else {}
                acknowledged["acknowledged"] = True
                return AssistantTurn(
                    self.story_id,
                    STAR_AWARD_SCENE,
                    event_updates={WEEKLY_STAR_EVENT_ID: acknowledged},
                    state_story=self.story_id,
                    state_scene=STAR_TUTORIAL_INTRO_SCENE,
                    state_status="active",
                    # The STAR was already saved when it was awarded.  Keep
                    # this handoff transient so the weekly report itself does
                    # not become resumable in the database.
                    continue_flow=True,
                )
            return AssistantTurn(
                self.story_id, STAR_AWARD_SCENE,
                lines=(AssistantLine("⭐ A STAR for the week."),),
                choices=_star_award_choices(context.state),
                star_grant_animation=True,
                state_story=self.story_id, state_scene=STAR_AWARD_SCENE, state_status="active",
            )
        if scene == DETAILS_SCENE:
            if selection and selection.choice_id == "done":
                return AssistantTurn(self.story_id, DETAILS_SCENE, completed=True, assistant_leaves=True, state_story=self.story_id, state_scene=DETAILS_SCENE, state_status="completed")
            if selection and selection.choice_id == "all_insights":
                return self._all_insights_turn(result, str(selected.get("extra", "")), True)
            return self._details_turn(result)
        if selection and selection.choice_id == "details":
            return self._details_turn(result, start, partial, extra_id)
        if selection and selection.choice_id == "continue":
            weekly = context.state.events.get(WEEKLY_STAR_EVENT_ID, {})
            if (
                context.state.story == self.story_id
                and context.state.status == "active"
                and (_debug_star_awards_enabled(context) or not partial)
                and isinstance(weekly, dict)
                and weekly.get("awarded")
                and not weekly.get("acknowledged")
            ):
                return self.advance(context, STAR_AWARD_SCENE, None)
            return self._remaining_summary(result, extra_id, shared_id, start, partial)
        if selection and selection.choice_id == "more":
            return self._more_summary(result, extra_id, shared_id)
        if selection and selection.choice_id == "all_insights":
            return self._all_insights_turn(result, extra_id, bool(selected.get("details_seen", False)))
        if selection and selection.choice_id == "done":
            return AssistantTurn(self.story_id, SUMMARY_SCENE, completed=True, assistant_leaves=True, state_story=WEEKLY_SUMMARY_STORY_ID, state_scene=SUMMARY_SCENE, state_status="completed")
        return self._opening_summary(result)

    def _summary_turn(self, context: AssistantContext, start: date, partial: bool) -> AssistantTurn:
        result = _analyse(context, start, partial)
        event_updates: dict[str, dict[str, object]] = {WEEK_SELECTION_EVENT_ID: {"start": start.isoformat(), "partial": partial}}
        event_updates.update(record_first_weekly_summary_view(context.state, context.now))
        stars_delta = 0
        debug_awards_enabled = _debug_star_awards_enabled(context)
        if debug_awards_enabled:
            weekly_result = {
                "evaluated_week": start.isoformat(),
                "awarded": True,
                "last_claimed_week": start.isoformat(),
                "debug_forced": True,
            }
            stars_delta = 1
            event_updates[WEEKLY_STAR_EVENT_ID] = weekly_result
        elif not partial:
            weekly_result, stars_delta = _weekly_star_evaluation(context.state, start, result.rate)
            event_updates[WEEKLY_STAR_EVENT_ID] = weekly_result
        turn = self._opening_summary(result, include_week_to_week=not bool(stars_delta))
        opening = (AssistantLine("This week is still moving."), AssistantLine("Here’s the story so far.", typing_delay=0.6)) if partial else (AssistantLine("Let’s look at last week."), AssistantLine("A few things stand out.", typing_delay=0.6))
        content = (*opening, *turn.content) if turn.content else ()
        changes = {
            **turn.__dict__,
            "lines": (*opening, *turn.lines),
            "content": content,
            "event_updates": event_updates,
            "stars_delta": stars_delta,
            "knowledge_updates": (
                {WEEKLY_STAR_REWARD_UNLOCKED_KNOWLEDGE_KEY: True}
                if stars_delta
                else {}
            ),
            # Starting any report durably records the viewed milestone and a
            # possible STAR, but never a resumable weekly-summary position.
            "completed": True,
            "state_story": STANDARD_STORY_ID,
            "state_scene": READY_NODE,
            "state_status": "completed",
        }
        if stars_delta:
            # Keep the STAR acknowledgement in this report turn.  This avoids
            # storing a weekly-summary scene solely to resume the award UI.
            changes.update(
                lines=(*changes["lines"], AssistantLine("⭐ A STAR for the week.")),
                content=(*changes["content"], AssistantLine("⭐ A STAR for the week.")),
                choices=_star_award_choices(context.state),
                star_grant_animation=True,
            )
            if weekly_result.get("low_completion_note"):
                note = AssistantLine(
                    "I do wonder whether STARs should be given for such a low completion rate."
                )
                changes.update(
                    lines=(*changes["lines"], note),
                    content=(*changes["content"], note),
                )
        return AssistantTurn(**changes)

    def _opening_summary(
        self, result: WeekResult, *, include_week_to_week: bool = True
    ) -> AssistantTurn:
        if not result.active:
            message = (
                f"Only {result.skipped} excused period{'s were' if result.skipped != 1 else ' was'} recorded."
                if result.skipped
                else "No goals were active to analyse."
            )
            content = (
                AssistantLine("That week was quiet."),
                AssistantLine(message, typing_delay=0.6),
            )
            return AssistantTurn(
                self.story_id,
                SUMMARY_SCENE,
                lines=content,
                content=content,
                choices=(AssistantChoice("done", "Done"),),
            )
        title = "COMPLETION SO FAR" if result.partial else "WEEKLY COMPLETION"
        detail = f"{result.fulfilled} of {result.active} goal periods completed"
        if result.partial:
            detail += f"\n{result.start.strftime('%A')}–{result.end.strftime('%A')}"
        headline_rows = [("Incomplete", str(result.active - result.fulfilled))]
        if result.skipped:
            headline_rows.append(("Excused", str(result.skipped)))
        headline = AssistantCard(
            title,
            f"{round(result.rate)}%",
            detail,
            tuple(headline_rows),
            result.rate,
        )
        if result.active < 3:
            observation = (
                f"You completed all {result.active} active period{'s' if result.active != 1 else ''}."
                if result.fulfilled == result.active
                else "A fuller story will appear as more periods are recorded."
            )
            content: tuple[AssistantLine | AssistantCard, ...] = (
                AssistantLine("There isn’t much data yet."),
                headline,
                AssistantLine(observation, typing_delay=0.6),
            )
            return AssistantTurn(
                self.story_id,
                SUMMARY_SCENE,
                lines=tuple(item for item in content if isinstance(item, AssistantLine)),
                cards=(headline,),
                content=content,
                choices=(AssistantChoice("done", "Done"),),
            )
        content: list[AssistantLine | AssistantCard] = [
            AssistantLine("First, the big picture."),
            headline,
            AssistantLine(_headline_analysis(result)),
        ]
        if include_week_to_week:
            content.extend(self._week_to_week_content(result))
        lines = tuple(item for item in content if isinstance(item, AssistantLine))
        cards = tuple(item for item in content if isinstance(item, AssistantCard))
        return AssistantTurn(self.story_id, SUMMARY_SCENE, lines=lines, cards=cards, content=tuple(content), choices=(AssistantChoice("continue", "Continue"),))

    @staticmethod
    def _week_to_week_content(result: WeekResult) -> tuple[AssistantLine | AssistantCard, ...]:
        if result.previous_rate is None or result.partial:
            return ()
        diff = result.rate - result.previous_rate
        workload = result.active - result.previous_active
        content: list[AssistantLine | AssistantCard] = [
            AssistantCard(
                "WEEK TO WEEK",
                f"{diff:+.0f} completion points",
                "",
                (
                    ("Previous week", f"{result.previous_rate:.0f}% · {result.previous_active} active"),
                    ("Selected week", f"{result.rate:.0f}% · {result.active} active"),
                    ("Workload", f"{workload:+d} active periods"),
                ),
                weekly_chart=_week_to_week_chart(result),
            )
        ]
        comparison = _comparison_analysis(result, diff)
        if comparison:
            content.append(AssistantLine(comparison))
        return tuple(content)

    def _week_to_week_turn(
        self,
        result: WeekResult,
        *,
        weekly_update: dict[str, object],
    ) -> AssistantTurn:
        """Restore the normal pause after the Week-to-Week insight."""
        content = self._week_to_week_content(result)
        if not content:
            return self._remaining_summary(result)
        return AssistantTurn(
            self.story_id,
            SUMMARY_SCENE,
            lines=tuple(item for item in content if isinstance(item, AssistantLine)),
            cards=tuple(item for item in content if isinstance(item, AssistantCard)),
            content=content,
            choices=(AssistantChoice("continue", "Continue"),),
            event_updates={WEEKLY_STAR_EVENT_ID: weekly_update},
            state_story=self.story_id,
            state_scene=SUMMARY_SCENE,
            state_status="active",
        )

    def _remaining_summary_content(
        self, result: WeekResult, selected_id: str = "", shared_id: str = ""
    ) -> tuple[list[list[AssistantLine | AssistantCard]], str, str]:
        """Build the remaining insights as individually presentable groups."""
        groups: list[list[AssistantLine | AssistantCard]] = []
        strongest = _strongest_goal(result.goals)
        improved = _most_improved_goal(result.goals)
        positive = improved if improved and improved != strongest else strongest
        streak_goal = _select_streak(result.goals, positive)
        if streak_goal:
            groups.append(list(_streak_content(streak_goal)))
        elif improved and positive == improved:
            groups.append([
                    AssistantLine(f"{improved.name} made the biggest jump."),
                    AssistantCard(
                        "MOST IMPROVED",
                        improved.name,
                        f"{improved.previous_rate:.0f}% → {improved.rate:.0f}%",
                        progress=improved.rate,
                    ),
                    AssistantLine(
                        f"It gained {improved.rate - improved.previous_rate:.0f} percentage points "
                        "from the week before."
                    ),
                ])
        else:
            groups.append([
                AssistantLine(f"{strongest.name} led the way."),
                AssistantCard("STRONGEST GOAL", strongest.name, f"{strongest.fulfilled} of {strongest.active} periods completed", progress=strongest.rate),
                AssistantLine(_strongest_analysis(strongest)),
            ])
        grouped_content = [item for group in groups for item in group]
        used_types, used_subjects = _used_existing_insights(grouped_content)
        shared_candidates = _shared_insights(result, used_subjects, used_types)
        selected_shared = next((item for item in shared_candidates if item.identifier == shared_id), None)
        if selected_shared is None and shared_candidates:
            selected_shared = random.choice(shared_candidates)
        if selected_shared is not None:
            groups.append(list(selected_shared.content))
        near_miss = _select_near_miss(result)
        weak = min((goal for goal in result.goals if goal.active), key=lambda goal: (goal.rate, -goal.active))
        if near_miss is not None:
            goal, when, percent, current, target = near_miss
            unit_detail = f"{current} of {target}" if target > 1 else f"{percent:.0f}% of target"
            period_label = "Weekly period" if goal.is_weekly else when.strftime("%A")
            groups.append([
                    AssistantLine(f"{goal.name} was closer than the score suggests.", typing_delay=0.6),
                    AssistantCard(
                        "NEAR MISS",
                        goal.name,
                        f"{period_label} · {unit_detail}",
                        progress=percent,
                    ),
                    AssistantLine(_near_miss_analysis(result, goal, percent, current, target)),
                ])
        elif weak.rate < 60 and weak != positive:
            groups.append([
                AssistantLine("One goal needs a closer look.", typing_delay=0.6),
                AssistantCard("NEEDS ATTENTION", weak.name, f"{weak.fulfilled} of {weak.active} periods completed", progress=weak.rate),
                AssistantLine(_weak_analysis(weak)),
            ])
        # Existing cards are deliberately considered before choosing an extra insight.
        grouped_content = [item for group in groups for item in group]
        used_types, used_subjects = _used_existing_insights(grouped_content)
        candidates = _additional_insights(result, used_types, used_subjects)
        selected_extra = next((item for item in candidates if item.identifier == selected_id), None)
        if selected_extra is None and candidates:
            selected_extra = random.choice(candidates)
        if selected_extra is not None:
            groups.append(list(selected_extra.content))
        return groups, selected_extra.identifier if selected_extra else "", selected_shared.identifier if selected_shared else ""

    def _remaining_summary(self, result: WeekResult, selected_id: str = "", shared_id: str = "", start: date | None = None, partial: bool = False) -> AssistantTurn:
        """Render two further insights before offering the next conversational break."""
        groups, selected_extra_id, selected_shared_id = self._remaining_summary_content(result, selected_id, shared_id)
        preview_groups = groups[:2]
        content: list[AssistantLine | AssistantCard] = [AssistantLine("Let’s look a little closer.", typing_delay=0.4)]
        content.extend(item for group in preview_groups for item in group)
        lines = tuple(item for item in content if isinstance(item, AssistantLine))
        cards = tuple(item for item in content if isinstance(item, AssistantCard))
        updates = {WEEK_SELECTION_EVENT_ID: {"start": start.isoformat(), "partial": partial, "extra": selected_extra_id, "shared": selected_shared_id}} if start else {}
        choices = (AssistantChoice("more", "Show me more, please"),) if len(groups) > 2 else (AssistantChoice("details", "See goal details"), AssistantChoice("all_insights", "Show all insights"), AssistantChoice("done", "Done"))
        return AssistantTurn(self.story_id, SUMMARY_SCENE, lines=lines, cards=cards, content=tuple(content), choices=choices, event_updates=updates)

    def _more_summary(self, result: WeekResult, selected_id: str = "", shared_id: str = "") -> AssistantTurn:
        """Render the remaining insights after the second conversational break."""
        groups, _, _ = self._remaining_summary_content(result, selected_id, shared_id)
        content: list[AssistantLine | AssistantCard] = [AssistantLine("Here’s more.", typing_delay=0.4)]
        content.extend(item for group in groups[2:] for item in group)
        content.extend(_closing(result))
        return AssistantTurn(self.story_id, SUMMARY_SCENE, lines=tuple(item for item in content if isinstance(item, AssistantLine)), cards=tuple(item for item in content if isinstance(item, AssistantCard)), content=tuple(content), choices=(AssistantChoice("details", "See goal details"), AssistantChoice("all_insights", "Show all insights"), AssistantChoice("done", "Done")))

    def _all_insights_turn(self, result: WeekResult, selected_id: str = "", details_seen: bool = False) -> AssistantTurn:
        # The initial overview is intentionally not repeated.  Re-evaluate the existing
        # cards so this view also excludes facts already used by the standard story.
        groups, _, _ = self._remaining_summary_content(result, selected_id)
        used_types, used_subjects = _used_existing_insights(
            [item for group in groups for item in group]
        )
        remaining = _additional_insights(
            result, used_types, used_subjects, include_outgoing_support=True
        )
        content: list[AssistantLine | AssistantCard] = [AssistantLine("Here’s everything else I found.")]
        for insight in remaining:
            content.extend(insight.content)
        if len(content) == 1:
            content.append(AssistantLine("There were no other distinct insights to add."))
        choices = (AssistantChoice("done", "Close analysis"),) if details_seen else (AssistantChoice("details", "See goal details"), AssistantChoice("done", "Close analysis"))
        return AssistantTurn(self.story_id, SUMMARY_SCENE, lines=tuple(x for x in content if isinstance(x, AssistantLine)), cards=tuple(x for x in content if isinstance(x, AssistantCard)), content=tuple(content), choices=choices)

    def _details_turn(self, result: WeekResult, start: date | None = None, partial: bool = False, extra_id: str = "") -> AssistantTurn:
        rows = tuple(
            (
                goal.name,
                (
                    f"{goal.fulfilled} / {goal.active} · {goal.rate:.0f}%"
                    if goal.active
                    else "No active periods"
                )
                + (f" · {goal.skipped} excused" if goal.skipped else "")
                + f"\n{_detail_streak(goal.streak)}",
            )
            for goal in sorted(result.goals, key=lambda goal: (-goal.active, -goal.rate))
        )
        updates = {WEEK_SELECTION_EVENT_ID: {"start": start.isoformat(), "partial": partial, "extra": extra_id, "details_seen": True}} if start else {}
        return AssistantTurn(self.story_id, DETAILS_SCENE, lines=(AssistantLine("Here’s the goal-by-goal view."),), cards=(AssistantCard("GOAL DETAILS", "", "", rows),), choices=(AssistantChoice("all_insights", "Show all insights"), AssistantChoice("done", "Close analysis")), event_updates=updates, state_story=self.story_id, state_scene=DETAILS_SCENE, state_status="active")


def _week_to_week_chart(result: WeekResult) -> tuple[tuple[date, float, bool], ...]:
    """Return the fixed-length weekly series ending with the selected week."""
    rates = {
        start: fulfilled * 100 / active
        for start, fulfilled, active in result.history
        if active > 0 and start < result.start
    }
    starts = tuple(
        result.start - timedelta(days=7 * offset)
        for offset in range(WEEK_TO_WEEK_CHART_WEEKS - 1, -1, -1)
    )
    return tuple(
        (start, result.rate if start == result.start else rates.get(start, 0), start == result.start)
        for start in starts
    )


def _detail_streak(streak: StreakResult) -> str:
    ended = f"{streak.ended_value}-{streak.unit[:-1]} streak paused {streak.ended_on.strftime('%A')}" if streak.ended and streak.ended_on else None
    current = streak.label
    return f"{ended}\nCurrent streak: {current}" if ended and streak.value else ended or current


def _strongest_goal(goals: tuple[GoalResult, ...]) -> GoalResult:
    """Prefer a substantial habit over a perfect one-off result."""
    active_goals = tuple(goal for goal in goals if goal.active)
    return max(
        active_goals,
        key=lambda goal: (
            goal.rate * min(goal.active, 3) / 3,
            goal.fulfilled,
            goal.rate,
            goal.active,
        ),
    )


def _most_improved_goal(goals: tuple[GoalResult, ...]) -> GoalResult | None:
    candidates = tuple(
        goal
        for goal in goals
        if goal.active >= 2
        and goal.previous_rate is not None
        and goal.rate - goal.previous_rate >= 20
    )
    return max(candidates, key=lambda goal: goal.rate - (goal.previous_rate or 0), default=None)


def _select_streak(goals: tuple[GoalResult, ...], strongest: GoalResult) -> GoalResult | None:
    def score(goal: GoalResult) -> tuple[int, int, int, int]:
        streak = goal.streak
        milestone = streak.value in ({3, 4, 8, 12, 26, 52} if streak.unit == "weeks" else {3, 7, 14, 30, 50, 100})
        meaningful = max(streak.value, streak.ended_value, streak.highest) >= (3 if streak.unit == "weeks" else 5)
        event = streak.record or milestone or streak.started or streak.ended or streak.added > 0
        return (int(streak.record), int(milestone), int(event and meaningful), streak.added)
    candidate = max(goals, key=score)
    candidate_score = score(candidate)
    return (
        candidate
        if any(candidate_score[:3])
        and (candidate == strongest or candidate_score[:3] >= (0, 1, 0))
        else None
    )


def _streak_content(goal: GoalResult) -> tuple[AssistantLine | AssistantCard, ...]:
    streak = goal.streak
    if streak.ended and streak.restarted:
        title = "STREAK RECOVERY"; detail = f"Ended at {streak.ended_value} {streak.unit}\nRestarted after: {streak.restart_delay} period{'s' if streak.restart_delay != 1 else ''}"
        text = f"The {streak.ended_value}-{streak.unit[:-1]} streak paused on {streak.ended_on.strftime('%A')}.\nYou restarted it {'the next period' if streak.restart_delay == 1 else 'during the week'}."
    elif streak.record:
        title = "NEW STREAK RECORD"; detail = f"Previous best: {streak.previous_best} {streak.unit}"
        text = f"{goal.name} reached a new record.\nYou added {streak.added} successful {streak.unit} during the analysed week."
    elif streak.ended:
        title = "STREAK UPDATE"; detail = f"Ended at {streak.ended_value} {streak.unit}\nCurrent streak: {streak.value}"
        text = f"The streak paused at {streak.ended_value} {streak.unit}.\nThose successful {streak.unit} still happened."
    else:
        title = "CURRENT STREAK"; detail = f"This week: +{streak.added} {streak.unit}"
        if streak.has_skips: detail += f"\n{streak.fulfilled} completed · {streak.valid_skips} valid skips"
        text = (f"{streak.value}-{streak.unit[:-1]} streak.\nEvery period was completed or validly skipped." if streak.has_skips else f"The streak reached {streak.value} {streak.unit}.\nThis week kept it moving.")
    recent_activity_html = _recent_activity_html(goal) if streak.record else ""
    return (AssistantLine(f"{goal.name} kept its rhythm."), AssistantCard(title, goal.name, f"{streak.label}\n{detail}", (("Recent", " ".join(streak.symbols)),), recent_activity_html=recent_activity_html), AssistantLine(text))


def _recent_activity_html(goal: GoalResult) -> str:
    if not goal.source_goal or not goal.source_participant or goal.activity_end is None:
        return ""
    activity_now = datetime.combine(goal.activity_end, time(hour=12), tzinfo=APP_ZONE)
    return compact_goal_activity_html(goal.source_goal, goal.source_participant, now=activity_now)


def _headline_text(result: WeekResult) -> str:
    if result.partial: return "You’re currently on a strong pace." if result.rate >= 75 else "The week is still open." if result.rate >= 50 else "There is still room to change the story."
    return "That was a very strong week." if result.rate >= 90 else "That was a solid week." if result.rate >= 75 else "More worked than didn’t." if result.rate >= 50 else "The week was uneven." if result.rate >= 25 else "The targets had a difficult week."


def _headline_analysis(result: WeekResult) -> str:
    headline = _headline_text(result)
    label = "so far" if result.partial else "finished at"
    activity = (
        f"\nProgress was recorded on {result.active_days} "
        f"day{'s' if result.active_days != 1 else ''}."
        if result.active_days and result.rate < 50
        else ""
    )
    return (
        f"{headline}\nYou completed {result.fulfilled} of {result.active} active goal periods.\n"
        f"The week {label} {result.rate:.0f}%.{activity}"
    )


def _comparison_analysis(result: WeekResult, diff: float) -> str:
    workload_change = result.active - result.previous_active
    meaningful_workload = abs(workload_change) >= 3 or (
        result.previous_active > 0 and abs(workload_change) / result.previous_active >= .2
    )
    if diff >= 5:
        if meaningful_workload and workload_change > 0: return "You improved despite a busier week."
        if meaningful_workload and workload_change < 0: return "The score improved, although the week was lighter."
        return f"A clear step forward.\nCompletion increased by {diff:.0f} percentage points."
    if diff <= -5:
        if meaningful_workload and workload_change > 0: return "The result dropped, but the week was also busier."
        if meaningful_workload and workload_change < 0: return "The week was lighter and less complete."
        return f"The result dropped this week.\nCompletion fell by {abs(diff):.0f} percentage points."
    if meaningful_workload and workload_change > 0: return "You maintained the result with more active periods."
    if meaningful_workload and workload_change < 0: return "The result stayed similar during a lighter week."
    return "Almost the same result.\nThe score barely moved,\nbut the daily rhythm tells the fuller story."


def _strongest_analysis(goal: GoalResult) -> str:
    if goal.rate >= 100:
        return f"Every relevant period was completed.\n{goal.name} did not miss once."
    return f"Your steadiest substantial goal this week.\n{goal.name} completed {goal.fulfilled} of {goal.active} periods."


def _rhythm_analysis(result: WeekResult) -> str:
    active_days = [(day, done / active) for day, active, done in result.daily if active]
    if not active_days:
        return "The rhythm is still taking shape.\nThere is more of the week to fill in."
    best_day, best_rate = max(active_days, key=lambda item: item[1])
    worst_day, worst_rate = min(active_days, key=lambda item: item[1])
    perfect_streak = _longest_perfect_day_streak(result.daily)
    for index, (day, rate) in enumerate(active_days[:-1]):
        next_day, next_rate = active_days[index + 1]
        if (next_day - day).days == 1 and rate < .5 and next_rate >= .75:
            return (
                f"{day.strftime('%A')} interrupted the rhythm.\n"
                f"{next_day.strftime('%A')} bounced back to {next_rate:.0%}."
            )
    first, second = _momentum_halves(result)
    if first is not None and second is not None and second - first >= .2:
        return (
            f"The week finished much stronger than it started.\n"
            f"The later stretch rose by {(second - first) * 100:.0f} percentage points."
        )
    if first is not None and second is not None and first - second >= .2:
        return (
            f"The week started strongly, then became less consistent.\n"
            f"{best_day.strftime('%A')} still reached {best_rate:.0%}."
        )
    if perfect_streak >= 3:
        return (
            f"You built a {perfect_streak}-day perfect streak.\n"
            "Every active goal was completed on each of those days."
        )
    if best_rate - worst_rate < .2:
        return "Your progress was fairly steady.\nThere was no sharp inactive gap,\nand most days contributed something."
    return (
        f"{best_day.strftime('%A')} was strongest.\n"
        f"{worst_day.strftime('%A')} had the hardest result."
    )


def _longest_perfect_day_streak(daily: tuple[tuple[date, int, int], ...]) -> int:
    longest = current = 0
    for _, active, done in daily:
        if active and done == active:
            current += 1
            longest = max(longest, current)
        elif active:
            current = 0
    return longest


def _select_near_miss(
    result: WeekResult,
) -> tuple[GoalResult, date, float, int, int] | None:
    return max(
        result.near_misses,
        key=lambda item: (item[2], item[0].active),
        default=None,
    )


def _near_miss_analysis(
    result: WeekResult,
    goal: GoalResult,
    percent: float,
    current: int,
    target: int,
) -> str:
    gap = max(0, target - current)
    if target > 1:
        close = f"It stopped only {gap} short of its target."
    else:
        close = f"It reached {percent:.0f}% of its target."
    count = len(result.near_misses)
    if count > 1:
        return f"{close}\nThere were {count} near misses across the week."
    return f"{close}\nThe binary score hides how close that period was."


def _weak_analysis(goal: GoalResult) -> str:
    return (
        f"{goal.name} had the hardest week.\n"
        f"It completed {goal.fulfilled} of {goal.active} periods.\n"
        "That is the clearest place to focus next."
    )


def _closing(result: WeekResult) -> tuple[AssistantLine, ...]:
    if result.partial:
        return (AssistantLine("The story is not finished yet.\n\nThe remaining days can still change it.", typing_delay=0.6),)
    if result.rate >= 90:
        evidence = (
            f"{result.perfect_days} perfect days."
            if result.perfect_days
            else f"{result.fulfilled} completed periods."
        )
        return (AssistantLine(f"That was a serious week.\n\n{evidence}\nThe consistency was real.", typing_delay=0.6),)
    difficult_days = [
        day
        for day, active, done in result.daily
        if active and done < active
    ]
    if len(difficult_days) == 1 and result.perfect_days >= 2:
        return (AssistantLine("One difficult day did not control your week.\n\nThe rest of the rhythm held together.", typing_delay=0.6),)
    if result.near_misses:
        return (AssistantLine("This week was closer than the final score looks.\n\nThe next adjustment can be small.", typing_delay=0.6),)
    if result.rate < 25:
        activity = (
            f"You still made progress on {result.active_days} days."
            if result.active_days
            else "The next week starts with a clean page."
        )
        return (AssistantLine(f"This week did not go to plan.\n\n{activity}", typing_delay=0.6),)
    if result.perfect_days:
        return (AssistantLine(f"Not perfect. Still grounded.\n\n{result.perfect_days} fully successful day{'s' if result.perfect_days != 1 else ''} gave the week a base.", typing_delay=0.6),)
    return (AssistantLine("The week was uneven.\n\nThe useful part is knowing where to focus next.", typing_delay=0.6),)
