from __future__ import annotations


ACTIVITY_COLORS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]


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
