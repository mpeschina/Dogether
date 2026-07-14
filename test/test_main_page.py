from datetime import datetime
from pathlib import Path

from src.pages.health_data_import_page import (
    DEFAULT_SHORTCUT_INSTALL_URL,
    active_health_data_import_goal,
    apple_steps_shortcut_run_url,
    data_import_available_for_viewport,
    health_data_import_settings,
    health_data_import_enabled,
    normalized_data_import_availability,
)
from src.pages.common_helpers import (
    MINI_ACTIVITY_CELL_SIZE,
    ACTIVITY_COLORS,
    PARTICIPANT_SPARKLINE_FILL,
    PARTICIPANT_SPARKLINE_STROKE_WIDTH,
    FUTURE_ACTIVITY_COLOR,
    PARTICIPANT_SPARKLINE_COLOR,
    PARTICIPANT_SPARKLINE_DEFAULT_DAYS,
    STREAMLIT_PRIMARY_COLOR,
    compact_goal_activity_html,
    mini_activity_styles,
    participant_sparkline_html,
    _participant_sparkline_values,
)
from src.pages.main_page import (
    participant_name_with_progress_html,
    participant_progress_label,
    ordered_active_participant_ids,
    visible_participant_ids,
    truncate_participant_name,
)


def test_ordered_active_participant_ids_pins_current_user_first() -> None:
    goal = {
        "participant_user_ids": ["alice", "bob", "charlie"],
        "participants": {
            "alice": {"left_at": None},
            "bob": {"left_at": None},
            "charlie": {"left_at": None},
        },
    }

    assert ordered_active_participant_ids(goal, "bob") == ["bob", "alice", "charlie"]


def test_ordered_active_participant_ids_filters_left_participants() -> None:
    goal = {
        "participant_user_ids": ["alice", "bob", "charlie"],
        "participants": {
            "alice": {"left_at": None},
            "bob": {"left_at": "2026-06-01T10:00:00+00:00"},
            "charlie": {"left_at": None},
        },
    }

    assert ordered_active_participant_ids(goal, "alice") == ["alice", "charlie"]


def test_ordered_active_participant_ids_includes_active_participants_missing_from_order() -> None:
    goal = {
        "participant_user_ids": ["alice"],
        "participants": {
            "alice": {"left_at": None},
            "bob": {"left_at": None},
            "charlie": {"left_at": None},
        },
    }

    assert ordered_active_participant_ids(goal, "charlie") == ["charlie", "alice", "bob"]


def test_visible_participant_ids_include_self_and_friends_only() -> None:
    goal = {
        "participant_user_ids": ["alice", "bob", "charlie", "dana"],
        "participants": {
            "alice": {"left_at": None},
            "bob": {"left_at": None},
            "charlie": {"left_at": None},
            "dana": {"left_at": "2026-06-01T10:00:00+00:00"},
        },
    }

    assert visible_participant_ids(goal, "alice", {"bob", "dana"}) == ["alice", "bob"]


def test_visible_participant_ids_preserve_order_with_missing_participants() -> None:
    goal = {
        "participant_user_ids": ["alice"],
        "participants": {
            "alice": {"left_at": None},
            "bob": {"left_at": None},
            "charlie": {"left_at": None},
        },
    }

    assert visible_participant_ids(goal, "charlie", {"alice", "bob"}) == ["charlie", "alice", "bob"]


def test_participant_progress_label_uses_compact_current_target() -> None:
    assert participant_progress_label(0, 10, False) == "0/10"


def test_participant_name_with_progress_keeps_progress_inline_and_escaped() -> None:
    html = participant_name_with_progress_html("Ada <L>", "0/10")

    assert "Ada &lt;L&gt;" in html
    assert "0/10" in html
    assert "participant-progress-row" in html


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _goal(schedule_class: str, required_periods: int = 1, participant: dict | None = None) -> dict:
    return {
        "id": "goal_1",
        "schedule_class": schedule_class,
        "required_periods": required_periods,
        "participants": {
            "alice": participant
            or {
                "current": 0,
                "target": 10,
                "skipped": False,
                "period_outcomes": {},
            }
        },
    }


def test_truncate_participant_name_keeps_twenty_five_characters() -> None:
    assert truncate_participant_name("Ada Lovelace") == "Ada Lovelace"
    assert truncate_participant_name("ABCDEFGHIJKLMNOPQRSTUVWXYZ") == "ABCDEFGHIJKLMNOPQRSTUV..."


def test_participant_name_with_progress_truncates_and_escapes_name() -> None:
    html = participant_name_with_progress_html("ABCDEFGHIJKLMNOPQRSTUVWX<danger>", "1/2")

    assert "ABCDEFGHIJKLMNOPQRSTUV..." in html
    assert "title='ABCDEFGHIJKLMNOPQRSTUVWX&lt;danger&gt;'" in html
    assert "<danger>" not in html


