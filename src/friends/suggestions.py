from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from typing import Any

from src.db.persistence import Persistence


def _pair(first_user_id: str, second_user_id: str) -> tuple[str, str]:
    return tuple(sorted((first_user_id, second_user_id)))


@dataclass(frozen=True)
class FriendSuggestionData:
    """The complete, page-level data set used to calculate friend suggestions."""

    user_id: str
    friends: list[dict[str, Any]]
    goals: list[dict[str, Any]]
    dismissed_pairs: set[tuple[str, str]]
    connected_pairs: set[tuple[str, str]]
    suggestions_by_pair: dict[tuple[str, str], list[dict[str, Any]]]


def load_friend_suggestion_data(
    persistence: Persistence,
    user_id: str,
    now: datetime | None = None,
) -> FriendSuggestionData:
    """Load relationship and suggestion records once for the Friends page."""
    friends = persistence.list_friends(user_id)
    scoped_user_ids = [user_id, *(friend["user_id"] for friend in friends)]
    friendships = persistence.list_active_friendships_for_users(scoped_user_ids)
    suggestions = persistence.list_friend_suggestions_for_users(scoped_user_ids)

    connected_pairs = {
        _pair(friendship["user_ids"][0], friendship["user_ids"][1])
        for friendship in friendships
        if len(friendship.get("user_ids", [])) == 2
    }
    suggestions_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for suggestion in suggestions:
        suggested_user_ids = suggestion.get("suggested_user_ids", [])
        if len(suggested_user_ids) != 2:
            continue
        suggestions_by_pair.setdefault(_pair(*suggested_user_ids), []).append(suggestion)

    return FriendSuggestionData(
        user_id=user_id,
        friends=friends,
        goals=persistence.list_goals_for_user(user_id, now=now),
        dismissed_pairs={tuple(pair) for pair in persistence.dismissed_friend_suggestion_pairs(user_id)},
        connected_pairs=connected_pairs,
        suggestions_by_pair=suggestions_by_pair,
    )


def friend_suggestion_candidates(data: FriendSuggestionData) -> list[dict[str, Any]]:
    friend_ids = {friend["user_id"] for friend in data.friends}
    if len(friend_ids) < 2:
        return []

    friend_by_id = {friend["user_id"]: friend for friend in data.friends}
    candidates = []
    seen_pairs: set[tuple[str, str]] = set()

    for goal in data.goals:
        goal_id = goal["id"]
        active_friend_participants = sorted(
            participant_id
            for participant_id, participant in goal.get("participants", {}).items()
            if participant_id in friend_ids and not participant.get("left_at")
        )
        for first_user_id, second_user_id in combinations(active_friend_participants, 2):
            pair = _pair(first_user_id, second_user_id)
            if pair in seen_pairs or pair in data.dismissed_pairs:
                continue
            seen_pairs.add(pair)
            if pair in data.connected_pairs:
                continue

            pair_suggestions = data.suggestions_by_pair.get(pair, [])
            if any(suggestion.get("status") == "pending" for suggestion in pair_suggestions):
                continue
            if any(
                suggestion.get("status") == "declined"
                and suggestion.get("suggested_by_user_id") == data.user_id
                and suggestion.get("source_goal_id") == goal_id
                for suggestion in pair_suggestions
            ):
                continue

            candidates.append(
                {
                    "goal_id": goal_id,
                    "goal_description": str(goal.get("description") or "a shared goal"),
                    "first_user": friend_by_id[first_user_id],
                    "second_user": friend_by_id[second_user_id],
                }
            )

    return candidates


def manual_friend_suggestion_options(data: FriendSuggestionData) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    friends = data.friends
    if len(friends) < 2:
        return friends, {}

    eligible_by_first_user_id: dict[str, list[dict[str, Any]]] = {friend["user_id"]: [] for friend in friends}
    for first_friend, second_friend in combinations(friends, 2):
        first_user_id = first_friend["user_id"]
        second_user_id = second_friend["user_id"]
        pair = _pair(first_user_id, second_user_id)
        if pair in data.connected_pairs:
            continue
        pair_suggestions = data.suggestions_by_pair.get(pair, [])
        if any(suggestion.get("status") == "pending" for suggestion in pair_suggestions):
            continue
        if any(
            suggestion.get("status") == "declined"
            and suggestion.get("suggested_by_user_id") == data.user_id
            and suggestion.get("source_goal_id") is None
            for suggestion in pair_suggestions
        ):
            continue
        eligible_by_first_user_id[first_user_id].append(second_friend)
        eligible_by_first_user_id[second_user_id].append(first_friend)

    return friends, eligible_by_first_user_id
