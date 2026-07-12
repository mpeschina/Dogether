from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from html import escape

from src.db.persistence_helpers import _now, _period_fulfilled, _period_start, _schedule


ACTIVITY_COLORS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
FUTURE_ACTIVITY_COLOR = "#ffffff"
STREAMLIT_PRIMARY_COLOR = "#1F2937"
X_PER_SCHEDULE_CLASSES = {"daily_x_per_week", "weekly_x_per_month"}


def activity_color_for_percent(percent: float, *, active: bool = True) -> str:
    if not active:
        return ACTIVITY_COLORS[0]
    if percent >= 100:
        return ACTIVITY_COLORS[4]
    if percent >= 75:
        return ACTIVITY_COLORS[3]
    if percent >= 50:
        return ACTIVITY_COLORS[2]
    if percent > 0:
        return ACTIVITY_COLORS[1]
    return ACTIVITY_COLORS[0]


def compact_goal_activity_html(goal: dict, participant: dict, now: datetime | None = None) -> str:
    now_dt = _now(now)
    schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
    period_starts = _mini_activity_period_starts(now_dt, schedule)
    current_period_start = _period_start(now_dt, schedule["base"])
    dots = [
        (
            f"<span class='{_mini_activity_dot_class(period_start, current_period_start)}' "
            f"title='{escape(period_start.strftime('%A'), quote=True)}' "
            f"style='background:{_mini_activity_color(goal, participant, period_start, now_dt)};'></span>"
        )
        for period_start in period_starts
    ]
    return f"<span class='mini-activity-dots'>{''.join(dots)}</span>"


def mini_activity_styles() -> str:
    return """
        .mini-activity-dots {
            display: inline-flex;
            align-items: center;
            gap: 3px;
            white-space: nowrap;
        }
        .mini-activity-dot {
            width: 8px;
            height: 8px;
            border-radius: 2px;
            box-shadow: inset 0 0 0 1px rgba(27,31,36,0.14);
            flex: 0 0 auto;
        }
        .mini-activity-dot-current {
            box-shadow: 0 0 0 1.5px rgba(31,41,55,0.42);
        }
    """


def _mini_activity_dot_class(period_start: datetime, current_period_start: datetime) -> str:
    class_name = "mini-activity-dot"
    if period_start == current_period_start:
        class_name += " mini-activity-dot-current"
    return class_name


def _mini_activity_period_starts(now_dt: datetime, schedule: dict) -> list[datetime]:
    if schedule["base"] == "day":
        week_start = _period_start(now_dt, "week")
        return [week_start + timedelta(days=offset) for offset in range(7)]

    month_start = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _, month_days = calendar.monthrange(month_start.year, month_start.month)
    return [
        month_start + timedelta(days=day_offset)
        for day_offset in range(month_days)
        if (month_start + timedelta(days=day_offset)).weekday() == 0
    ]


def _mini_activity_color(goal: dict, participant: dict, period_start: datetime, now_dt: datetime) -> str:
    schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
    current_period_start = _period_start(now_dt, schedule["base"])
    if period_start > current_period_start:
        return FUTURE_ACTIVITY_COLOR

    outcome = participant.get("period_outcomes", {}).get(period_start.date().isoformat())
    if isinstance(outcome, dict):
        completed = bool(outcome.get("completed", False))
        fulfilled = bool(outcome.get("fulfilled", completed))
        percent = _outcome_percent(outcome)
        if completed:
            return ACTIVITY_COLORS[4]
        if _uses_required_period_allowance(goal):
            if fulfilled and outcome.get("skipped"):
                return STREAMLIT_PRIMARY_COLOR
            if not fulfilled and percent <= 0:
                return ACTIVITY_COLORS[0]
        if fulfilled:
            return ACTIVITY_COLORS[4]
        return activity_color_for_percent(percent)

    if period_start == current_period_start:
        fulfilled = _period_fulfilled(goal, participant, period_start)
        skipped = bool(participant.get("skipped", False))
        if _uses_required_period_allowance(goal):
            if fulfilled and skipped:
                return STREAMLIT_PRIMARY_COLOR
        if skipped and not fulfilled:
            return ACTIVITY_COLORS[0]
        if fulfilled:
            return ACTIVITY_COLORS[4]
        target = max(1, int(participant.get("target", 1) or 1))
        current = max(0, int(participant.get("current", 0) or 0))
        return activity_color_for_percent((current / target) * 100)

    return ACTIVITY_COLORS[0]


def _uses_required_period_allowance(goal: dict) -> bool:
    return goal.get("schedule_class") in X_PER_SCHEDULE_CLASSES


def _outcome_percent(outcome: dict) -> float:
    if "percent" in outcome:
        return max(0.0, float(outcome.get("percent") or 0.0))
    target = max(1, int(outcome.get("target", 1) or 1))
    current = max(0, int(outcome.get("current", 0) or 0))
    return (current / target) * 100
