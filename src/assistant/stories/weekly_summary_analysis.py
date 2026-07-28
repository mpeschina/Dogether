"""Data analysis for the weekly summary story."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from src.assistant.core import AssistantContext
from src.db.persistence_helpers import APP_ZONE

@dataclass(frozen=True)
class GoalResult:
    name: str
    fulfilled: int
    active: int
    skipped: int
    previous_rate: float | None
    streak: "StreakResult"
    near_misses: tuple[tuple[date, float, int, int], ...] = ()
    schedule_class: str = "daily"
    periods: tuple[tuple[date, bool, int, int], ...] = ()

    @property
    def rate(self) -> float:
        return self.fulfilled * 100 / self.active if self.active else 0

    @property
    def is_weekly(self) -> bool:
        return self.schedule_class in {"weekly", "weekly_x_per_month"}


@dataclass(frozen=True)
class SharedParticipantResult:
    user_id: str
    name: str
    fulfilled: int
    active: int
    skipped: int
    progress_rate: float
    streak: "StreakResult"
    periods: tuple[tuple[date, bool, bool, int, int], ...]

    @property
    def rate(self) -> float:
        return self.fulfilled * 100 / self.active if self.active else 0


@dataclass(frozen=True)
class SharedGoalResult:
    identifier: str
    name: str
    schedule_class: str
    participants: tuple[SharedParticipantResult, ...]
    reactions: tuple[tuple[str, str, str, datetime], ...] = ()

    @property
    def user(self) -> SharedParticipantResult:
        return self.participants[0]

    @property
    def is_weekly(self) -> bool:
        return self.schedule_class in {"weekly", "weekly_x_per_month"}


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
    previous_active: int = 0
    previous_fulfilled: int = 0
    progress_days: tuple[date, ...] = ()
    # Each row is (date, fulfilled, active, current, target, goal name, schedule).
    period_data: tuple[tuple[date, bool, bool, int, int, str, str], ...] = ()
    history: tuple[tuple[date, int, int], ...] = ()
    historical_daily: tuple[tuple[date, bool, bool], ...] = ()
    shared_goals: tuple[SharedGoalResult, ...] = ()

    @property
    def rate(self) -> float:
        return self.fulfilled * 100 / self.active if self.active else 0

    @property
    def perfect_days(self) -> int:
        return sum(active > 0 and done == active for _, active, done in self.daily)

    @property
    def active_days(self) -> int:
        return len(self.progress_days)

    @property
    def near_misses(self) -> tuple[tuple[GoalResult, date, float, int, int], ...]:
        return tuple(
            (goal, when, percent, current, target)
            for goal in self.goals
            for when, percent, current, target in goal.near_misses
        )


def _analyse(context: AssistantContext, start: date, partial: bool) -> WeekResult:
    now = _now(context).date()
    end = min(start + timedelta(days=6), now) if partial else start + timedelta(days=6)
    previous_start = start - timedelta(days=7)
    goals: list[GoalResult] = []
    daily = {start + timedelta(days=offset): [0, 0] for offset in range((end - start).days + 1)}
    progress_days: set[date] = set()
    period_data: list[tuple[date, bool, bool, int, int, str, str]] = []
    historical: dict[date, list[int]] = {}
    historical_daily: list[tuple[date, bool, bool]] = []
    shared_goals: list[SharedGoalResult] = []
    previous_active = 0
    previous_done = 0
    for goal in context.user_state.get("goals", []):
        participant = goal.get("participants", {}).get(context.user_id, {}) if isinstance(goal, dict) else {}
        outcomes = participant.get("period_outcomes", {}) if isinstance(participant, dict) else {}
        # Retained history can be incomplete; only weeks with enough closed
        # periods are later eligible for a record.
        if isinstance(outcomes, dict):
            for raw_when, raw_item in outcomes.items():
                when = _date(raw_when)
                if when is None or when >= start or not isinstance(raw_item, dict) or _is_excused(raw_item):
                    continue
                week = _week_start(when)
                bucket = historical.setdefault(week, [0, 0])
                bucket[0] += int(_is_completed(raw_item))
                bucket[1] += 1
                historical_daily.append((when, _is_completed(raw_item), True))
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
        goal_previous_active = sum(not _is_excused(item) for _, item in previous)
        goal_previous_done = sum(_is_completed(item) for _, item in previous)
        previous_active += goal_previous_active
        previous_done += goal_previous_done
        if not selected:
            continue
        fulfilled = sum(_is_completed(item) for _, item in selected)
        skipped = sum(_is_excused(item) for _, item in selected)
        active = sum(not _is_excused(item) for _, item in selected)
        previous_rate = (
            goal_previous_done * 100 / goal_previous_active
            if goal_previous_active
            else None
        )
        near_misses = tuple(
            (when, percent, current, target)
            for when, item in selected
            if not _is_excused(item)
            and not _is_completed(item)
            and (progress := _progress(item)) is not None
            and 75 <= (percent := progress[0]) < 100
            for current, target in (progress[1:],)
        )
        streak = _analyse_streak(goal, participant, start, end, now)
        periods = tuple(
            (when, _is_completed(item), *( _period_amounts(item) ))
            for when, item in selected if not _is_excused(item)
        )
        goals.append(
            GoalResult(
                str(goal.get("description", "Goal")),
                fulfilled,
                active,
                skipped,
                previous_rate,
                streak,
                near_misses,
                str(goal.get("schedule_class", "daily")),
                periods,
            )
        )
        weekly = str(goal.get("schedule_class", "daily")) in {
            "weekly",
            "weekly_x_per_month",
        }
        for when, item in selected:
            current, target = _period_amounts(item)
            period_data.append((
                when, _is_completed(item), not _is_excused(item),
                current, target,
                str(goal.get("description", "Goal")), str(goal.get("schedule_class", "daily")),
            ))
            # A weekly outcome is keyed by the Monday when its period began,
            # not by the day it was completed. Do not invent a daily event.
            if not weekly and when in daily and not _is_excused(item):
                daily[when][0] += 1
                daily[when][1] += int(_is_completed(item))
                if _has_progress(item):
                    progress_days.add(when)
        shared = _analyse_shared_goal(context, goal, start, end, now)
        if shared is not None:
            shared_goals.append(shared)
    active = sum(goal.active for goal in goals)
    fulfilled = sum(goal.fulfilled for goal in goals)
    skipped = sum(goal.skipped for goal in goals)
    return WeekResult(
        start=start,
        end=end,
        partial=partial,
        fulfilled=fulfilled,
        active=active,
        skipped=skipped,
        daily=tuple((day, *values) for day, values in daily.items()),
        goals=tuple(goals),
        previous_rate=previous_done * 100 / previous_active if previous_active else None,
        previous_active=previous_active,
        previous_fulfilled=previous_done,
        progress_days=tuple(sorted(progress_days)),
        period_data=tuple(period_data),
        history=tuple((week, values[0], values[1]) for week, values in sorted(historical.items())),
        historical_daily=tuple(historical_daily),
        shared_goals=tuple(shared_goals),
    )


def _analyse_shared_goal(
    context: AssistantContext,
    goal: dict[str, Any],
    start: date,
    end: date,
    now: date,
) -> SharedGoalResult | None:
    """Extract only active, currently approved participants for social insights."""
    participants = goal.get("participants", {})
    if not isinstance(participants, dict) or context.user_id not in participants:
        return None
    profiles = context.user_state.get("friend_profiles", {})
    profiles = profiles if isinstance(profiles, dict) else {}
    visible_ids = [context.user_id]
    visible_ids.extend(
        participant_id
        for participant_id, participant in participants.items()
        if participant_id != context.user_id
        and participant_id in profiles
        and isinstance(participant, dict)
        and not participant.get("left_at")
    )
    if len(visible_ids) < 2:
        return None
    shared_people: list[SharedParticipantResult] = []
    for participant_id in visible_ids:
        participant = participants.get(participant_id, {})
        if not isinstance(participant, dict):
            continue
        selected = _participant_selected_outcomes(participant, start, end)
        active = sum(not _is_excused(item) for _, item in selected)
        fulfilled = sum(_is_completed(item) for _, item in selected)
        skipped = sum(_is_excused(item) for _, item in selected)
        progress_values = [_progress(item)[0] for _, item in selected if not _is_excused(item) and _progress(item) is not None]
        profile = context.current_user if participant_id == context.user_id else profiles.get(participant_id, {})
        name = str(profile.get("name") or profile.get("email") or participant_id) if isinstance(profile, dict) else participant_id
        shared_people.append(SharedParticipantResult(
            participant_id, name, fulfilled, active, skipped,
            sum(progress_values) / len(progress_values) if progress_values else 0,
            _analyse_streak(goal, participant, start, end, now),
            tuple((when, _is_completed(item), not _is_excused(item), *_period_amounts(item)) for when, item in selected),
        ))
    # The user must have data and at least one approved friend must have data.
    if len(shared_people) < 2 or shared_people[0].user_id != context.user_id or not shared_people[0].periods:
        return None
    reactions = _shared_reactions(goal, context.user_id, profiles, start, end)
    return SharedGoalResult(
        str(goal.get("id") or goal.get("description", "goal")),
        str(goal.get("description", "Goal")),
        str(goal.get("schedule_class", "daily")),
        tuple(shared_people),
        reactions,
    )


def _participant_selected_outcomes(participant: dict[str, Any], start: date, end: date) -> list[tuple[date, dict[str, Any]]]:
    outcomes = participant.get("period_outcomes", {})
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
    return sorted(selected, key=lambda item: item[0])


def _shared_reactions(
    goal: dict[str, Any],
    user_id: str,
    profiles: dict[str, Any],
    start: date,
    end: date,
) -> tuple[tuple[str, str, str, datetime], ...]:
    participant = goal.get("participants", {}).get(user_id, {})
    reactions = participant.get("completion_reactions", {}) if isinstance(participant, dict) else {}
    result = []
    if not isinstance(reactions, dict):
        return ()
    for period_reactions in reactions.values():
        if not isinstance(period_reactions, dict):
            continue
        for sender_id, reaction in period_reactions.items():
            if sender_id not in profiles or not isinstance(reaction, dict):
                continue
            reacted_at = _datetime(reaction.get("reacted_at"))
            if reacted_at is None:
                continue
            local_reacted_at = reacted_at.replace(tzinfo=APP_ZONE) if reacted_at.tzinfo is None else reacted_at.astimezone(APP_ZONE)
            if not (start <= local_reacted_at.date() <= end):
                continue
            profile = profiles[sender_id]
            name = str(profile.get("name") or profile.get("email") or sender_id) if isinstance(profile, dict) else sender_id
            result.append((sender_id, name, str(reaction.get("emote", "")), local_reacted_at))
    return tuple(result)


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


def _outcomes_in(outcomes: Any, start: date, end: date) -> list[tuple[date, dict[str, Any]]]:
    result = []
    for key, value in outcomes.items() if isinstance(outcomes, dict) else ():
        when = _date(key)
        if when is not None and start <= when <= end and isinstance(value, dict): result.append((when, value))
    return result


def _is_completed(outcome: dict[str, Any]) -> bool:
    """Return actual target completion, not aggregate allowance fulfilment."""
    if bool(outcome.get("skipped", False)):
        return False
    return bool(outcome.get("completed", outcome.get("fulfilled", False)))


def _is_excused(outcome: dict[str, Any]) -> bool:
    """A valid allowance is neutral; an unfulfilled skip remains incomplete."""
    return (
        bool(outcome.get("skipped", False))
        and bool(outcome.get("fulfilled", False))
        and not bool(outcome.get("completed", False))
    )


def _progress(outcome: dict[str, Any]) -> tuple[float, int, int] | None:
    try:
        current = max(0, int(outcome.get("current", 0) or 0))
        target = max(1, int(outcome.get("target", 1) or 1))
        percent = float(outcome.get("percent", current * 100 / target))
    except (TypeError, ValueError):
        return None
    return max(0.0, percent), current, target


def _period_amounts(outcome: dict[str, Any]) -> tuple[int, int]:
    progress = _progress(outcome)
    if progress is None:
        return (1, 1) if _is_completed(outcome) else (0, 1)
    _, current, target = progress
    # Binary outcomes often omit measurements.  A completion still represents
    # one target reached; do not turn it into zero effort in combined progress.
    if _is_completed(outcome) and current == 0:
        return target, target
    return current, target


def _has_progress(outcome: dict[str, Any]) -> bool:
    progress = _progress(outcome)
    return _is_completed(outcome) or bool(progress and progress[1] > 0)


def _week_start(value: date) -> date: return value - timedelta(days=value.weekday())
def _date(value: Any) -> date | None:
    try: return datetime.fromisoformat(str(value)).date()
    except ValueError: return None
def _datetime(value: Any) -> datetime | None:
    try: return datetime.fromisoformat(str(value))
    except ValueError: return None
def _now(context: AssistantContext) -> datetime:
    value = context.now or datetime.now(APP_ZONE)
    if value.tzinfo is None:
        return value.replace(tzinfo=APP_ZONE)
    return value.astimezone(APP_ZONE)
def _momentum_halves(result: WeekResult) -> tuple[float | None, float | None]:
    days = tuple((active, done) for _, active, done in result.daily)
    if len(days) < 2:
        return None, None
    split = 3 if len(days) == 7 else (len(days) + 1) // 2

    def rate(rows: tuple[tuple[int, int], ...]) -> float | None:
        active = sum(row[0] for row in rows)
        return sum(row[1] for row in rows) / active if active else None

    return rate(days[:split]), rate(days[split:])

