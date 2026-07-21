"""Shared persistence constants and domain helpers for Dogether."""
from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo


APP_ZONE = ZoneInfo("Europe/Berlin")
UTC = timezone.utc
ACTIVITY_DAYS_REPAIR_VERSION = 1
SCHEDULES = {
    "daily": {"label": "Daily", "base": "day", "required_periods": 1, "aggregate": "day"},
    "weekly": {"label": "Weekly", "base": "week", "required_periods": 1, "aggregate": "week"},
    "daily_x_per_week": {
        "label": "Daily with X per week",
        "base": "day",
        "required_periods": 5,
        "aggregate": "week",
    },
    "weekly_x_per_month": {
        "label": "Weekly with X per month",
        "base": "week",
        "required_periods": 3,
        "aggregate": "month",
    },
}
STANDARD_REACTION_EMOTES = ["👍", "🎉", "🔥", "👏", "💪", "❤️"]
REACTION_EMOTES = [
    *STANDARD_REACTION_EMOTES,
    "😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣", "😊", "😇", "🙂", "🙃", "😉", "😍", "😘", "😜", "🤩", "🥳",
    "😎", "🥹", "😮", "😱", "😤", "😭", "🤯", "🤝", "🙌", "🫶", "👌", "✌️", "🤞", "🙏", "💯", "⭐", "✨", "⚡",
    "☀️", "🌈", "🌟", "🏆", "🥇", "🏅", "🎯", "🚀", "💎", "🌻", "🌸", "🍀", "🍕", "🍰", "☕", "🎵", "🎁", "✅",
]


def _empty_store() -> dict[str, Any]:
    return {
        "users": {},
        "friend_invites": {},
        "friend_suggestions": {},
        "friendships": {},
        "goals": {},
        "user_stats": {},
        "debug": {"time_offset_seconds": 0},
    }


def _normalise_store(data: dict[str, Any]) -> dict[str, Any]:
    # Earlier local data files could contain non-profile user records; ignore
    # entries that are not Dogether profiles and initialise missing collections.
    store = _empty_store()
    users = data.get("users", {}) if isinstance(data.get("users"), dict) else {}
    store["users"] = {
        user_id: _normalise_user_profile(user)
        for user_id, user in users.items()
        if isinstance(user, dict) and "email" in user and "user_id" in user
    }
    for key in ["friend_invites", "friend_suggestions", "friendships", "goals", "user_stats"]:
        value = data.get(key, {})
        store[key] = value if isinstance(value, dict) else {}
    _normalise_goal_participants(store["goals"])
    _normalise_user_stats(store["user_stats"])
    debug = data.get("debug", {}) if isinstance(data.get("debug"), dict) else {}
    try:
        offset_seconds = int(debug.get("time_offset_seconds", 0) or 0)
    except (TypeError, ValueError):
        offset_seconds = 0
    store["debug"] = {"time_offset_seconds": max(0, offset_seconds)}
    return store


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _normalise_friend_pair(value: Any) -> list[str] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    first_user_id = str(value[0] or "").strip()
    second_user_id = str(value[1] or "").strip()
    if not first_user_id or not second_user_id or first_user_id == second_user_id:
        return None
    return sorted([first_user_id, second_user_id])


def _normalise_user_profile(user: dict[str, Any]) -> dict[str, Any]:
    normalised = dict(user)
    dismissed_pairs = []
    seen_pairs = set()
    for value in user.get("dismissed_friend_suggestion_pairs", []):
        pair = _normalise_friend_pair(value)
        if pair is None:
            continue
        pair_key = tuple(pair)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        dismissed_pairs.append(pair)
    normalised["dismissed_friend_suggestion_pairs"] = dismissed_pairs
    return normalised


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(APP_ZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=APP_ZONE)
    return now.astimezone(APP_ZONE)


def _iso(now: datetime | None = None) -> str:
    return _now(now).astimezone(UTC).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _now(parsed)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _friendship_id(first_user_id: str, second_user_id: str) -> str:
    first, second = sorted([first_user_id, second_user_id])
    return f"friendship_{first}_{second}"


def _find_user_by_email(data: dict[str, Any], email: str) -> dict[str, Any] | None:
    for user in data["users"].values():
        if user.get("email") == normalize_email(email):
            return user
    return None