def test_participant_sparkline_renders_ten_day_inline_svg_with_progress_bar_fill() -> None:
    participant = {
        "current": 8,
        "target": 10,
        "skipped": False,
        "period_outcomes": {
            "2026-06-01": {"completed": False, "fulfilled": False, "current": 2, "target": 10},
            "2026-06-04": {"completed": True, "fulfilled": True, "current": 4, "target": 4},
            "2026-06-08": {"completed": False, "fulfilled": False, "current": 5, "target": 10},
        },
    }

    html = participant_sparkline_html(
        _goal("daily", participant=participant),
        participant,
        now=_at("2026-06-10T12:00:00"),
    )
    line_points = html.split("<polyline", 1)[1].split("points='", 1)[1].split("'", 1)[0].split()

    assert "participant-sparkline" in html
    assert f"title='Sparkline of the last {PARTICIPANT_SPARKLINE_DEFAULT_DAYS} days'" in html
    assert f"stroke='{PARTICIPANT_SPARKLINE_COLOR}'" in html
    assert f"stroke-width='{PARTICIPANT_SPARKLINE_STROKE_WIDTH}'" in html
    assert f"<polygon points=" in html
    assert f"fill='{PARTICIPANT_SPARKLINE_FILL}'" in html
    assert f"<circle" in html
    assert f"fill='{PARTICIPANT_SPARKLINE_COLOR}'" in html
    completed_x, completed_y = [float(value) for value in line_points[3].split(",")]
    today_x, today_y = [float(value) for value in line_points[-1].split(",")]

    assert len(line_points) == PARTICIPANT_SPARKLINE_DEFAULT_DAYS
    assert completed_x < today_x
    assert completed_y > today_y


def test_participant_sparkline_treats_allowed_x_per_week_skip_as_reached() -> None:
    participant = {
        "current": 0,
        "target": 10,
        "skipped": True,
        "period_outcomes": {
            "2026-06-01": {
                "completed": False,
                "skipped": True,
                "fulfilled": True,
                "current": 0,
                "target": 10,
            }
        },
    }
    goal = _goal("daily_x_per_week", required_periods=5, participant=participant)

    values = _participant_sparkline_values(goal, participant, now=_at("2026-06-03T12:00:00"))

    assert values[-3] == 10
    assert values[-1] == 10


def test_participant_sparkline_does_not_cap_progress_at_target() -> None:
    participant = {
        "current": 15,
        "target": 10,
        "skipped": False,
        "period_outcomes": {
            "2026-06-01": {
                "completed": True,
                "fulfilled": True,
                "current": 14,
                "target": 10,
            }
        },
    }
    goal = _goal("daily", participant=participant)

    values = _participant_sparkline_values(goal, participant, now=_at("2026-06-03T12:00:00"))

    assert values[-3] == 14
    assert values[-1] == 15


def test_compact_goal_activity_renders_daily_current_week_seven_dots() -> None:
    participant = {"current": 0, "target": 10, "skipped": False, "period_outcomes": {}}
    html = compact_goal_activity_html(
        _goal("daily", participant=participant),
        participant,
        now=_at("2026-06-03T12:00:00"),
    )

    assert html.count("title='") == 7
    assert "title='Monday'" in html
    assert "title='Sunday'" in html
    assert html.count("mini-activity-dot-current") == 1
    assert "title='Wednesday'" in html


def test_mini_activity_uses_own_configurable_cell_size() -> None:
    styles = mini_activity_styles()

    assert f"width: {MINI_ACTIVITY_CELL_SIZE};" in styles
    assert f"height: {MINI_ACTIVITY_CELL_SIZE};" in styles


def test_compact_goal_activity_renders_unreached_days_as_white() -> None:
    participant = {"current": 0, "target": 10, "skipped": False, "period_outcomes": {}}
    html = compact_goal_activity_html(
        _goal("daily", participant=participant),
        participant,
        now=_at("2026-06-03T12:00:00"),
    )

    reached_dot = "title='Tuesday'"
    future_dot = "title='Thursday'"
    assert f"{reached_dot} style='background:{ACTIVITY_COLORS[0]};'" in html
    assert f"{future_dot} style='background:{FUTURE_ACTIVITY_COLOR};'" in html


def test_compact_goal_activity_renders_daily_skipped_unfulfilled_as_grey() -> None:
    participant = {
        "current": 0,
        "target": 10,
        "skipped": False,
        "period_outcomes": {"2026-06-02": {"completed": False, "skipped": True, "fulfilled": False}},
    }
    html = compact_goal_activity_html(
        _goal("daily", participant=participant),
        participant,
        now=_at("2026-06-03T12:00:00"),
    )

    assert f"background:{ACTIVITY_COLORS[0]}" in html
    assert f"background:{ACTIVITY_COLORS[4]}" not in html


