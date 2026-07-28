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
    streak: "StreakResult"

    @property
    def rate(self) -> float:
        return self.fulfilled * 100 / self.active if self.active else 0


@dataclass(frozen=True)
class StreakResult:
    """A goal-local streak derived from closed base periods only."""

    value: int
    unit: str
    start_value: int
    highest: int
    added: int
    started: bool
    ended: bool
    ended_value: int
    ended_on: date | None
    restarted: bool
    restart_delay: int | None
    valid_skips: int
    fulfilled: int
    record: bool
    previous_best: int | None
    symbols: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.value} {self.unit}" if self.value else "No current streak"

    @property
    def has_skips(self) -> bool:
        return self.valid_skips > 0


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
        content = (*opening, *turn.content) if turn.content else ()
        return AssistantTurn(**{**turn.__dict__, "lines": (*opening, *turn.lines), "content": content, "event_updates": {WEEK_SELECTION_EVENT_ID: {"start": start.isoformat(), "partial": partial}}, "state_story": self.story_id, "state_scene": SUMMARY_SCENE, "state_status": "active"})

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
        content: list[AssistantLine | AssistantCard] = [
            AssistantLine("First, the big picture."),
            headline,
            AssistantLine(_headline_analysis(result)),
        ]
        if result.previous_rate is not None and not result.partial:
            diff = result.rate - result.previous_rate
            content.append(AssistantCard("WEEK TO WEEK", f"{diff:+.0f} percentage points", "", (("Previous week", f"{result.previous_rate:.0f}%"), ("Selected week", f"{result.rate:.0f}%"))))
            comparison = _comparison_analysis(result, diff)
            if comparison:
                content.append(AssistantLine(comparison))
        strongest = max(result.goals, key=lambda goal: (goal.rate, goal.active))
        streak_goal = _select_streak(result.goals, strongest)
        if streak_goal:
            content.extend(_streak_content(streak_goal))
        else:
            content.extend((
                AssistantLine(f"{strongest.name} led the way."),
                AssistantCard("STRONGEST GOAL", strongest.name, f"{strongest.fulfilled} of {strongest.active} periods completed", progress=strongest.rate),
                AssistantLine(_strongest_analysis(strongest)),
            ))
        day_rows = tuple((day.strftime("%a").upper(), "—" if active == 0 else f"{round(done * 100 / active)}%") for day, active, done in result.daily)
        content.extend((
            AssistantLine("Here’s how the week moved."),
            AssistantCard("DAILY RHYTHM", "", "No active goals are shown as —", day_rows),
            AssistantLine(_rhythm_analysis(result)),
        ))
        weak = min((goal for goal in result.goals if goal.active), key=lambda goal: goal.rate)
        if weak.rate < 60 and weak != strongest:
            content.extend((
                AssistantLine("One goal needs a closer look.", typing_delay=0.6),
                AssistantCard("NEEDS ATTENTION", weak.name, f"{weak.fulfilled} of {weak.active} periods completed", progress=weak.rate),
                AssistantLine(_weak_analysis(weak)),
            ))
        content.extend(_closing(result))
        lines = tuple(item for item in content if isinstance(item, AssistantLine))
        cards = tuple(item for item in content if isinstance(item, AssistantCard))
        return AssistantTurn(self.story_id, SUMMARY_SCENE, lines=lines, cards=cards, content=tuple(content), choices=(AssistantChoice("details", "See goal details"), AssistantChoice("done", "Done")))

    def _details_turn(self, result: WeekResult) -> AssistantTurn:
        rows = tuple(
            (goal.name, f"{goal.fulfilled} / {goal.active} · {goal.rate:.0f}%\n{_detail_streak(goal.streak)}")
            for goal in sorted(result.goals, key=lambda goal: (-goal.active, -goal.rate))
        )
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
        streak = _analyse_streak(goal, participant, start, end, now)
        goals.append(GoalResult(str(goal.get("description", "Goal")), fulfilled, active, skipped, previous_rate, streak))
        for when, item in selected:
            if when in daily:
                daily[when][0] += 1
                daily[when][1] += int(bool(item.get("fulfilled", item.get("completed", False))))
    active = sum(goal.active for goal in goals); fulfilled = sum(goal.fulfilled for goal in goals); skipped = sum(goal.skipped for goal in goals)
    previous_active = sum(1 for goal in context.user_state.get("goals", []) for _ in _outcomes_in(goal.get("participants", {}).get(context.user_id, {}).get("period_outcomes", {}), previous_start, previous_start + timedelta(days=6)))
    previous_done = sum(int(bool(item.get("fulfilled", item.get("completed", False)))) for goal in context.user_state.get("goals", []) for _, item in _outcomes_in(goal.get("participants", {}).get(context.user_id, {}).get("period_outcomes", {}), previous_start, previous_start + timedelta(days=6)))
    return WeekResult(start, end, partial, fulfilled, active, skipped, tuple((day, *values) for day, values in daily.items()), tuple(goals), previous_done * 100 / previous_active if previous_active else None)


