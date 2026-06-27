from datetime import datetime
from zoneinfo import ZoneInfo

from src.pages.account_page import activity_diagram_html

BERLIN = ZoneInfo("Europe/Berlin")


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=BERLIN)


def test_activity_diagram_html_renders_variable_month_github_grid() -> None:
    html = activity_diagram_html(
        {
            "2026-11-02": {"active_goals": 2, "fulfilled_goals": 1, "percent": 50.0},
            "2026-12-01": {"active_goals": 1, "fulfilled_goals": 1, "percent": 100.0},
        },
        now=at("2026-12-15T12:00:00"),
        months=2,
    )

    assert "activity-grid" in html
    assert "repeat(8,var(--cell))" in html
    assert ">Nov</div>" in html
    assert ">Dec</div>" in html
    assert html.count("class='activity-day'") == 56
    assert "2026-11-02: 1 / 2 goals fulfilled (50.0%)" in html
    assert "background:#40c463" in html
    assert "2026-12-01: 1 / 1 goals fulfilled (100.0%)" in html
    assert "background:#216e39" in html


def test_activity_diagram_html_renders_full_past_365_days() -> None:
    html = activity_diagram_html(
        {
            "2026-01-01": {"active_goals": 1, "fulfilled_goals": 1, "percent": 100.0},
            "2026-12-31": {"active_goals": 2, "fulfilled_goals": 1, "percent": 50.0},
        },
        now=at("2026-12-31T12:00:00"),
        days=365,
    )

    assert ">Jan</div>" in html
    assert ">Dec</div>" in html
    assert "2026-01-01: 1 / 1 goals fulfilled (100.0%)" in html
    assert "2026-12-31: 1 / 2 goals fulfilled (50.0%)" in html
    assert html.count("class='activity-day'") == 371
