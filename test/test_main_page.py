from datetime import datetime
from pathlib import Path

from streamlit.testing.v1 import AppTest

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
    compact_goal_activity_html,
    mini_activity_styles,
    participant_sparkline_html,
    _participant_sparkline_values,
)
from src.db.persistence_helpers import STANDARD_REACTION_EMOTES
from src.assistant.core import AssistantContext
from src.assistant.director import AssistantDirector
from src.assistant.state import AssistantState
from src.assistant.stories import default_stories
from src.assistant.stories.tutorial import TUTORIAL_STORY_ID
from src.pages.main_page import (
    ONBOARDING_OFFER_DISMISSED_KNOWLEDGE_KEY,
    GOAL_ACTION_ERRORS_SESSION_KEY,
    GOAL_ACTION_RESULTS_SESSION_KEY,
    GOAL_PRESENTATION_SNAPSHOTS_SESSION_KEY,
    cleanup_goal_session_state,
    current_user_reaction_emote,
    dismiss_tutorial_offer,
    display_users_for_goal,
    goal_presentation_data,
    participant_goal_is_completed,
    participant_name_with_progress_html,
    participant_progress_label,
    participant_reaction_details,
    participant_reaction_summary,
    ordered_active_participant_ids,
    queue_site_break_for_goal_hit,
    should_render_balloons_for_goal_hit,
    should_render_site_break_for_goal_hit,
    submit_goal_progress,
    tutorial_has_never_started,
    visible_participant_ids,
    truncate_participant_name,
)


def test_submit_goal_progress_commits_once_and_stores_returned_goal(monkeypatch) -> None:
    calls = []
    session_state = {"current_goal-1": 2}
    updated_goal = {
        "id": "goal-1",
        "participants": {"alice": {"current": 4, "target": 10}},
    }
    monkeypatch.setattr("src.pages.main_page.st.session_state", session_state)
    monkeypatch.setattr(
        "src.pages.main_page.update_goal_progress_with_push",
        lambda *args, **kwargs: calls.append((args, kwargs)) or updated_goal,
    )
    monkeypatch.setattr("src.pages.main_page.get_notification_dispatcher", object)

    submit_goal_progress(
        object(),
        {"id": "goal-1"},
        {"current": 0, "target": 10},
        "alice",
        None,
        None,
        None,
        current=4,
    )

    assert len(calls) == 1
    assert calls[0][1]["current"] == 4
    assert calls[0][1]["dispatcher"] is not None
    assert session_state[GOAL_ACTION_RESULTS_SESSION_KEY]["goal-1"] == updated_goal
    assert "current_goal-1" not in session_state


