from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
import streamlit as st

from src.db.persistence import Persistence
from src.pages.common_helpers import ACTIVITY_COLORS, activity_color_for_percent


def render_account(
    persistence: Persistence,
    current_user: dict,
    user_id: str,
    now: datetime | None = None,
) -> None:
    st.title("Account")
    st.write("Name")
    picture_url = st.user.get("picture")
    if picture_url:
        image_col, name_col = st.columns([0.15, 0.85], vertical_alignment="center", gap="xsmall")
        image_col.image(picture_url, width=80)
        name_col.subheader(current_user["name"])
    else:
        st.subheader(current_user["name"])
    st.write("Email")
    st.subheader(current_user["email"])

    stats = persistence.account_stats(user_id, now=now)
    cols = st.columns(4)
    cols[0].metric("Active goals", stats["active_goals"])
    cols[1].metric("Friends", stats["friend_count"])
    cols[2].metric("Days using app", stats["days_using_app"])
    cols[3].metric("Month completion", f"{stats['completion_rate']}%")

    st.subheader("Activity")
    render_activity_diagram(stats.get("activity_days", {}), now=now, days=365)


def render_activity_diagram(
    activity_days: dict,
    now: datetime | None = None,
    *,
    days: int = 365,
    months: int | None = None,
) -> None:
    html = activity_diagram_html(activity_days, now=now, days=days, months=months)
    if hasattr(st, "html"):
        st.html(html)
    else:
        st.markdown(html, unsafe_allow_html=True)


def activity_diagram_html(
    activity_days: dict,
    now: datetime | None = None,
    *,
    days: int = 365,
    months: int | None = None,
) -> str:
    today = _local_date(now)
    if months is not None:
        months = max(1, int(months))
        first_day = _shift_month(today.replace(day=1), -(months - 1))
    else:
        first_day = today - timedelta(days=max(1, int(days)) - 1)
    end_day = today
    grid_start = first_day - timedelta(days=first_day.weekday())
    grid_end = today + timedelta(days=6 - today.weekday())
    total_days = (grid_end - grid_start).days + 1
    week_count = total_days // 7

    month_labels = []
    month_cursor = first_day.replace(day=1)
    while month_cursor <= end_day:
        label_day = max(month_cursor, first_day)
        column = ((label_day - grid_start).days // 7) + 2
        month_labels.append(
            f"<div class='activity-month' style='grid-column:{column};'>{escape(month_cursor.strftime('%b'))}</div>"
        )
        month_cursor = _shift_month(month_cursor, 1)

    weekday_labels = {
        0: "M",
        2: "W",
        4: "F",
    }
    weekday_nodes = [
        f"<div class='activity-weekday' style='grid-row:{weekday + 2};'>{label}</div>"
        for weekday, label in weekday_labels.items()
    ]

    day_nodes = []
    current_day = grid_start
    while current_day <= grid_end:
        week = ((current_day - grid_start).days // 7) + 2
        weekday = current_day.weekday() + 2
        is_visible_day = first_day <= current_day <= end_day
        stats = activity_days.get(current_day.isoformat(), {}) if is_visible_day else {}
        active_goals = int(stats.get("active_goals", 0) or 0)
        fulfilled_goals = int(stats.get("fulfilled_goals", 0) or 0)
        percent = float(stats.get("percent", 0.0) or 0.0)
        color = activity_color_for_percent(percent, active=active_goals > 0) if is_visible_day else "transparent"
        title = escape(
            f"{current_day.isoformat()}: {fulfilled_goals} / {active_goals} goals fulfilled ({percent}%)",
            quote=True,
        )
        day_nodes.append(
            (
                f"<div class='activity-day' title='{title}' "
                f"style='grid-column:{week};grid-row:{weekday};background:{color};'></div>"
            )
        )
        current_day += timedelta(days=1)

    legend_nodes = "".join(f"<span style='background:{color}'></span>" for color in ACTIVITY_COLORS)
    return (
        "<style>"
        ".activity-shell{--cell:11px;--gap:3px;color:#57606a;max-width:100%;overflow-x:auto;"
        "padding:0.15rem 0 0.35rem;}"
        ".activity-grid{display:grid;grid-template-columns:22px repeat("
        f"{week_count},var(--cell));grid-template-rows:18px repeat(7,var(--cell));"
        "grid-auto-flow:column;gap:var(--gap);align-items:center;}"
        ".activity-month{grid-row:1;font-size:0.76rem;line-height:1;color:#6e7781;white-space:nowrap;}"
        ".activity-weekday{grid-column:1;font-size:0.68rem;line-height:1;color:#6e7781;}"
        ".activity-day{width:var(--cell);height:var(--cell);border-radius:2px;box-shadow:inset 0 0 0 1px rgba(27,31,36,0.06);}"
        ".activity-legend{display:flex;align-items:center;justify-content:flex-end;gap:0.35rem;"
        "font-size:0.72rem;color:#6e7781;margin-top:0.55rem;}"
        ".activity-legend span{width:var(--cell);height:var(--cell);border-radius:2px;"
        "box-shadow:inset 0 0 0 1px rgba(27,31,36,0.06);}"
        "</style>"
        "<div class='activity-shell'>"
        f"<div class='activity-grid'>{''.join(month_labels)}{''.join(weekday_nodes)}{''.join(day_nodes)}</div>"
        f"<div class='activity-legend'>Less{legend_nodes}More</div>"
        "</div>"
    )


def _local_date(now: datetime | None = None) -> date:
    if now is None:
        return datetime.now().date()
    return now.date()


def _shift_month(day: date, offset: int) -> date:
    month_index = day.year * 12 + day.month - 1 + offset
    year, month_zero = divmod(month_index, 12)
    return date(year, month_zero + 1, 1)