def _analyse_streak(goal: dict[str, Any], participant: dict[str, Any], start: date, end: date, today: date) -> StreakResult:
    """Derive the story data without treating the open base period as a result."""
    weekly = goal.get("schedule_class") in {"weekly", "weekly_x_per_month"}
    step = timedelta(days=7 if weekly else 1)
    unit = "weeks" if weekly else "days"
    outcomes = participant.get("period_outcomes", {}) if isinstance(participant.get("period_outcomes"), dict) else {}
    parsed = {when: value for key, value in outcomes.items() if (when := _date(key)) is not None and isinstance(value, dict)}
    current_start = _week_start(today) if weekly else today
    # Retained outcome history is finite.  Beginning at its first known period
    # avoids inventing failures before the goal was tracked.
    first = min(parsed, default=None)
    created = _date(goal.get("created_at"))
    if created is not None:
        created = _week_start(created) if weekly else created
        first = min(first, created) if first else created
    if first is None:
        return StreakResult(0, unit, 0, 0, 0, False, False, 0, None, False, None, 0, 0, False, None, ())
    first = _week_start(first) if weekly else first
    selected_start = _week_start(start) if weekly else start
    selected_end = _week_start(end) if weekly else end
    values: list[tuple[date, str]] = []
    cursor = first
    while cursor < current_start:
        outcome = parsed.get(cursor)
        if outcome is None:
            state = "failed"
        elif bool(outcome.get("fulfilled", outcome.get("completed", False))):
            state = "skip" if bool(outcome.get("skipped", False)) else "fulfilled"
        else:
            state = "failed"
        values.append((cursor, state))
        cursor += step

    before = [state for when, state in values if when < selected_start]
    start_value = _trailing_successes(before)
    running = start_value
    highest = running
    ended = False; ended_value = 0; ended_on = None; restarted = False; restart_delay = None
    failure_at: int | None = None
    added = 0
    symbols: list[str] = []
    for index, (when, state) in enumerate(values):
        if not (selected_start <= when <= selected_end):
            continue
        if state == "failed":
            if running:
                ended = True; ended_value = max(ended_value, running); ended_on = when
                failure_at = index
            running = 0
            symbols.append("○")
        else:
            if failure_at is not None and not restarted:
                restarted = True; restart_delay = index - failure_at
            running += 1; added += 1; highest = max(highest, running)
            symbols.append("×" if state == "skip" else "●")
    current = _trailing_successes([state for _, state in values])
    # An open period can be shown but never changes the derived count.
    if selected_start <= current_start <= selected_end:
        symbols.append("○")
    current_states: list[str] = []
    for _, state in reversed(values):
        if state == "failed": break
        current_states.append(state)
    current_states.reverse()
    valid_skips = sum(state == "skip" for state in current_states)
    completed = sum(state == "fulfilled" for state in current_states)
    prior_values = [state for when, state in values if when < selected_start]
    previous_best = max((_run_length(prior_values)), default=0) if prior_values else None
    # A record can be reached during the week even if a later closed period
    # resets it, so compare the week's high-water mark rather than only today.
    record = previous_best is not None and highest > previous_best
    return StreakResult(current, unit, start_value, highest, added, start_value == 0 and highest >= (2 if weekly else 3), ended, ended_value, ended_on, restarted, restart_delay, valid_skips, completed, record, previous_best, tuple(symbols))


def _trailing_successes(values: list[str]) -> int:
    total = 0
    for value in reversed(values):
        if value == "failed": break
        total += 1
    return total


def _run_length(values: list[str]) -> list[int]:
    runs: list[int] = []; current = 0
    for value in values:
        if value == "failed":
            if current: runs.append(current)
            current = 0
        else: current += 1
    if current: runs.append(current)
    return runs


def _detail_streak(streak: StreakResult) -> str:
    ended = f"{streak.ended_value}-{streak.unit[:-1]} streak ended {streak.ended_on.strftime('%A')}" if streak.ended and streak.ended_on else None
    current = streak.label
    return f"{ended}\nCurrent streak: {current}" if ended and streak.value else ended or current


def _select_streak(goals: tuple[GoalResult, ...], strongest: GoalResult) -> GoalResult | None:
    def score(goal: GoalResult) -> tuple[int, int, int, int]:
        streak = goal.streak
        milestone = streak.value in ({3, 4, 8, 12, 26, 52} if streak.unit == "weeks" else {3, 7, 14, 30, 50, 100})
        meaningful = max(streak.value, streak.ended_value, streak.highest) >= (3 if streak.unit == "weeks" else 5)
        event = streak.record or milestone or streak.started or streak.ended or streak.added > 0
        return (int(streak.record), int(milestone), int(event and meaningful), streak.added)
    candidate = max(goals, key=score)
    return candidate if score(candidate) > (0, 0, 0, 0) and (candidate == strongest or score(candidate)[:3] >= (0, 1, 0)) else None