def test_submit_goal_progress_rejects_conflicting_current_sources(monkeypatch) -> None:
    calls = []
    session_state = {"current_goal-1": 7}
    monkeypatch.setattr("src.pages.main_page.st.session_state", session_state)
    monkeypatch.setattr(
        "src.pages.main_page.update_goal_progress_with_push",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    submit_goal_progress(
        object(),
        {"id": "goal-1"},
        {"current": 0, "target": 10},
        "alice",
        None,
        None,
        None,
        current=4,
        current_key="current_goal-1",
    )

    assert calls == []
    assert session_state["current_goal-1"] == 7


def test_submit_goal_progress_preserves_input_when_persistence_rejects(monkeypatch) -> None:
    session_state = {"current_goal-1": 7}
    monkeypatch.setattr("src.pages.main_page.st.session_state", session_state)
    monkeypatch.setattr("src.pages.main_page.get_notification_dispatcher", object)

    def reject_update(*args, **kwargs) -> None:
        raise ValueError("rejected")

    monkeypatch.setattr(
        "src.pages.main_page.update_goal_progress_with_push",
        reject_update,
    )

    submit_goal_progress(
        object(),
        {"id": "goal-1"},
        {"current": 0, "target": 10},
        "alice",
        None,
        None,
        None,
        current_key="current_goal-1",
    )

    assert session_state["current_goal-1"] == 7
    assert "goal-1" in session_state[GOAL_ACTION_ERRORS_SESSION_KEY]


def test_save_callback_reads_the_submitted_number_input_from_session_state() -> None:
    app = AppTest.from_string(
        '''
import streamlit as st
from src.pages import main_page

def update(*args, **kwargs):
    st.session_state["persisted_current"] = kwargs["current"]
    return {
        "id": "goal-1",
        "participants": {"alice": {"current": kwargs["current"], "target": 10}},
    }

main_page.update_goal_progress_with_push = update
main_page.get_notification_dispatcher = object
goal = {"id": "goal-1"}
pending_goals = st.session_state.get(main_page.GOAL_ACTION_RESULTS_SESSION_KEY, {})
pending_goal = pending_goals.pop("goal-1", None)
participant = (
    pending_goal["participants"]["alice"]
    if pending_goal
    else {"current": 0, "target": 10}
)
st.number_input(
    "Current",
    value=participant["current"],
    key="current_goal-1",
)
st.button(
    "Save",
    on_click=main_page.submit_goal_progress,
    args=(object(), goal, participant, "alice", None, None, None),
    kwargs={"current_key": "current_goal-1"},
)
'''
    ).run()

    app.number_input[0].set_value(7)
    app.button[0].click().run()

    assert app.session_state["persisted_current"] == 7
    assert app.number_input[0].value == 7


def test_goal_presentation_snapshot_refreshes_after_ttl_and_cleans_inactive_state(monkeypatch) -> None:
    class Persistence:
        def __init__(self) -> None:
            self.user_calls = 0
            self.friend_calls = 0
            self.users = {"alice": {"name": "Alice"}, "charlie": {"name": "Charlie"}}
            self.friends = [{"user_id": "charlie", "name": "Charlie"}]

        def users_by_ids(self, user_ids):
            self.user_calls += 1
            return {user_id: self.users[user_id] for user_id in user_ids if user_id in self.users}

        def list_friends(self, user_id):
            self.friend_calls += 1
            return list(self.friends)

    session_state = {
        GOAL_PRESENTATION_SNAPSHOTS_SESSION_KEY: {
            "goal-1": {
                "loaded_at": 10.0,
                "users": {"alice": {"name": "Old Alice"}},
                "friends": [{"user_id": "bob", "name": "Bob"}],
            },
            "inactive": {"loaded_at": 10.0, "users": {}, "friends": []},
        },
        "goal_render_generation:inactive": 1,
    }
    monkeypatch.setattr("src.pages.main_page.st.session_state", session_state)
    persistence = Persistence()
    goal = {"id": "goal-1", "participants": {"alice": {}, "charlie": {}}}

    cached_users, cached_friends = goal_presentation_data(
        persistence, goal, "alice", current_time=14.9
    )
    fresh_users, fresh_friends = goal_presentation_data(
        persistence, goal, "alice", current_time=15.1
    )
    cleanup_goal_session_state({"goal-1"})

    assert cached_users == {"alice": {"name": "Old Alice"}}
    assert cached_friends[0]["user_id"] == "bob"
    assert fresh_users["charlie"]["name"] == "Charlie"
    assert fresh_friends[0]["user_id"] == "charlie"
    assert persistence.user_calls == 1
    assert persistence.friend_calls == 1
    assert "inactive" not in session_state[GOAL_PRESENTATION_SNAPSHOTS_SESSION_KEY]
    assert "goal_render_generation:inactive" not in session_state


def test_standard_reaction_emotes_exclude_remove_and_include_rocket() -> None:
    assert STANDARD_REACTION_EMOTES == ["🚀", "🔥", "👏", "💪", "❤️"]


def test_tutorial_has_never_started_only_for_a_fresh_assistant_state() -> None:
    assert tutorial_has_never_started(AssistantState()) is True
    assert tutorial_has_never_started(
        AssistantState(story="tutorial", scene="onboarding.welcome")
    ) is False
    assert tutorial_has_never_started(AssistantState(status="dismissed")) is False


def test_dismissing_the_goals_offer_keeps_assistant_onboarding_available() -> None:
    dismissed_offer = dismiss_tutorial_offer(AssistantState())

    assert dismissed_offer.status == "new"
    assert dismissed_offer.story is None
    assert dismissed_offer.knowledge[ONBOARDING_OFFER_DISMISSED_KNOWLEDGE_KEY] is True
    assert not tutorial_has_never_started(dismissed_offer)

    story = AssistantDirector(object(), default_stories()).story_dispatch(
        AssistantContext(
            user_id="alice",
            current_user={"user_id": "alice"},
            state=dismissed_offer,
            session_state={},
            current_page_key="assistant",
            now=datetime(2026, 8, 10, 12),
        ),
        None,
    )

    assert story is not None
    assert story.story_id == TUTORIAL_STORY_ID

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


def test_display_users_for_goal_uses_friend_profile_for_departed_participant() -> None:
    goal = {
        "participants": {
            "alice": {"left_at": None},
            "bob": {"left_at": "2026-06-01T10:00:00+00:00"},
        }
    }

    users = display_users_for_goal(
        goal,
        {"alice": {"name": "Alice"}, "bob": {"name": "Old Bob"}},
        [{"user_id": "bob", "name": "Bob"}],
        "alice",
    )

    assert users["alice"] == {"name": "Alice"}
    assert users["bob"] == {"user_id": "bob", "name": "Bob"}


def test_display_users_for_goal_hides_departed_non_friend_identity() -> None:
    goal = {"participants": {"bob": {"left_at": "2026-06-01T10:00:00+00:00"}}}

    users = display_users_for_goal(goal, {"bob": {"name": "Bob"}}, [], "alice")

    assert users["bob"] == {"name": "unknown"}


def test_display_users_for_goal_uses_friends_for_reactions_from_removed_participants() -> None:
    goal = {
        "participants": {
            "alice": {
                "left_at": None,
                "completion_reactions": {"2026-06-01": {"bob": {"emote": "👍"}}},
            }
        }
    }

    users = display_users_for_goal(
        goal,
        {"alice": {"name": "Alice"}},
        [{"user_id": "bob", "name": "Bob"}],
        "alice",
    )

    assert users["bob"] == {"user_id": "bob", "name": "Bob"}


def test_display_users_for_goal_hides_reactions_from_removed_non_friends() -> None:
    goal = {
        "participants": {
            "alice": {
                "left_at": None,
                "completion_reactions": {"2026-06-01": {"bob": {"emote": "👍"}}},
            }
        }
    }

    users = display_users_for_goal(goal, {"alice": {"name": "Alice"}}, [], "alice")

    assert users["bob"] == {"name": "unknown"}


def test_display_users_for_goal_hides_active_non_friend_reaction_sender_identity() -> None:
    goal = {
        "participants": {
            "alice": {
                "left_at": None,
                "completion_reactions": {"2026-06-01": {"charlie": {"emote": "👍"}}},
            },
            "charlie": {"left_at": None},
        }
    }

    users = display_users_for_goal(
        goal,
        {"alice": {"name": "Alice"}, "charlie": {"name": "Charlie", "email": "charlie@example.com"}},
        [],
        "alice",
    )

    assert users["charlie"] != {"name": "Charlie", "email": "charlie@example.com"}
    assert "email" not in users["charlie"]


def test_participant_progress_label_uses_compact_current_target() -> None:
    assert participant_progress_label(0, 10, False) == "0/10"


def test_balloons_are_only_eligible_for_a_new_completion_over_double_target() -> None:
    previous = {"current": 9, "target": 10}

    assert should_render_balloons_for_goal_hit(previous, {"current": 21, "target": 10}, random_value=0.09)
    assert not should_render_balloons_for_goal_hit(previous, {"current": 20, "target": 10}, random_value=0.01)
    assert not should_render_balloons_for_goal_hit(previous, {"current": 21, "target": 10}, random_value=0.10)
    assert not should_render_balloons_for_goal_hit({"current": 10, "target": 10}, {"current": 21, "target": 10}, random_value=0.01)


def test_site_break_requires_an_unskipped_crossing_at_least_two_times_target() -> None:
    previous = {"current": 9, "target": 10, "skipped": False}

    assert should_render_site_break_for_goal_hit(
        previous, {"current": 20, "target": 10, "skipped": False}, random_value=0.19
    )
    assert not should_render_site_break_for_goal_hit(
        previous, {"current": 20, "target": 10, "skipped": False}, random_value=0.20
    )
    assert should_render_site_break_for_goal_hit(
        {"current": 10, "target": 10}, {"current": 20, "target": 10}, random_value=0
    )
    assert not should_render_site_break_for_goal_hit(
        previous, {"current": 19, "target": 10, "skipped": False}, random_value=0
    )
    assert not should_render_site_break_for_goal_hit(
        {"current": 20, "target": 10}, {"current": 21, "target": 10}, random_value=0
    )
    assert not should_render_site_break_for_goal_hit(
        previous, {"current": 20, "target": 10, "skipped": True}, random_value=0
    )


def test_site_break_does_not_claim_the_daily_effect_when_it_will_not_render(monkeypatch) -> None:
    class Persistence:
        claim_calls = 0

        def claim_site_break_effect(self, user_id: str, now=None) -> bool:
            self.claim_calls += 1
            return True

    persistence = Persistence()
    previous = {"current": 19, "target": 10, "skipped": False}
    updated_goal = {
        "id": "goal-1",
        "participants": {"alice": {"current": 20, "target": 10, "skipped": False}},
    }
    monkeypatch.setattr("src.pages.main_page.should_render_site_break_for_goal_hit", lambda *_: False)

    assert not queue_site_break_for_goal_hit(persistence, previous, updated_goal, "alice", now=None)
    assert persistence.claim_calls == 0


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


def test_participant_sparkline_keeps_zero_at_the_chart_baseline() -> None:
    participant = {
        "current": 3,
        "target": 10,
        "period_outcomes": {
            "2026-06-08": {"current": 2, "target": 10},
            "2026-06-09": {"current": 4, "target": 10},
        },
    }

    html = participant_sparkline_html(
        _goal("daily", participant=participant),
        participant,
        now=_at("2026-06-10T12:00:00"),
        days=3,
    )
    line_points = html.split("<polyline", 1)[1].split("points='", 1)[1].split("'", 1)[0].split()

    first_y = float(line_points[0].split(",")[1])
    assert first_y == 11.0


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
    assert "mini-activity-dot-skipped" not in html


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


def test_compact_goal_activity_daily_x_per_week_valid_skip_uses_x_marker() -> None:
    participant = {
        "current": 0,
        "target": 10,
        "skipped": True,
        "period_outcomes": {"2026-06-01": {"completed": False, "skipped": True, "fulfilled": True}},
    }
    goal = _goal("daily_x_per_week", required_periods=5, participant=participant)
    html = compact_goal_activity_html(goal, participant, now=_at("2026-06-03T12:00:00"))

    assert html.count("mini-activity-dot-skipped") == 2
    assert f"background:{ACTIVITY_COLORS[4]}" not in html

    goal["required_periods"] = 6
    html = compact_goal_activity_html(goal, participant, now=_at("2026-06-03T12:00:00"))

    assert html.count("mini-activity-dot-skipped") == 2
    assert html.count(f"background:{ACTIVITY_COLORS[0]}") == 3
    assert html.count(f"background:{FUTURE_ACTIVITY_COLOR}") == 4


def test_compact_goal_activity_daily_x_per_week_skippable_current_day_uses_x_marker() -> None:
    participant = {
        "current": 0,
        "target": 10,
        "skipped": False,
        "period_outcomes": {},
    }
    html = compact_goal_activity_html(
        _goal("daily_x_per_week", required_periods=5, participant=participant),
        participant,
        now=_at("2026-06-03T12:00:00"),
    )

    current_dot = html.split("title='Wednesday'", 1)[0].rsplit("<span", 1)[1]
    assert "mini-activity-dot-skipped" in current_dot
    assert f"background:{ACTIVITY_COLORS[4]}" not in current_dot


def test_compact_goal_activity_daily_x_per_week_unfulfilled_skip_uses_x_marker() -> None:
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

    assert "mini-activity-dot-skipped" in html
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

    assert "from src.viewport_component import viewport_info" not in content
    assert "viewport = viewport_info(require_ready=False)" not in content
    assert "viewport: dict | None = None" in content
    assert 'key="main_viewport_info"' not in content
    assert "pixel_threshold=20" not in content
    assert "debounce_ms=500" not in content
    assert "require_ready=True" not in content
    assert 'loading_message="Loading layout..."' not in content
    assert "fallback_timeout_seconds=5" not in content
    assert "def main_viewport" not in content
    assert "MAIN_VIEWPORT_SESSION_KEY" not in content
    assert "def main_render_path" not in content
    assert "@st.fragment" in content
    assert "def render_goal_card(" in content
    assert "def _current_goal_for_user(" not in content
    assert "persistence.get_goal_for_user(goal_id, user_id, now=now)" in content
    assert 'render_path = "widescreen"' in content
    assert 'viewport.get("renderPath") == "widescreen"' in content
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
    content = Path("streamlit_app.py").read_text(encoding="utf-8")

    assert "from src.app_notifications import flush_startup_notifications, queue_user_notification" in content
    assert "from src.viewport_component import viewport_info" in content
    assert content.index("viewport = viewport_info(require_ready=False)") < content.index("flush_startup_notifications(viewport_ready=isinstance(viewport, dict))")
    assert content.index("flush_startup_notifications(viewport_ready=isinstance(viewport, dict))") < content.index("render_main(")


def test_main_page_goal_actions_use_fragment_scoped_reruns() -> None:
    content = Path("src/pages/main_page.py").read_text(encoding="utf-8")

    assert 'st.rerun(scope="fragment")' in content
    assert 'st.rerun(scope="app")' in content
    assert "st.rerun()" not in content
    actions = content[content.index("def render_goal_actions("):content.index("def render_participant_progress(")]
    assert "on_click=submit_goal_progress" in actions
    assert 'st.rerun(scope="fragment")' not in actions


def test_main_page_site_break_stops_after_the_goal_header() -> None:
    content = Path("src/pages/main_page.py").read_text(encoding="utf-8")

    assert "SITE_BREAK_GOAL_ID_SESSION_KEY" in content
    assert "should_render_site_break_for_goal_hit" in content
    assert "def render_site_break_error" in content
    assert "st.exception(error)" in content
    assert "def _inspect_suspiciously_high_completion_rate" in content
    assert "def _wake_achievement_gremlin" in content
    assert "raise AchievementGremlinError" in content
    assert "Achievement gremlin reports dangerously impressive behavior." in content
    assert ".goal--too-motivated" in content
    assert 'st.markdown(f"```css\\n{SITE_BREAK_CSS}\\n```' in content
    assert "def render_site_break_toasts" in content
    assert 'icon=":material/support_agent:"' in content
    assert "sleep(7)" in content
    assert "sleep(5)" in content
    assert "Try to reload, maybe" in content
    assert "if site_break_rendered:\n            return" in content


def test_participant_goal_is_completed_requires_completed_unskipped_progress() -> None:
    assert participant_goal_is_completed({"current": 10, "target": 10, "skipped": False}) is True
    assert participant_goal_is_completed({"current": 9, "target": 10, "skipped": False}) is False
    assert participant_goal_is_completed({"current": 10, "target": 10, "skipped": True}) is False


def test_participant_reaction_summary_is_empty_without_current_period_reactions() -> None:
    participant = {"current": 10, "target": 10, "skipped": False, "period_start": "2026-06-01T00:00:00+02:00"}
    goal = _goal("daily", participant=participant)

    assert participant_reaction_summary(participant, goal, now=_at("2026-06-01T12:00:00")) == []


def test_participant_reaction_summary_aggregates_current_period_emotes() -> None:
    participant = {
        "current": 10,
        "target": 10,
        "skipped": False,
        "period_start": "2026-06-02T00:00:00+02:00",
        "completion_reactions": {
            "2026-06-01": {"dana": {"emote": "🔥"}},
            "2026-06-02": {
                "bob": {"emote": "👍"},
                "charlie": {"emote": "🎉"},
                "dana": {"emote": "👍"},
                "ignored": {"emote": "unsupported"},
            },
        },
    }
    goal = _goal("daily", participant=participant)

    assert participant_reaction_summary(participant, goal, now=_at("2026-06-02T12:00:00")) == [("👍", 2), ("🎉", 1)]


def test_current_user_reaction_emote_returns_current_period_reaction() -> None:
    participant = {
        "current": 10,
        "target": 10,
        "skipped": False,
        "period_start": "2026-06-02T00:00:00+02:00",
        "completion_reactions": {
            "2026-06-01": {"bob": {"emote": "🔥"}},
            "2026-06-02": {"bob": {"emote": "👍"}},
        },
    }
    goal = _goal("daily", participant=participant)

    assert current_user_reaction_emote(participant, goal, "bob", now=_at("2026-06-02T12:00:00")) == "👍"
    assert current_user_reaction_emote(participant, goal, "charlie", now=_at("2026-06-02T12:00:00")) == ""


def test_participant_reaction_details_include_emote_and_sender_name() -> None:
    participant = {
        "current": 10,
        "target": 10,
        "skipped": False,
        "period_start": "2026-06-02T00:00:00+02:00",
        "completion_reactions": {
            "2026-06-02": {
                "charlie": {"emote": "🎉"},
                "bob": {"emote": "👍"},
                "dana": {"emote": "👍"},
                "ignored": {"emote": "unsupported"},
            },
        },
    }
    goal = _goal("daily", participant=participant)
    users = {
        "bob": {"name": "Bob"},
        "charlie": {"name": "Charlie"},
        "dana": {"email": "dana@example.com"},
    }

    assert participant_reaction_details(participant, goal, users, now=_at("2026-06-02T12:00:00")) == [
        {"emote": "👍", "name": "Bob"},
        {"emote": "👍", "name": "dana@example.com"},
        {"emote": "🎉", "name": "Charlie"},
    ]


def test_main_page_uses_slim_component_picker_for_active_friend_rows() -> None:
    content = Path("src/pages/main_page.py").read_text(encoding="utf-8")

    assert "participant_reaction_row(" in content
    assert "participant_id != current_user_id" in content
    assert "not skipped" in content
    assert "participant_goal_is_completed(participant)" not in content
    assert 'open_picker=st.session_state.get("participant_reaction_open_row") == row_id' in content
    assert 'st.popover("React")' not in content
    assert "set_goal_completion_reaction" in content
    assert 'action == "close"' in content
    assert 'st.rerun(scope="fragment")' in content


def test_participant_reaction_component_build_exists_with_inline_picker() -> None:
    content = Path("src/reaction_component/frontend/build/index.html").read_text(encoding="utf-8")

    assert "streamlit:componentReady" in content
    assert "streamlit:render" in content
    assert "streamlit:setComponentValue" in content
    assert "participant-reaction-line" in content
    assert "participant-progress-meta" in content
    assert "participant-reaction-summary" in content
    assert "--streamlit-secondary-background-color" in content
    assert "secondaryBackgroundColor" in content
    assert "position: absolute" in content
    assert "participant-reaction-picker" in content
    assert "participant-reaction-detail-menu" in content
    assert "participant-reaction-detail-row" in content
    assert "participant-reaction-summary-entry" in content
    assert "summary.slice(0, 2)" in content
    assert "participant-reaction-summary-more" in content
    assert "function clampFloatingMenu" in content
    assert "getBoundingClientRect()" in content
    assert "translateX" in content
    assert "participant-reaction-more" in content
    assert "Remove reaction" in content
    assert ">Remove</button>" in content
    assert "current_user_reaction_emote" in content
    assert "filter((emote) => String(emote" in content
    assert "participant-reaction-all" in content
    assert "overflow-y: auto" in content
    assert "standard_emotes" in content
    assert "reaction_details" in content
    assert "mini-activity-dot-current" in content
    assert "mini-activity-dot-skipped::before" in content
    assert "mini-activity-dot-skipped::after" in content
    assert "width: 0.5rem" in content
    assert "height: 1px" in content
    assert "background: #4B5563" in content
    assert "transform: translate(-50%, -50%) rotate(45deg)" in content
    assert 'action: "toggle"' in content
    assert 'action: "react"' in content
    assert 'action: "close"' in content
    assert "window.parent.document.addEventListener" in content
    assert "open = Boolean(args.open_picker)" in content
    assert "React to this goal" in content