def test_compact_goal_activity_renders_stored_partial_progress_as_light_green() -> None:
    participant = {
        "current": 0,
        "target": 5000,
        "skipped": False,
        "period_outcomes": {
            "2026-06-02": {
                "completed": False,
                "skipped": False,
                "fulfilled": False,
                "current": 3800,
                "target": 5000,
                "percent": 76.0,
            }
        },
    }
    html = compact_goal_activity_html(
        _goal("daily", participant=participant),
        participant,
        now=_at("2026-06-03T12:00:00"),
    )

    assert f"background:{ACTIVITY_COLORS[3]}" in html
    assert f"background:{ACTIVITY_COLORS[4]}" not in html


def test_compact_goal_activity_daily_x_per_week_partial_progress_uses_light_green() -> None:
    participant = {
        "current": 0,
        "target": 5000,
        "skipped": False,
        "period_outcomes": {
            "2026-06-01": {
                "completed": False,
                "skipped": False,
                "fulfilled": False,
                "current": 3800,
                "target": 5000,
                "percent": 76.0,
            }
        },
    }
    html = compact_goal_activity_html(
        _goal("daily_x_per_week", required_periods=5, participant=participant),
        participant,
        now=_at("2026-06-03T12:00:00"),
    )

    partial_dot = "title='Monday'"
    assert f"{partial_dot} style='background:{ACTIVITY_COLORS[3]};'" in html
    assert f"{partial_dot} style='background:{ACTIVITY_COLORS[4]};'" not in html


def test_compact_goal_activity_daily_x_per_week_completion_stays_green() -> None:
    participant = {
        "current": 0,
        "target": 10,
        "skipped": False,
        "period_outcomes": {"2026-06-01": {"completed": True, "skipped": False, "fulfilled": True}},
    }
    html = compact_goal_activity_html(
        _goal("daily_x_per_week", required_periods=5, participant=participant),
        participant,
        now=_at("2026-06-03T12:00:00"),
    )

    assert f"background:{ACTIVITY_COLORS[4]}" in html


def test_compact_goal_activity_daily_x_per_week_valid_skip_uses_primary_color() -> None:
    participant = {
        "current": 0,
        "target": 10,
        "skipped": True,
        "period_outcomes": {"2026-06-01": {"completed": False, "skipped": True, "fulfilled": True}},
    }
    goal = _goal("daily_x_per_week", required_periods=5, participant=participant)
    html = compact_goal_activity_html(goal, participant, now=_at("2026-06-03T12:00:00"))

    assert html.count(f"background:{STREAMLIT_PRIMARY_COLOR}") == 2
    assert f"background:{ACTIVITY_COLORS[4]}" not in html

    goal["required_periods"] = 6
    html = compact_goal_activity_html(goal, participant, now=_at("2026-06-03T12:00:00"))

    assert html.count(f"background:{STREAMLIT_PRIMARY_COLOR}") == 1
    assert html.count(f"background:{ACTIVITY_COLORS[0]}") == 2
    assert html.count(f"background:{FUTURE_ACTIVITY_COLOR}") == 4


def test_compact_goal_activity_daily_x_per_week_unfulfilled_skip_uses_grey() -> None:
    participant = {
        "current": 0,
        "target": 10,
        "skipped": False,
        "period_outcomes": {"2026-06-01": {"completed": False, "skipped": True, "fulfilled": False}},
    }
    html = compact_goal_activity_html(
        _goal("daily_x_per_week", required_periods=5, participant=participant),
        participant,
        now=_at("2026-06-03T12:00:00"),
    )

    assert f"background:{STREAMLIT_PRIMARY_COLOR}" not in html
    assert f"background:{ACTIVITY_COLORS[0]}" in html


def test_compact_goal_activity_renders_weekly_current_month_dots() -> None:
    participant = {"current": 0, "target": 10, "skipped": False, "period_outcomes": {}}
    html = compact_goal_activity_html(
        _goal("weekly", participant=participant),
        participant,
        now=_at("2026-06-15T12:00:00"),
    )

    assert html.count("title='") == 5
    assert "title='Monday'" in html