def _active_friendship(data: dict[str, Any], first_user_id: str, second_user_id: str) -> bool:
    friendship = data["friendships"].get(_friendship_id(first_user_id, second_user_id))
    return bool(friendship and friendship.get("active"))


def _goal_active_for_user(goal: dict[str, Any], user_id: str) -> bool:
    participant = goal.get("participants", {}).get(user_id)
    return bool(participant and not participant.get("left_at") and not goal.get("archived_at"))


def _schedule(schedule_class: str, required_periods: int | None = None) -> dict[str, Any]:
    if schedule_class not in SCHEDULES:
        raise ValueError("Unsupported schedule class.")
    schedule = dict(SCHEDULES[schedule_class])
    if schedule_class in {"daily_x_per_week", "weekly_x_per_month"}:
        schedule["required_periods"] = max(1, int(required_periods or schedule["required_periods"]))
    return schedule


def _period_start(now: datetime, base: str) -> datetime:
    local = _now(now)
    if base == "day":
        return local.replace(hour=0, minute=0, second=0, microsecond=0)
    if base == "week":
        start = local - timedelta(days=local.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"Unsupported period base: {base}")


def _next_period_start(period_start: datetime, base: str) -> datetime:
    if base == "day":
        return period_start + timedelta(days=1)
    if base == "week":
        return period_start + timedelta(weeks=1)
    raise ValueError(f"Unsupported period base: {base}")


def _period_key(period_start: datetime) -> str:
    return _now(period_start).date().isoformat()


def _participant_period_key(participant: dict[str, Any], goal: dict[str, Any], now: datetime | None = None) -> str:
    schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
    period_start = _parse_dt(participant.get("period_start"))
    if period_start is None:
        period_start = _period_start(_now(now), schedule["base"])
    return _period_key(_period_start(period_start, schedule["base"]))


def _aggregate_start(period_start: datetime, aggregate: str) -> date:
    local = _now(period_start)
    if aggregate == "day":
        return local.date()
    if aggregate == "week":
        return (local - timedelta(days=local.weekday())).date()
    if aggregate == "month":
        return date(local.year, local.month, 1)
    raise ValueError(f"Unsupported aggregate: {aggregate}")


def _base_periods_in_aggregate(period_start: datetime, schedule: dict[str, Any]) -> int:
    if schedule["aggregate"] == "day":
        return 1
    if schedule["aggregate"] == "week" and schedule["base"] == "day":
        return 7
    if schedule["aggregate"] == "month" and schedule["base"] == "week":
        month_start = _aggregate_start(period_start, "month")
        _, month_days = calendar.monthrange(month_start.year, month_start.month)
        return sum(
            1
            for day_number in range(1, month_days + 1)
            if date(month_start.year, month_start.month, day_number).weekday() == 0
        )
    return int(schedule.get("required_periods", 1))


def _period_outcomes(participant: dict[str, Any]) -> dict[str, Any]:
    outcomes = participant.setdefault("period_outcomes", {})
    if not isinstance(outcomes, dict):
        outcomes = {}
        participant["period_outcomes"] = outcomes
    return outcomes


def _completion_reactions(participant: dict[str, Any]) -> dict[str, Any]:
    reactions = participant.setdefault("completion_reactions", {})
    if not isinstance(reactions, dict):
        reactions = {}
        participant["completion_reactions"] = reactions
    return reactions


def _validate_goal_completion_reaction(
    goal: dict[str, Any],
    completed_user_id: str,
    reacting_user_id: str,
    emote: str,
    now: datetime | None = None,
) -> tuple[dict[str, Any], str]:
    if emote not in REACTION_EMOTES:
        raise ValueError("Unsupported reaction emote.")
    if completed_user_id == reacting_user_id:
        raise ValueError("You cannot react to your own completed goal.")
    if not _goal_active_for_user(goal, completed_user_id) or not _goal_active_for_user(goal, reacting_user_id):
        raise ValueError("Goal is not active for this user.")

    participant = goal["participants"][completed_user_id]
    if participant.get("skipped"):
        raise ValueError("Skipped goals cannot receive reactions.")
    current = max(0, int(participant.get("current", 0) or 0))
    target = max(1, int(participant.get("target", 1) or 1))
    if current < target:
        raise ValueError("Only completed goals can receive reactions.")
    return participant, _participant_period_key(participant, goal, now)


