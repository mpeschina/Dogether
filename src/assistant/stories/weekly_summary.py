"""A short, evidence-based weekly progress story."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Final

from src.assistant.core import AssistantCard, AssistantChoice, AssistantContext, AssistantLine, AssistantSelection, AssistantStory, AssistantTurn

WEEKLY_SUMMARY_STORY_ID: Final = "weekly_summary"
WEEK_SELECTION_EVENT_ID: Final = "weekly_summary.selection"
SELECT_SCENE: Final = "weekly.select"
SUMMARY_SCENE: Final = "weekly.summary"
DETAILS_SCENE: Final = "weekly.details"


@dataclass(frozen=True)
class GoalResult:
    name: str
    fulfilled: int
    active: int
    skipped: int
    previous_rate: float | None

    @property
    def rate(self) -> float:
        return self.fulfilled * 100 / self.active if self.active else 0


@dataclass(frozen=True)
class WeekResult:
    start: date
    end: date
    partial: bool
    fulfilled: int
    active: int
    skipped: int
    daily: tuple[tuple[date, int, int], ...]
    goals: tuple[GoalResult, ...]
    previous_rate: float | None

    @property
    def rate(self) -> float:
        return self.fulfilled * 100 / self.active if self.active else 0


class WeeklySummaryStory(AssistantStory):
    story_id = WEEKLY_SUMMARY_STORY_ID

    def entry_scene(self, context: AssistantContext) -> str:
        selected = context.state.events.get(WEEK_SELECTION_EVENT_ID, {})
        if isinstance(selected, dict) and selected.get("start"):
            return SUMMARY_SCENE
        return SELECT_SCENE

    def advance(self, context: AssistantContext, scene_id: str | None, selection: AssistantSelection | None) -> AssistantTurn:
        scene = scene_id or self.entry_scene(context)
        now = _now(context)
        if scene == SELECT_SCENE:
            if selection is None:
                if now.weekday() >= 3:
                    return AssistantTurn(self.story_id, SELECT_SCENE, lines=(AssistantLine("Which week should I analyse?"),), choices=(AssistantChoice("this", "This week"), AssistantChoice("last", "Last week")), state_story=self.story_id, state_scene=SELECT_SCENE, state_status="active")
                return self._summary_turn(context, _week_start(now.date() - timedelta(days=7)), False)
            start = _week_start(now.date()) if selection.choice_id == "this" else _week_start(now.date() - timedelta(days=7))
            return self._summary_turn(context, start, selection.choice_id == "this")
        selected = context.state.events.get(WEEK_SELECTION_EVENT_ID, {})
        start = _date(selected.get("start")) if isinstance(selected, dict) else None
        partial = bool(selected.get("partial")) if isinstance(selected, dict) else False
        if start is None:
            return self.advance(context, SELECT_SCENE, None)
        result = _analyse(context, start, partial)
        if scene == DETAILS_SCENE:
            if selection and selection.choice_id == "done":
                return AssistantTurn(self.story_id, DETAILS_SCENE, completed=True, state_story=self.story_id, state_scene=DETAILS_SCENE, state_status="completed")
            return self._details_turn(result)
        if selection and selection.choice_id == "details":
            return self._details_turn(result)
        if selection and selection.choice_id == "done":
            return AssistantTurn(self.story_id, SUMMARY_SCENE, completed=True, state_story=WEEKLY_SUMMARY_STORY_ID, state_scene=SUMMARY_SCENE, state_status="completed")
        return self._summary_content(result)

    def _summary_turn(self, context: AssistantContext, start: date, partial: bool) -> AssistantTurn:
        result = _analyse(context, start, partial)
        turn = self._summary_content(result)
        opening = (AssistantLine("This week is still moving."), AssistantLine("Here’s the story so far.", typing_delay=0.6)) if partial else (AssistantLine("Let’s look at last week."), AssistantLine("A few things stand out.", typing_delay=0.6))
        return AssistantTurn(**{**turn.__dict__, "lines": (*opening, *turn.lines), "event_updates": {WEEK_SELECTION_EVENT_ID: {"start": start.isoformat(), "partial": partial}}, "state_story": self.story_id, "state_scene": SUMMARY_SCENE, "state_status": "active"})

    def _summary_content(self, result: WeekResult) -> AssistantTurn:
        if not result.active:
            return AssistantTurn(self.story_id, SUMMARY_SCENE, lines=(AssistantLine("That week was quiet."), AssistantLine("No goals were active to analyse.", typing_delay=0.6)), choices=(AssistantChoice("done", "Done"),))
        title = "COMPLETION SO FAR" if result.partial else "WEEKLY COMPLETION"
        detail = f"{result.fulfilled} of {result.active} goal periods completed"
        if result.partial:
            detail += f"\n{result.start.strftime('%A')}–{result.end.strftime('%A')}"
        headline = AssistantCard(title, f"{round(result.rate)}%", detail, (("Incomplete", str(result.active - result.fulfilled - result.skipped)), ("Excused", str(result.skipped))) if result.skipped else (("Incomplete", str(result.active - result.fulfilled)),), result.rate)
        if result.active < 3:
            observation = "You completed both active goals." if result.fulfilled == result.active else "A fuller story will appear as the week fills in."
            return AssistantTurn(self.story_id, SUMMARY_SCENE, lines=(AssistantLine("There isn’t much data yet."), AssistantLine("But one thing already stands out.", typing_delay=0.6), AssistantLine(observation)), cards=(headline,), choices=(AssistantChoice("done", "Done"),))
        lines = [AssistantLine("First, the big picture."), AssistantLine(_headline_text(result))]
        cards = [headline]
        if result.previous_rate is not None and not result.partial:
            diff = result.rate - result.previous_rate
            lines.append(AssistantLine("And you moved forward." if diff >= 5 else "Compared with the week before:" if diff <= -5 else "The result was close to last week."))
            cards.append(AssistantCard("WEEK TO WEEK", f"{diff:+.0f} percentage points", "", (("Previous week", f"{result.previous_rate:.0f}%"), ("Selected week", f"{result.rate:.0f}%"))))
        strongest = max(result.goals, key=lambda goal: (goal.rate, goal.active))
        lines.extend((AssistantLine("One goal carried the week."), AssistantLine(f"{strongest.name} did not miss once." if strongest.rate >= 100 else f"{strongest.name} was your steadiest goal.")))
        cards.append(AssistantCard("STRONGEST GOAL", strongest.name, f"{strongest.fulfilled} of {strongest.active} periods completed", progress=strongest.rate))
        day_rows = tuple((day.strftime("%a").upper(), "—" if active == 0 else f"{round(done * 100 / active)}%") for day, active, done in result.daily)
        lines.append(AssistantLine("Here’s how the week moved."))
        cards.append(AssistantCard("DAILY RHYTHM", "", "No active goals are shown as —", day_rows))
        weak = min((goal for goal in result.goals if goal.active), key=lambda goal: goal.rate)
        if weak.rate < 60 and weak != strongest:
            lines.extend((AssistantLine("One goal had the hardest week."), AssistantLine(f"{weak.name} lost some momentum.")))
            cards.append(AssistantCard("NEEDS ATTENTION", weak.name, f"{weak.fulfilled} of {weak.active} periods completed", progress=weak.rate))
        lines.extend(_closing(result))
        return AssistantTurn(self.story_id, SUMMARY_SCENE, lines=tuple(lines), cards=tuple(cards), choices=(AssistantChoice("details", "See goal details"), AssistantChoice("done", "Done")))

    def _details_turn(self, result: WeekResult) -> AssistantTurn:
        rows = tuple((goal.name, f"{goal.fulfilled} / {goal.active} · {goal.rate:.0f}%") for goal in sorted(result.goals, key=lambda goal: (-goal.active, -goal.rate)))
        return AssistantTurn(self.story_id, DETAILS_SCENE, lines=(AssistantLine("Here’s the goal-by-goal view."),), cards=(AssistantCard("GOAL DETAILS", "", "", rows),), choices=(AssistantChoice("done", "Close analysis"),), state_story=self.story_id, state_scene=DETAILS_SCENE, state_status="active")


def _analyse(context: AssistantContext, start: date, partial: bool) -> WeekResult:
    now = _now(context).date()
    end = min(start + timedelta(days=6), now) if partial else start + timedelta(days=6)
    previous_start = start - timedelta(days=7)
    goals: list[GoalResult] = []
    daily = {start + timedelta(days=offset): [0, 0] for offset in range((end - start).days + 1)}
    for goal in context.user_state.get("goals", []):
        participant = goal.get("participants", {}).get(context.user_id, {}) if isinstance(goal, dict) else {}
        outcomes = participant.get("period_outcomes", {}) if isinstance(participant, dict) else {}
        selected = _outcomes_in(outcomes, start, end)
        current_start = _date(participant.get("period_start"))
        if current_start is not None and start <= current_start <= end and not any(day == current_start for day, _ in selected):
            current = max(0, int(participant.get("current", 0) or 0))
            target = max(1, int(participant.get("target", 1) or 1))
            selected.append((current_start, {
                "completed": current >= target,
                "fulfilled": current >= target,
                "skipped": bool(participant.get("skipped", False)),
                "current": current,
                "target": target,
            }))
        previous = _outcomes_in(outcomes, previous_start, previous_start + timedelta(days=6))
        if not selected:
            continue
        fulfilled = sum(bool(item.get("fulfilled", item.get("completed", False))) for _, item in selected)
        skipped = sum(bool(item.get("skipped", False)) for _, item in selected)
        active = len(selected)
        previous_rate = (sum(bool(item.get("fulfilled", item.get("completed", False))) for _, item in previous) * 100 / len(previous)) if previous else None
        goals.append(GoalResult(str(goal.get("description", "Goal")), fulfilled, active, skipped, previous_rate))
        for when, item in selected:
            if when in daily:
                daily[when][0] += 1
                daily[when][1] += int(bool(item.get("fulfilled", item.get("completed", False))))
    active = sum(goal.active for goal in goals); fulfilled = sum(goal.fulfilled for goal in goals); skipped = sum(goal.skipped for goal in goals)
    previous_active = sum(1 for goal in context.user_state.get("goals", []) for _ in _outcomes_in(goal.get("participants", {}).get(context.user_id, {}).get("period_outcomes", {}), previous_start, previous_start + timedelta(days=6)))
    previous_done = sum(int(bool(item.get("fulfilled", item.get("completed", False)))) for goal in context.user_state.get("goals", []) for _, item in _outcomes_in(goal.get("participants", {}).get(context.user_id, {}).get("period_outcomes", {}), previous_start, previous_start + timedelta(days=6)))
    return WeekResult(start, end, partial, fulfilled, active, skipped, tuple((day, *values) for day, values in daily.items()), tuple(goals), previous_done * 100 / previous_active if previous_active else None)


def _outcomes_in(outcomes: Any, start: date, end: date) -> list[tuple[date, dict[str, Any]]]:
    result = []
    for key, value in outcomes.items() if isinstance(outcomes, dict) else ():
        when = _date(key)
        if when is not None and start <= when <= end and isinstance(value, dict): result.append((when, value))
    return result

def _week_start(value: date) -> date: return value - timedelta(days=value.weekday())
def _date(value: Any) -> date | None:
    try: return datetime.fromisoformat(str(value)).date()
    except ValueError: return None
def _now(context: AssistantContext) -> datetime:
    value = context.now or datetime.now(timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
def _headline_text(result: WeekResult) -> str:
    if result.partial: return "You’re currently on a strong pace." if result.rate >= 75 else "The week is still open." if result.rate >= 50 else "There is still room to change the story."
    return "That was a very strong week." if result.rate >= 90 else "That was a solid week." if result.rate >= 75 else "More worked than didn’t." if result.rate >= 50 else "The week was uneven." if result.rate >= 25 else "The targets had a difficult week."
def _closing(result: WeekResult) -> tuple[AssistantLine, ...]:
    if result.partial: return (AssistantLine("The story is not finished yet."), AssistantLine("Today can still change the result.", typing_delay=0.6))
    if result.rate >= 90: return (AssistantLine("That was a serious week."), AssistantLine("You made consistency look easy.", typing_delay=0.6))
    if result.rate < 25: return (AssistantLine("This week did not go to plan."), AssistantLine("The next one does not have to repeat it.", typing_delay=0.6))
    return (AssistantLine("Not perfect."), AssistantLine("Very steady.", typing_delay=0.6), AssistantLine("Steady is how habits become normal.", typing_delay=0.6))