def _streak_content(goal: GoalResult) -> tuple[AssistantLine | AssistantCard, ...]:
    streak = goal.streak
    if streak.ended and streak.restarted:
        title = "STREAK RECOVERY"; detail = f"Ended at {streak.ended_value} {streak.unit}\nRestarted after: {streak.restart_delay} period{'s' if streak.restart_delay != 1 else ''}"
        text = f"**The {streak.ended_value}-{streak.unit[:-1]} streak ended on {streak.ended_on.strftime('%A')}.**\nYou restarted it {'the next period' if streak.restart_delay == 1 else 'during the week'}."
    elif streak.record:
        title = "NEW STREAK RECORD"; detail = f"Previous best: {streak.previous_best} {streak.unit}"
        text = f"**{goal.name} reached a new record.**\nYou added {streak.added} successful {streak.unit} during the analysed week."
    elif streak.ended:
        title = "STREAK UPDATE"; detail = f"Ended at {streak.ended_value} {streak.unit}\nCurrent streak: {streak.value}"
        text = f"**The streak stopped at {streak.ended_value} {streak.unit}.**\nThose successful {streak.unit} still happened."
    else:
        title = "CURRENT STREAK"; detail = f"This week: +{streak.added} {streak.unit}"
        if streak.has_skips: detail += f"\n{streak.fulfilled} completed · {streak.valid_skips} valid skips"
        text = (f"**{streak.value}-{streak.unit[:-1]} streak.**\nEvery period was completed or validly skipped." if streak.has_skips else f"**The streak reached {streak.value} {streak.unit}.**\nThis week kept it moving.")
    return (AssistantLine(f"{goal.name} kept its rhythm."), AssistantCard(title, goal.name, f"{streak.label}\n{detail}", (("Recent", " ".join(streak.symbols)),)), AssistantLine(text))


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


def _headline_analysis(result: WeekResult) -> str:
    headline = _headline_text(result)
    label = "so far" if result.partial else "finished at"
    return f"**{headline}**\nYou completed **{result.fulfilled} of {result.active}** active goal periods.\nThe week {label} **{result.rate:.0f}%**."


def _comparison_analysis(result: WeekResult, diff: float) -> str:
    if diff >= 5:
        return f"**A clear step forward.**\nCompletion increased by **{diff:.0f} percentage points**\nfrom the week before."
    if diff <= -5:
        return f"**The result dropped this week.**\nCompletion fell by **{abs(diff):.0f} percentage points**\nfrom the week before."
    return "**Almost the same result.**\nThe score barely moved,\nbut the daily rhythm tells the fuller story."


def _strongest_analysis(goal: GoalResult) -> str:
    if goal.rate >= 100:
        return f"**Every relevant period was completed.**\n**{goal.name}** did not miss once."
    return f"**Your steadiest goal this week.**\n**{goal.name}** completed **{goal.fulfilled} of {goal.active}** periods."


def _rhythm_analysis(result: WeekResult) -> str:
    active_days = [(day, done / active) for day, active, done in result.daily if active]
    if not active_days:
        return "**The rhythm is still taking shape.**\nThere is more of the week to fill in."
    best_day, best_rate = max(active_days, key=lambda item: item[1])
    worst_day, worst_rate = min(active_days, key=lambda item: item[1])
    if best_rate - worst_rate < .2:
        return "**Your progress was fairly steady.**\nThere was no sharp inactive gap,\nand most days contributed something."
    return f"**{best_day.strftime('%A')} was strongest.**\n{worst_day.strftime('%A')} slowed things down,\nbut the rest of the week recovered."


def _weak_analysis(goal: GoalResult) -> str:
    return f"**{goal.name} had the hardest week.**\nIt completed **{goal.fulfilled} of {goal.active}** periods\nand needs a little more momentum."


def _closing(result: WeekResult) -> tuple[AssistantLine, ...]:
    if result.partial: return (AssistantLine("**The story is not finished yet.**\n\nToday can still change the result.", typing_delay=0.6),)
    if result.rate >= 90: return (AssistantLine("**That was a serious week.**\n\nYou made consistency look easy.", typing_delay=0.6),)
    if result.rate < 25: return (AssistantLine("**This week did not go to plan.**\n\nThe next one does not have to repeat it.", typing_delay=0.6),)
    return (AssistantLine("**Not perfect. Very steady.**\n\nAnd steady is how habits\nbecome normal.", typing_delay=0.6),)