def _period_fulfilled(
    goal: dict[str, Any],
    participant: dict[str, Any],
    period_start: datetime,
    *,
    current: int | None = None,
    target: int | None = None,
    skipped: bool | None = None,
) -> bool:
    progress = max(0, int(participant.get("current", 0) if current is None else current))
    max_target = max(1, int(participant.get("target", 1) if target is None else target))
    if progress >= max_target:
        return True

    schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
    if schedule["base"] == schedule["aggregate"]:
        return False

    allowed_missed_periods = max(0, _base_periods_in_aggregate(period_start, schedule) - schedule["required_periods"])
    if allowed_missed_periods <= 0:
        return False

    current_key = _period_key(period_start)
    current_aggregate_start = _aggregate_start(period_start, schedule["aggregate"])
    missed_periods = 1
    for outcome_key, outcome in _period_outcomes(participant).items():
        if outcome_key >= current_key or not isinstance(outcome, dict) or outcome.get("completed"):
            continue
        outcome_start = _now(datetime.fromisoformat(outcome_key))
        if _aggregate_start(outcome_start, schedule["aggregate"]) == current_aggregate_start:
            missed_periods += 1
    return missed_periods <= allowed_missed_periods


def _record_period_outcome(
    goal: dict[str, Any],
    participant: dict[str, Any],
    period_start: datetime,
    *,
    current: int | None = None,
    target: int | None = None,
    skipped: bool | None = None,
) -> bool:
    progress = max(0, int(participant.get("current", 0) if current is None else current))
    max_target = max(1, int(participant.get("target", 1) if target is None else target))
    is_skipped = bool(participant.get("skipped", False) if skipped is None else skipped)
    completed = progress >= max_target
    fulfilled = _period_fulfilled(
        goal,
        participant,
        period_start,
        current=progress,
        target=max_target,
        skipped=is_skipped,
    )
    outcomes = _period_outcomes(participant)
    outcomes[_period_key(period_start)] = {
        "completed": completed,
        "skipped": is_skipped or progress == 0,
        "fulfilled": fulfilled,
        "current": progress,
        "target": max_target,
        "percent": round((progress / max_target) * 100, 1),
    }
    for outcome_key in sorted(outcomes)[:-370]:
        del outcomes[outcome_key]
    return fulfilled


def _correct_period_outcome(
    goal: dict[str, Any],
    participant: dict[str, Any],
    period_start: datetime,
    *,
    current: int,
    target: int | None = None,
    skipped: bool = False,
) -> list[date]:
    schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
    corrected_start = _period_start(period_start, schedule["base"])
    corrected_key = _period_key(corrected_start)
    aggregate_start = _aggregate_start(corrected_start, schedule["aggregate"])
    outcomes = _period_outcomes(participant)
    existing_target = outcomes.get(corrected_key, {}).get("target", participant.get("target", 1))
    corrected_target = max(1, int(existing_target if target is None else target))
    outcomes[corrected_key] = {
        "current": max(0, int(current)),
        "target": corrected_target,
        "skipped": bool(skipped),
    }

    affected_keys = {
        outcome_key
        for outcome_key in outcomes
        if outcome_key >= corrected_key
        and _aggregate_start(_now(datetime.fromisoformat(outcome_key)), schedule["aggregate"]) == aggregate_start
    }
    affected_days = []
    for outcome_key in sorted(affected_keys):
        outcome = outcomes.get(outcome_key, {})
        if not isinstance(outcome, dict):
            outcome = {}
        outcome_start = _period_start(_now(datetime.fromisoformat(outcome_key)), schedule["base"])
        _record_period_outcome(
            goal,
            participant,
            outcome_start,
            current=max(0, int(outcome.get("current", 0) or 0)),
            target=max(1, int(outcome.get("target", participant.get("target", 1)) or 1)),
            skipped=bool(outcome.get("skipped", False)),
        )
        affected_days.append(outcome_start.date())

    current_period_start = _parse_dt(participant.get("period_start"))
    if current_period_start:
        current_period_start = _period_start(current_period_start, schedule["base"])
        if _aggregate_start(current_period_start, schedule["aggregate"]) == aggregate_start:
            affected_days.append(current_period_start.date())
    return sorted(set(affected_days))

