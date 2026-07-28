"""Optional insight candidates for the weekly summary story."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from src.assistant.core import AssistantCard, AssistantLine
from src.assistant.stories.weekly_summary_analysis import GoalResult, SharedGoalResult, SharedParticipantResult, WeekResult, _momentum_halves

@dataclass(frozen=True)
class AdditionalInsight:
    identifier: str
    subjects: frozenset[str]
    content: tuple[AssistantLine | AssistantCard, ...]


def _used_existing_insights(content: list[AssistantLine | AssistantCard] | tuple[AssistantLine | AssistantCard, ...]) -> tuple[set[str], set[str]]:
    """A small, explicit duplicate guard is more reliable than ranking candidates."""
    types: set[str] = set()
    subjects: set[str] = set()
    for item in content:
        if not isinstance(item, AssistantCard):
            continue
        title = item.title
        if title == "STRONGEST GOAL": types.add("strongest_goal"); subjects.add(item.value)
        elif title == "MOST IMPROVED": types.add("most_improved_goal"); subjects.add(item.value)
        elif title == "NEAR MISS": types.add("near_miss"); subjects.add(item.value)
        elif title == "NEEDS ATTENTION": types.add("weakest_goal"); subjects.add(item.value)
        elif title == "DAILY RHYTHM": types.add("daily_rhythm")
        elif title in {"CURRENT STREAK", "NEW STREAK RECORD", "STREAK UPDATE", "STREAK RECOVERY"}:
            types.add("goal_streak"); subjects.add(item.value)
        elif title == "TOTAL PROGRESS": types.add("total_progress")
        elif title in {"ACTIVE DAYS", "ACTIVE DAYS SO FAR"}: types.add("active_days")
        elif title in {"PERFECT DAYS", "PERFECT-DAY STREAK"}: types.add("perfect_days")
        elif title == "WEEKLY MOMENTUM": types.add("momentum")
        elif title == "WEEKDAY VS WEEKEND": types.add("weekday_weekend")
        elif title == "GOAL CHANGE": types.add("goal_decline"); subjects.add(item.value)
        elif title == "OVER TARGET": types.add("over_target"); subjects.add(item.value)
        elif title == "BY SCHEDULE": types.add("schedule_breakdown")
    return types, subjects


def _additional_insights(result: WeekResult, used_types: set[str], used_subjects: set[str]) -> list[AdditionalInsight]:
    """Return valid, non-overlapping optional insights in the prescribed broad order."""
    candidates: list[AdditionalInsight] = []
    record = _personal_record_insight(result)
    if record and "personal_record" not in used_types:
        candidates.append(record)
    total = _total_progress_insight(result)
    if total and "total_progress" not in used_types:
        candidates.append(total)
    perfect = _perfect_or_active_insight(result)
    if perfect and perfect.identifier not in used_types:
        candidates.append(perfect)
    momentum = _momentum_insight(result)
    weekday = _weekday_weekend_insight(result)
    if momentum:
        candidates.append(momentum)
    elif weekday:
        candidates.append(weekday)
    weekday_history = _repeated_weekday_insight(result)
    if weekday_history:
        candidates.append(weekday_history)
    decline = _goal_decline_insight(result, used_subjects)
    if decline:
        candidates.append(decline)
    over = _over_target_insight(result, used_subjects)
    if over:
        candidates.append(over)
    schedule = _schedule_breakdown_insight(result)
    if schedule:
        candidates.append(schedule)
    candidates.extend(_shared_insights(result, used_subjects))
    return candidates


def _shared_insights(result: WeekResult, used_subjects: set[str]) -> list[AdditionalInsight]:
    """One strongest, independently useful candidate for each social pattern."""
    candidates = [
        _matching_completions_insight(result),
        _shared_success_insight(result),
        _friend_comparison_insight(result),
        _shared_streak_insight(result, used_subjects),
        _group_consistency_insight(result),
        _friend_recovery_insight(result),
        _reaction_insight(result),
    ]
    return [candidate for candidate in candidates if candidate is not None]


def _period_map(participant: SharedParticipantResult) -> dict[date, tuple[bool, bool, int, int]]:
    return {when: (done, active, current, target) for when, done, active, current, target in participant.periods}


def _matching_completions_insight(result: WeekResult) -> AdditionalInsight | None:
    options = []
    for goal in result.shared_goals:
        user = _period_map(goal.user)
        for friend in goal.participants[1:]:
            friend_periods = _period_map(friend)
            comparable = sorted(set(user) & set(friend_periods))
            matching = [when for when in comparable if user[when][0] and friend_periods[when][0]]
            if matching and (len(matching) >= 2 or len(matching) == len(comparable)):
                options.append((len(matching), len(matching) / len(comparable), max(matching), len(comparable), goal, friend))
    if not options:
        return None
    count, ratio, recent, active, goal, friend = max(options, key=lambda item: item[:4])
    label = "the weekly target" if goal.is_weekly else f"{count} of {active} periods"
    text = "You finished the week together." if goal.is_weekly else f"You matched each other on {count} day{'s' if count != 1 else ''}."
    return AdditionalInsight(f"shared_momentum:{goal.identifier}:{friend.user_id}", frozenset({goal.name}), (
        AssistantLine(f"You and {friend.name} moved together."),
        AssistantCard("SHARED MOMENTUM", goal.name, f"With {friend.name}\nBoth completed {label}"),
        AssistantLine(text),
    ))


def _shared_success_insight(result: WeekResult) -> AdditionalInsight | None:
    options = []
    for goal in result.shared_goals:
        maps = [_period_map(participant) for participant in goal.participants]
        for when in set.intersection(*(set(periods) for periods in maps)) if maps else set():
            if all(periods[when][0] for periods in maps):
                user_map = maps[0]
                prior_miss = any(not done for day, (done, *_rest) in user_map.items() if day < when)
                options.append((len(maps), when, int(prior_miss), goal))
    if not options:
        return None
    people, when, recovered, goal = max(options, key=lambda item: (item[0], item[1], item[2], _shared_goal_activity(item[3])))
    names = [participant.name for participant in goal.participants]
    everyone = _join_names(["You", *names[1:]])
    intro = "Everyone completed the weekly goal." if goal.is_weekly else f"{when.strftime('%A')} belonged to the whole group."
    return AdditionalInsight(f"shared_success:{goal.identifier}:{when.isoformat()}", frozenset({goal.name}), (
        AssistantLine(intro),
        AssistantCard("SHARED SUCCESS", goal.name, f"{everyone}\nall completed the goal"),
        AssistantLine("Everyone reached their target that period."),
    ))


def _friend_comparison_insight(result: WeekResult) -> AdditionalInsight | None:
    eligible = [goal for goal in result.shared_goals if sum(participant.active > 0 for participant in goal.participants) >= 2]
    if not eligible:
        return None
    goal = max(eligible, key=lambda item: (_shared_goal_activity(item), len(item.participants), item.name))
    valid = [participant for participant in goal.participants if participant.active > 0]
    if goal.user not in valid or all(person.fulfilled == person.active for person in valid):
        return None
    people = [goal.user, *sorted((person for person in valid if person.user_id != goal.user.user_id), key=lambda p: (-p.fulfilled, -p.rate, p.name.casefold()))[:3]]
    if len(people) < 2:
        return None
    targets = {target for person in people for _, _, active, _, target in person.periods if active}
    equal_targets = len(targets) == 1
    rows = []
    for index, person in enumerate(people):
        label = "You" if index == 0 else person.name
        if equal_targets:
            current = sum(current for _, _, active, current, _ in person.periods if active)
            target = sum(target for _, _, active, _, target in person.periods if active)
            detail = f"{current:,} / {target:,} · {person.fulfilled} of {person.active} periods · {person.rate:.0f}%"
        else:
            detail = f"{person.progress_rate:.0f}% of personal target · {person.fulfilled} of {person.active} periods"
        rows.append((label, detail))
    leader = max(people, key=lambda person: (person.fulfilled, person.rate, person.name.casefold()))
    text = "Your result led the group this week." if leader.user_id == goal.user.user_id else f"{leader.name} had the strongest completion rate."
    return AdditionalInsight(f"friend_comparison:{goal.identifier}", frozenset({goal.name}), (
        AssistantLine("Here’s how the shared goal moved."),
        AssistantCard("SHARED GOAL", goal.name, "", tuple(rows)),
        AssistantLine(text),
    ))


def _shared_streak_insight(result: WeekResult, used_subjects: set[str]) -> AdditionalInsight | None:
    options = []
    for goal in result.shared_goals:
        if goal.name in used_subjects:
            continue
        minimum = 2 if goal.is_weekly else 3
        people = [person for person in goal.participants if person.streak.symbols]
        if len(people) >= 2 and max(person.streak.value for person in people) >= minimum:
            options.append((max(person.streak.value for person in people), _shared_goal_activity(goal), goal))
    if not options:
        return None
    _, _, goal = max(options, key=lambda item: item[:2])
    people = [person for person in goal.participants if person.streak.symbols]
    rows = tuple(("You" if person.user_id == goal.user.user_id else person.name, person.streak.label) for person in people[:4])
    leader = max(people, key=lambda person: (person.streak.value, person.name.casefold()))
    text = "Your streak is currently the longest." if leader.user_id == goal.user.user_id else f"{leader.name} has the longest streak right now."
    return AdditionalInsight(f"shared_streak:{goal.identifier}", frozenset({goal.name}), (
        AssistantLine("The group’s streaks tell another story."),
        AssistantCard("SHARED STREAKS", goal.name, "", rows),
        AssistantLine(text),
    ))


def _group_consistency_insight(result: WeekResult) -> AdditionalInsight | None:
    options = []
    for goal in result.shared_goals:
        maps = [_period_map(person) for person in goal.participants]
        comparable = set.intersection(*(set(periods) for periods in maps)) if maps else set()
        if not comparable:
            continue
        everyone = sum(all(periods[when][0] for periods in maps) for when in comparable)
        half = sum(sum(periods[when][0] for periods in maps) * 2 >= len(maps) for when in comparable)
        average = sum(person.rate for person in goal.participants) / len(goal.participants)
        together = everyone / len(comparable)
        eligible = (len(goal.participants) >= 3 or (len(goal.participants) == 2 and together >= .6)) and (half >= 2 or everyone >= 2)
        if eligible:
            options.append((everyone, half, average, len(comparable), goal))
    if not options:
        return None
    everyone, half, average, total, goal = max(options, key=lambda item: item[:4])
    unit = "weeks" if goal.is_weekly else "days"
    rows = ((f"{everyone} of {total} {unit}", "everyone completed"), (f"{half} of {total} {unit}", "at least half completed"))
    return AdditionalInsight(f"group_consistency:{goal.identifier}", frozenset({goal.name}), (
        AssistantLine("This shared goal stayed active across the group."),
        AssistantCard("GROUP CONSISTENCY", goal.name, "", rows),
        AssistantLine("The group kept showing up for this goal."),
    ))


def _friend_recovery_insight(result: WeekResult) -> AdditionalInsight | None:
    options = []
    for goal in result.shared_goals:
        user = _period_map(goal.user)
        for missed in sorted(day for day, values in user.items() if values[1] and not values[0]):
            recovered = next((day for day in sorted(user) if day > missed and user[day][0]), None)
            if recovered is None:
                continue
            for friend in goal.participants[1:]:
                friend_map = _period_map(friend)
                support = next((day for day in (recovered, missed) if friend_map.get(day, (False,))[0]), None)
                if support:
                    options.append((recovered, missed, goal, friend, support))
    if not options:
        return None
    recovered, missed, goal, friend, support = max(options, key=lambda item: item[0])
    rows = ((missed.strftime("%A"), "missed"), (support.strftime("%A"), f"{friend.name} completed"), (recovered.strftime("%A"), "you completed"))
    return AdditionalInsight(f"shared_recovery:{goal.identifier}:{recovered.isoformat()}:{friend.user_id}", frozenset({goal.name}), (
        AssistantLine(f"You rejoined the group after {missed.strftime('%A')}"),
        AssistantCard("SHARED RECOVERY", goal.name, "", rows),
        AssistantLine("You were back one period later." if (recovered - missed).days == (7 if goal.is_weekly else 1) else "You found your way back during the week."),
    ))


def _reaction_insight(result: WeekResult) -> AdditionalInsight | None:
    reactions = [reaction for goal in result.shared_goals for reaction in goal.reactions]
    if not reactions:
        return None
    counts: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for sender_id, sender_name, emote, _ in reactions:
        counts.setdefault(sender_id, []).append(emote)
        names[sender_id] = sender_name
    ordered = sorted(counts, key=lambda sender: (-len(counts[sender]), names[sender].casefold()))
    rows = tuple((names[sender], f"{len(counts[sender])}" + (f" · {' '.join(counts[sender][:3])}" if counts[sender] else "")) for sender in ordered[:4])
    total = len(reactions)
    if len(ordered) == 1:
        sender = ordered[0]
        detail = f"{names[sender]} reacted\nto {total} completion{'s' if total != 1 else ''}"
        text = f"{names[sender]} noticed your progress."
    else:
        detail = f"{total} reactions received"
        text = "Your friends noticed the week."
    return AdditionalInsight("friend_support:" + ":".join(ordered), frozenset(), (
        AssistantLine("Here’s who cheered you on."),
        AssistantCard("FRIEND SUPPORT", detail, "", rows),
        AssistantLine(text),
    ))


def _shared_goal_activity(goal: SharedGoalResult) -> int:
    return sum(participant.active for participant in goal.participants)


def _join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return names[0] if names else ""
    if len(names) == 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def _personal_record_insight(result: WeekResult) -> AdditionalInsight | None:
    """A conservative completion-rate record over retained complete weekly data."""
    history = [(start, done, active) for start, done, active in result.history if active >= 3]
    if not history or result.active < 3:
        return None
    best = max(done * 100 / active for _, done, active in history)
    if result.rate < best:
        return None
    window = len(history) + 1
    period = f"across {window} recorded weeks" if window != 12 else "in the last 12 weeks"
    matched = abs(result.rate - best) < .01
    text = "You matched your best recorded week." if matched else "This was your strongest recorded week in that period."
    return AdditionalInsight("personal_record", frozenset(), (AssistantLine("This week set a new mark."), AssistantCard("PERSONAL RECORD", "Highest weekly completion", f"{period}\n{result.rate:.0f}%", progress=result.rate), AssistantLine(text)))


def _total_progress_insight(result: WeekResult) -> AdditionalInsight | None:
    rows = [row for row in result.period_data if row[2] and row[4] > 0]
    if not rows:
        return None
    # Raw totals are meaningful only when every target uses the same unit/value scale.
    targets = {target for _, _, _, _, target, _, _ in rows}
    current = sum(value for _, _, _, value, _, _, _ in rows)
    progress = sum(min(1, value / target) for _, _, _, value, target, _, _ in rows) * 100 / len(rows)
    if abs(progress - result.rate) < 3:
        return None
    if len(targets) == 1:
        card = AssistantCard("TOTAL PROGRESS", f"{current:,}", "Across recorded goal periods", progress=progress)
        text = "That is the work behind the score."
    else:
        card = AssistantCard("TOTAL PROGRESS", f"{progress:.0f}%", "of combined targets reached", progress=progress)
        text = "The completion rate does not show all of that effort."
    return AdditionalInsight("total_progress", frozenset(), (AssistantLine("Here is what the week added up to."), card, AssistantLine(text)))


def _perfect_or_active_insight(result: WeekResult) -> AdditionalInsight | None:
    perfect_dates = [day for day, active, done in result.daily if active and done == active]
    active_dates = list(result.progress_days)
    streak = _longest_date_streak(perfect_dates)
    if len(streak) >= 2:
        label = _date_span(streak)
        return AdditionalInsight("perfect_days", frozenset(), (AssistantLine("You built a complete-day streak."), AssistantCard("PERFECT-DAY STREAK", f"{len(streak)} days", label), AssistantLine("Every active goal was completed on those days.")))
    active_streak = _longest_date_streak(active_dates)
    if len(active_streak) >= 3 and len(active_streak) != len(active_dates):
        return AdditionalInsight("active_day_streak", frozenset(), (AssistantLine("You kept returning."), AssistantCard("ACTIVE-DAY STREAK", f"{len(active_streak)} days", _date_span(active_streak)), AssistantLine("The week was not perfect, but it stayed active.")))
    denominator = (result.end - result.start).days + 1
    if len(active_dates) >= 2:
        title = "ACTIVE DAYS SO FAR" if result.partial else "ACTIVE DAYS"
        return AdditionalInsight("active_days", frozenset(), (AssistantLine("The score hides one useful fact."), AssistantCard(title, f"{len(active_dates)} of {denominator} days", "At least one goal completed"), AssistantLine("You made progress on almost every day.")))
    return None


def _momentum_insight(result: WeekResult) -> AdditionalInsight | None:
    if result.partial and result.end.weekday() < 3:
        return None
    first, second = _momentum_halves(result)
    if first is None or second is None:
        return None
    difference = (second - first) * 100
    if abs(difference) < 5:
        return None
    label = "The week improved as it went." if difference > 0 else "You started strongly."
    ending = "You finished much stronger than you started." if difference >= 15 else "The rhythm became harder to hold later." if difference <= -15 else "The change was noticeable but not dramatic."
    return AdditionalInsight("momentum", frozenset(), (AssistantLine(label), AssistantCard("WEEKLY MOMENTUM", f"{difference:+.0f} percentage points", "", (("Monday–Wednesday", f"{first:.0%}"), ("Thursday onward", f"{second:.0%}"))), AssistantLine(ending)))


def _weekday_weekend_insight(result: WeekResult) -> AdditionalInsight | None:
    if result.partial or result.end.weekday() < 6:
        return None
    weekday = [row for row in result.period_data if row[2] and row[0].weekday() < 5]
    weekend = [row for row in result.period_data if row[2] and row[0].weekday() >= 5]
    if len(weekday) < 3 or len(weekend) < 2:
        return None
    weekday_rate = sum(row[1] for row in weekday) * 100 / len(weekday)
    weekend_rate = sum(row[1] for row in weekend) * 100 / len(weekend)
    diff = weekend_rate - weekday_rate
    if abs(diff) < 20:
        return None
    text = "Your strongest rhythm appeared on Saturday and Sunday." if diff > 0 else "Most of your completed periods happened during the week."
    return AdditionalInsight("weekday_weekend", frozenset(), (AssistantLine("Your rhythm changed at the weekend."), AssistantCard("WEEKDAY VS WEEKEND", f"{diff:+.0f} percentage points", "", (("Weekdays", f"{weekday_rate:.0f}%"), ("Weekend", f"{weekend_rate:.0f}%"))), AssistantLine(text)))


def _goal_decline_insight(result: WeekResult, used_subjects: set[str]) -> AdditionalInsight | None:
    candidates = [goal for goal in result.goals if goal.previous_rate is not None and goal.rate - goal.previous_rate <= -20 and goal.name not in used_subjects]
    goal = min(candidates, key=lambda item: item.rate - (item.previous_rate or 0), default=None)
    if goal is None:
        return None
    diff = goal.rate - (goal.previous_rate or 0)
    return AdditionalInsight("goal_decline", frozenset({goal.name}), (AssistantLine("One goal changed in the other direction."), AssistantCard("GOAL CHANGE", goal.name, "", (("Previous week", f"{goal.previous_rate:.0f}%"), ("Selected week", f"{goal.rate:.0f}%"), ("Change", f"{diff:+.0f} percentage points"))), AssistantLine(f"{goal.name} had a much harder week.")))


def _over_target_insight(result: WeekResult, used_subjects: set[str]) -> AdditionalInsight | None:
    by_goal: dict[str, list[tuple[date, int, int]]] = {}
    for when, _, active, current, target, name, _ in result.period_data:
        if active and current > target:
            by_goal.setdefault(name, []).append((when, current, target))
    eligible = [(name, periods) for name, periods in by_goal.items() if name not in used_subjects and (len(periods) >= 2 or max(cur / target for _, cur, target in periods) >= 1.25)]
    if not eligible:
        return None
    name, periods = max(eligible, key=lambda item: (len(item[1]), max(cur / target for _, cur, target in item[1])))
    peak = max(cur * 100 / target for _, cur, target in periods)
    return AdditionalInsight("over_target", frozenset({name}), (AssistantLine("You went beyond the target more than once."), AssistantCard("OVER TARGET", name, f"{len(periods)} periods above target\nHighest result: {peak:.0f}%"), AssistantLine(f"{name} exceeded its target on {len(periods)} periods.")))


def _schedule_breakdown_insight(result: WeekResult) -> AdditionalInsight | None:
    groups: dict[str, list[tuple[date, bool, bool, int, int, str, str]]] = {}
    for row in result.period_data:
        schedule = row[6]
        label = "Weekly goals" if schedule in {"weekly", "weekly_x_per_month"} else "Flexible goals" if "x_per" in schedule or "allowance" in schedule else "Daily goals"
        if row[2]: groups.setdefault(label, []).append(row)
    rates = {name: sum(row[1] for row in rows) * 100 / len(rows) for name, rows in groups.items() if rows}
    if len(rates) < 2 or max(rates.values()) - min(rates.values()) < 20:
        return None
    strongest = max(rates, key=rates.get)
    rows = tuple((name, f"{rate:.0f}%") for name, rate in sorted(rates.items()))
    return AdditionalInsight("schedule_breakdown", frozenset(), (AssistantLine("Your goal types behaved differently."), AssistantCard("BY SCHEDULE", "", "", rows), AssistantLine(f"{strongest} were your most reliable group.")))


def _repeated_weekday_insight(result: WeekResult) -> AdditionalInsight | None:
    """Use only repeated retained observations, never a single exceptional day."""
    recent = [row for row in result.historical_daily if (result.start - row[0]).days <= 56 and row[2]]
    if len(recent) < 12:
        return None
    overall = sum(done for _, done, _ in recent) * 100 / len(recent)
    groups: dict[int, list[tuple[date, bool, bool]]] = {}
    for row in recent: groups.setdefault(row[0].weekday(), []).append(row)
    eligible = [
        (weekday, rows) for weekday, rows in groups.items()
        if len({day for day, _, _ in rows}) >= 4 and len(rows) >= 3
    ]
    if not eligible:
        return None
    weekday, rows = max(eligible, key=lambda pair: abs(sum(done for _, done, _ in pair[1]) * 100 / len(pair[1]) - overall))
    rate = sum(done for _, done, _ in rows) * 100 / len(rows)
    if abs(rate - overall) < 15:
        return None
    name = (result.start + timedelta(days=weekday)).strftime("%A")
    text = f"{name} has become your most reliable day." if rate > overall else f"{name} has been your most difficult weekday recently."
    return AdditionalInsight("weekday_pattern", frozenset({name}), (AssistantLine(f"{name} may be becoming a pattern."), AssistantCard(f"{name.upper()} PATTERN", f"Average completion     {rate:.0f}%", f"Last {len(rows)} {name}s", (("Overall average", f"{overall:.0f}%"),)), AssistantLine(text)))


def _longest_date_streak(days: list[date]) -> list[date]:
    best: list[date] = []; current: list[date] = []
    for day in sorted(set(days)):
        current = current + [day] if current and (day - current[-1]).days == 1 else [day]
        if len(current) > len(best): best = current
    return best


def _date_span(days: list[date]) -> str:
    if len(days) == 1: return days[0].strftime("%A")
    return f"{days[0].strftime('%A')}–{days[-1].strftime('%A')}"

