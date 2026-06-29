from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from typing import Mapping

import streamlit as st

from push_component import push_subscribe
from src.db.persistence import Persistence
from src.push.sender import push_configured, send_push_to_user
from src.push.storage import PushStorage


def render_account(
    persistence: Persistence,
    current_user: dict,
    user_id: str,
    push_storage: PushStorage | None = None,
    push_settings: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> None:
    st.title("Account")
    st.write("Name")
    st.subheader(current_user["name"])
    st.write("Email")
    st.subheader(current_user["email"])

    stats = persistence.account_stats(user_id, now=now)
    cols = st.columns(4)
    cols[0].metric("Active goals", stats["active_goals"])
    cols[1].metric("Friends", stats["friend_count"])
    cols[2].metric("Days using app", stats["days_using_app"])
    cols[3].metric("Month completion", f"{stats['completion_rate']}%")

    render_notification_controls(current_user, user_id, push_storage, push_settings or {}, now=now)

    st.subheader("Activity")
    render_activity_diagram(stats.get("activity_days", {}), now=now, days=365)


def render_notification_controls(
    current_user: dict,
    user_id: str,
    push_storage: PushStorage | None,
    push_settings: Mapping[str, str],
    now: datetime | None = None,
) -> None:
    st.subheader("Notifications")
    st.warning(
        "iPhone/iPad setup: open Dogether in Safari, use Share > Add to Home Screen, "
        "then open Dogether from the Home Screen before enabling notifications."
    )

    if not push_configured(push_settings):
        st.info("Push notifications are not configured for this deployment yet.")
        return
    if push_storage is None:
        st.info("Push notification storage is unavailable.")
        return

    value = push_subscribe(
        vapid_public_key=push_settings["vapid_public_key"],
        service_worker_url="/~/+/app/static/sw.js",
        key=f"push-subscribe-{user_id}",
    )

    if value:
        if value.get("ok") and value.get("subscription"):
            try:
                push_storage.save_subscription(
                    user_id,
                    current_user["email"],
                    value["subscription"],
                    user_agent=value.get("userAgent"),
                    now=now,
                )
                st.success("Push notifications are enabled for this device.")
            except ValueError as error:
                st.error(str(error))
        elif value.get("ok") and value.get("unsubscribe"):
            push_storage.delete_subscription(value.get("endpoint", ""))
            st.success("Push notifications are disabled for this device.")
        elif not value.get("ok"):
            st.error(value.get("error", "Could not update push notification settings."))

    if st.button("Send test notification", key="send_test_push"):
        result = send_push_to_user(
            push_storage,
            user_id,
            title="Dogether test",
            body="Push notifications are working.",
            url="/",
            vapid_private_key=push_settings["vapid_private_key"],
            vapid_subject=push_settings["vapid_subject"],
        )
        if result["sent"]:
            st.success(f"Sent {result['sent']} test notification(s).")
        elif result["removed"]:
            st.info("Removed expired push subscriptions. Enable notifications again on this device.")
        else:
            st.info("No active push subscriptions found for your account yet.")
        if result["errors"]:
            st.error("; ".join(result["errors"]))


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
        color = _activity_color(percent, active_goals) if is_visible_day else "transparent"
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

    legend_nodes = "".join(f"<span style='background:{color}'></span>" for color in _ACTIVITY_COLORS)
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


_ACTIVITY_COLORS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]


def _activity_color(percent: float, active_goals: int) -> str:
    if active_goals <= 0:
        return _ACTIVITY_COLORS[0]
    if percent >= 100:
        return _ACTIVITY_COLORS[4]
    if percent >= 75:
        return _ACTIVITY_COLORS[3]
    if percent >= 50:
        return _ACTIVITY_COLORS[2]
    if percent > 0:
        return _ACTIVITY_COLORS[1]
    return _ACTIVITY_COLORS[0]


def _local_date(now: datetime | None = None) -> date:
    if now is None:
        return datetime.now().date()
    return now.date()


def _shift_month(day: date, offset: int) -> date:
    month_index = day.year * 12 + day.month - 1 + offset
    year, month_zero = divmod(month_index, 12)
    return date(year, month_zero + 1, 1)
