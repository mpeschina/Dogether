from __future__ import annotations

from datetime import datetime
from itertools import combinations
from typing import Any

from src.db.persistence import Persistence


def friend_suggestion_candidates(
    persistence: Persistence,
    user_id: str,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    friends = persistence.list_friends(user_id)
    friend_ids = {friend["user_id"] for friend in friends}
    if len(friend_ids) < 2:
        return []

    friend_by_id = {friend["user_id"]: friend for friend in friends}
    friend_friend_ids: dict[str, set[str]] = {}
    candidates = []
    seen_pairs: set[tuple[str, str]] = set()

    for goal in persistence.list_goals_for_user(user_id, now=now):
        goal_id = goal["id"]
        active_friend_participants = sorted(
            participant_id
            for participant_id, participant in goal.get("participants", {}).items()
            if participant_id in friend_ids and not participant.get("left_at")
        )
        for first_user_id, second_user_id in combinations(active_friend_participants, 2):
            pair = tuple(sorted([first_user_id, second_user_id]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            if first_user_id not in friend_friend_ids:
                friend_friend_ids[first_user_id] = {
                    friend["user_id"]
                    for friend in persistence.list_friends(first_user_id)
                }
            if second_user_id in friend_friend_ids[first_user_id]:
                continue

            pair_suggestions = persistence.list_friend_suggestions_for_pair(first_user_id, second_user_id)
            if any(suggestion.get("status") == "pending" for suggestion in pair_suggestions):
                continue
            if any(
                suggestion.get("status") == "declined"
                and suggestion.get("suggested_by_user_id") == user_id
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


def manual_friend_suggestion_options(
    persistence: Persistence,
    user_id: str,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    friends = persistence.list_friends(user_id)
    friend_ids = {friend["user_id"] for friend in friends}
    if len(friend_ids) < 2:
        return friends, {}

    eligible_by_first_user_id: dict[str, list[dict[str, Any]]] = {}
    for first_friend in friends:
        first_user_id = first_friend["user_id"]
        connected_to_first = {
            friend["user_id"]
            for friend in persistence.list_friends(first_user_id)
        }
        eligible_second_friends = []

        for second_friend in friends:
            second_user_id = second_friend["user_id"]
            if second_user_id == first_user_id:
                continue
            if second_user_id in connected_to_first:
                continue

            pair_suggestions = persistence.list_friend_suggestions_for_pair(first_user_id, second_user_id)
            if any(suggestion.get("status") == "pending" for suggestion in pair_suggestions):
                continue
            if any(
                suggestion.get("status") == "declined"
                and suggestion.get("suggested_by_user_id") == user_id
                and suggestion.get("source_goal_id") is None
                for suggestion in pair_suggestions
            ):
                continue

            eligible_second_friends.append(second_friend)

        eligible_by_first_user_id[first_user_id] = eligible_second_friends

    return friends, eligible_by_first_user_id