def _normalise_goal_participants(goals: dict[str, Any]) -> None:
    for goal in goals.values():
        if not isinstance(goal, dict):
            continue
        participants = goal.get("participants", {})
        if not isinstance(participants, dict):
            goal["participants"] = {}
            continue
        for participant in participants.values():
            if isinstance(participant, dict):
                participant["completion_streak"] = max(0, int(participant.get("completion_streak", 0) or 0))
                participant["completion_notifications_enabled"] = bool(
                    participant.get("completion_notifications_enabled", True)
                )
                participant["completion_notifications_max_per_day"] = max(
                    1,
                    int(participant.get("completion_notifications_max_per_day", 3) or 3),
                )
                if not isinstance(participant.get("completion_notification_counts"), dict):
                    participant["completion_notification_counts"] = {}
                participant["skipped"] = bool(participant.get("skipped", False))
                if not isinstance(participant.get("period_outcomes"), dict):
                    participant["period_outcomes"] = {}
                if not isinstance(participant.get("completion_reactions"), dict):
                    participant["completion_reactions"] = {}


def _normalise_user_stats(user_stats: dict[str, Any]) -> None:
    for user_id, stats in list(user_stats.items()):
        if not isinstance(stats, dict):
            user_stats[user_id] = {"activity_days": {}}
            continue
        days = stats.get("activity_days", {})
        stats["activity_days"] = days if isinstance(days, dict) else {}


def _user_stats(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    stats = data.setdefault("user_stats", {}).setdefault(user_id, {})
    activity_days = stats.get("activity_days")
    if not isinstance(activity_days, dict):
        activity_days = {}
        stats["activity_days"] = activity_days
    return stats


def _refresh_activity_day(data: dict[str, Any], user_id: str, day: Any) -> None:
    date_key = day.isoformat() if hasattr(day, "isoformat") else str(day)
    day_start = _now(datetime.fromisoformat(date_key))
    active_goals = 0
    fulfilled_goals = 0
    for goal in data.get("goals", {}).values():
        if not isinstance(goal, dict) or not _goal_active_for_user(goal, user_id):
            continue
        participant = goal["participants"][user_id]
        schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
        day_period_start = _period_start(day_start, schedule["base"])
        period_key = day_period_start.date().isoformat()
        outcome = _period_outcomes(participant).get(period_key)
        current_period_start = _parse_dt(participant.get("period_start"))
        current_period_start = _period_start(current_period_start, schedule["base"]) if current_period_start else None
        is_current_period = current_period_start == day_period_start
        if not isinstance(outcome, dict) and not is_current_period:
            continue

        active_goals += 1
        if isinstance(outcome, dict):
            fulfilled = bool(outcome.get("fulfilled", outcome.get("completed", False)))
        else:
            fulfilled = _period_fulfilled(goal, participant, day_period_start)
        if fulfilled:
            fulfilled_goals += 1

    percent = round((fulfilled_goals / active_goals) * 100, 1) if active_goals else 0.0
    stats = _user_stats(data, user_id)
    activity_days = stats["activity_days"]
    activity_days[date_key] = {
        "active_goals": active_goals,
        "fulfilled_goals": fulfilled_goals,
        "percent": percent,
    }
    _trim_activity_days(activity_days)


def _repair_activity_days(data: dict[str, Any], user_id: str, now: datetime | None = None) -> None:
    stats = _user_stats(data, user_id)
    if stats.get("activity_days_repair_version") == ACTIVITY_DAYS_REPAIR_VERSION:
        return

    today = _now(now).date()
    for offset in range(364, -1, -1):
        _refresh_activity_day(data, user_id, today - timedelta(days=offset))
    stats["activity_days_repair_version"] = ACTIVITY_DAYS_REPAIR_VERSION


def _trim_activity_days(activity_days: dict[str, Any]) -> None:
    sorted_keys = sorted(activity_days)
    for date_key in sorted_keys[:-365]:
        del activity_days[date_key]


def _days_using_app(user: dict[str, Any], now: datetime) -> int:
    created_at = _parse_dt(user.get("created_at"))
    if not created_at:
        return 0
    return max(1, (now.date() - created_at.date()).days + 1)
