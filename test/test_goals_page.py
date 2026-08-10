from src.pages.goals_page import _addable_friend_options


def test_departed_goal_participant_can_be_invited_again() -> None:
    goal = {
        "participants": {
            "active": {"left_at": None},
            "departed": {"left_at": "2026-07-27T09:00:00+00:00"},
        }
    }
    friends = {"Active friend": "active", "Former participant": "departed"}

    options = _addable_friend_options(goal, friends)

    assert options == {"Former participant": "departed"}