def test_compact_goal_activity_uses_period_outcomes_from_current_goal_only() -> None:
    first_participant = {
        "current": 0,
        "target": 10,
        "skipped": False,
        "period_outcomes": {"2026-06-01": {"completed": True, "fulfilled": True}},
    }
    second_participant = {"current": 0, "target": 10, "skipped": False, "period_outcomes": {}}

    first_html = compact_goal_activity_html(
        _goal("daily", participant=first_participant),
        first_participant,
        now=_at("2026-06-03T12:00:00"),
    )
    second_html = compact_goal_activity_html(
        _goal("daily", participant=second_participant),
        second_participant,
        now=_at("2026-06-03T12:00:00"),
    )

    assert f"background:{ACTIVITY_COLORS[4]}" in first_html
    assert f"background:{ACTIVITY_COLORS[4]}" not in second_html


def test_health_data_import_helpers_find_active_goal() -> None:
    inactive = {"id": "goal_1", "participants": {"alice": {}}}
    active = {
        "id": "goal_2",
        "participants": {
            "alice": {"health_data_workflow": {"enabled": True, "provider": "apple_health_steps"}}
        },
    }

    assert health_data_import_enabled(inactive, "alice") is False
    assert health_data_import_enabled(active, "alice") is True
    assert active_health_data_import_goal([inactive, active], "alice") == active


def test_apple_steps_shortcut_settings_have_install_default_and_encoded_run_url() -> None:
    settings = health_data_import_settings({"health_data": {}})

    assert settings["apple_steps_shortcut_install_url"] == DEFAULT_SHORTCUT_INSTALL_URL
    assert settings["apple_steps_shortcut_availability"] == "ios"
    assert apple_steps_shortcut_run_url("Dogether Steps") == "shortcuts://run-shortcut?name=Dogether%20Steps"


def test_apple_steps_shortcut_availability_setting_is_per_path_and_normalized() -> None:
    for availability in ("all", "ios", "android", "pc"):
        settings = health_data_import_settings(
            {"health_data": {"apple_steps_shortcut_availability": availability.upper()}}
        )

        assert settings["apple_steps_shortcut_availability"] == availability

    assert normalized_data_import_availability("desktop") == "ios"
    assert health_data_import_settings(
        {"health_data": {"apple_steps_shortcut_availability": "desktop"}}
    )["apple_steps_shortcut_availability"] == "ios"


def test_data_import_availability_matches_viewport_platforms() -> None:
    assert data_import_available_for_viewport("all", None) is True
    assert data_import_available_for_viewport("all", {"devicePlatform": "pc"}) is True
    assert data_import_available_for_viewport("ios", None) is False
    assert data_import_available_for_viewport("ios", {"devicePlatform": "all"}) is True
    assert data_import_available_for_viewport("ios", {"devicePlatform": "ios"}) is True
    assert data_import_available_for_viewport("ios", {"devicePlatform": "android"}) is False
    assert data_import_available_for_viewport("android", {"devicePlatform": "android"}) is True
    assert data_import_available_for_viewport("android", {"devicePlatform": "pc"}) is False
    assert data_import_available_for_viewport("pc", {"devicePlatform": "pc"}) is True
    assert data_import_available_for_viewport("pc", {"devicePlatform": "ios"}) is False
    assert data_import_available_for_viewport("pc", {"devicePlatform": "all"}) is True



def test_main_page_uses_viewport_render_paths() -> None:
    content = Path("src/pages/main_page.py").read_text(encoding="utf-8")

    assert "from src.viewport_component import viewport_info" in content
    assert "viewport = viewport_info()" in content
    assert 'key="main_viewport_info"' not in content
    assert "pixel_threshold=20" not in content
    assert "debounce_ms=500" not in content
    assert "require_ready=True" not in content
    assert 'loading_message="Loading layout..."' not in content
    assert "fallback_timeout_seconds=5" not in content
    assert "def main_viewport" not in content
    assert "MAIN_VIEWPORT_SESSION_KEY" not in content
    assert "def main_render_path" not in content
    assert 'render_path = "widescreen"' in content
    assert 'viewport.get("renderPath") == "mobile_portrait"' in content
    assert "def render_goal_actions(" in content
    assert "def render_participant_progress(" in content
    assert 'render_path == "mobile_portrait"' in content
    assert "st.columns([6, 2])" in content


def test_main_page_gates_apple_steps_import_by_viewport_device() -> None:
    content = Path("src/pages/main_page.py").read_text(encoding="utf-8")

    assert "data_import_available_for_viewport" in content
    assert 'health_data_settings.get("apple_steps_shortcut_availability", "ios")' in content
    assert "can_use_apple_steps_shortcut = uses_health_data and" in content
    assert "elif can_use_apple_steps_shortcut:" in content
    assert "render_goal_actions(" in content
    assert "viewport," in content


def test_main_page_reads_viewport_before_loading_data() -> None:
    content = Path("src/pages/main_page.py").read_text(encoding="utf-8")

    assert content.index("viewport = viewport_info()") < content.index("persistence.account_stats")
    assert "st.session_state" not in content
