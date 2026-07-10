"""Document-store persistence behavior for Dogether backends."""
from __future__ import annotations

import copy
import threading
from datetime import datetime
from typing import Any

from .persistence_helpers import (
    _active_friendship,
    _days_using_app,
    _find_user_by_email,
    _friendship_id,
    _goal_active_for_user,
    _iso,
    _new_id,
    _now,
    _parse_dt,
    _period_start,
    _record_period_outcome,
    _refresh_activity_day,
    _schedule,
    _next_period_start,
    _user_stats,
    normalize_email,
)


class DocumentPersistence:
    """Shared domain operations for backends that read/write an app store document."""

    _lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        raise NotImplementedError

    def _write(self, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def upsert_user(
        self,
        user_id: str,
        email: str,
        name: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_iso = _iso(now)
        normalized_email = normalize_email(email)
        with self._lock:
            data = self._read()
            existing = data["users"].get(user_id, {})
            user = {
                "user_id": user_id,
                "email": normalized_email,
                "name": name.strip() or normalized_email,
                "created_at": existing.get("created_at", now_iso),
                "last_seen_at": now_iso,
            }
            data["users"][user_id] = user
            self._write(data)
            return user

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._read()["users"].get(user_id)

    def users_by_ids(self, user_ids: list[str]) -> dict[str, dict[str, Any]]:
        with self._lock:
            users = self._read()["users"]
            return {user_id: users[user_id] for user_id in user_ids if user_id in users}

    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        normalized_email = normalize_email(email)
        with self._lock:
            for user in self._read()["users"].values():
                if user.get("email") == normalized_email:
                    return user
        return None

    def list_users(self) -> list[dict[str, Any]]:
        with self._lock:
            users = list(self._read()["users"].values())
        return sorted(users, key=lambda user: (user.get("name", ""), user.get("email", "")))

    def debug_time_offset_seconds(self) -> int:
        with self._lock:
            return int(self._read().get("debug", {}).get("time_offset_seconds", 0))

    def add_debug_time_offset(self, seconds: int) -> int:
        with self._lock:
            data = self._read()
            debug = data.setdefault("debug", {})
            debug["time_offset_seconds"] = max(0, int(debug.get("time_offset_seconds", 0)) + int(seconds))
            self._write(data)
            return int(debug["time_offset_seconds"])

    def reset_debug_time_offset(self) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("debug", {})["time_offset_seconds"] = 0
            self._write(data)

    def create_friend_invite(
        self,
        from_user_id: str,
        from_email: str,
        to_email: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        to_email = normalize_email(to_email)
        from_email = normalize_email(from_email)
        if not to_email or "@" not in to_email:
            raise ValueError("Enter a valid email address.")
        if to_email == from_email:
            raise ValueError("You cannot invite yourself.")

        now_iso = _iso(now)
        with self._lock:
            data = self._read()
            target_user = _find_user_by_email(data, to_email)
            if not target_user:
                raise ValueError("No user found with that email address.")
            if _active_friendship(data, from_user_id, target_user["user_id"]):
                raise ValueError("You are already friends with that user.")

            for invite in data["friend_invites"].values():
                if (
                    invite.get("from_user_id") == from_user_id
                    and invite.get("to_email") == to_email
                    and invite.get("status") == "pending"
                ):
                    if invite.get("to_user_id") != target_user["user_id"]:
                        invite["to_user_id"] = target_user["user_id"]
                        self._write(data)
                    return invite

            invite_id = _new_id("invite")
            invite = {
                "id": invite_id,
                "from_user_id": from_user_id,
                "from_email": from_email,
                "to_email": to_email,
                "to_user_id": target_user["user_id"],
                "status": "pending",
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            data["friend_invites"][invite_id] = invite
            self._write(data)
            return invite

    def incoming_friend_invites(self, user_email: str, user_id: str | None = None) -> list[dict[str, Any]]:
        user_email = normalize_email(user_email)
        with self._lock:
            invites = [
                invite
                for invite in self._read()["friend_invites"].values()
                if invite.get("status") == "pending"
                and (
                    (user_id is not None and invite.get("to_user_id") == user_id)
                    or invite.get("to_email") == user_email
                )
            ]
        return sorted(invites, key=lambda invite: invite["created_at"])

    def outgoing_friend_invites(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read()
            invites = [
                invite
                for invite in data["friend_invites"].values()
                if invite.get("from_user_id") == user_id
                and invite.get("status") == "pending"
                and (
                    invite.get("to_user_id") in data["users"]
                    or _find_user_by_email(data, invite.get("to_email", "")) is not None
                )
            ]
        return sorted(invites, key=lambda invite: invite["created_at"])

    def respond_friend_invite(
        self,
        invite_id: str,
        user_id: str,
        user_email: str,
        approve: bool,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_iso = _iso(now)
        user_email = normalize_email(user_email)
        with self._lock:
            data = self._read()
            invite = data["friend_invites"].get(invite_id)
            if not invite or invite.get("status") != "pending":
                raise ValueError("This invite is no longer pending.")
            invite_to_user_id = invite.get("to_user_id")
            if invite_to_user_id and invite_to_user_id != user_id:
                raise ValueError("This invite is not addressed to your account.")
            if not invite_to_user_id and invite.get("to_email") != user_email:
                raise ValueError("This invite is not addressed to your account.")

            invite["status"] = "accepted" if approve else "declined"
            invite["updated_at"] = now_iso
            if approve:
                friendship_id = _friendship_id(invite["from_user_id"], user_id)
                from_user = data["users"].get(invite["from_user_id"], {})
                to_user = data["users"].get(user_id, {})
                data["friendships"][friendship_id] = {
                    "id": friendship_id,
                    "user_ids": sorted([invite["from_user_id"], user_id]),
                    "emails": sorted(
                        [
                            normalize_email(from_user.get("email", invite["from_email"])),
                            normalize_email(to_user.get("email", user_email)),
                        ]
                    ),
                    "active": True,
                    "created_at": data["friendships"].get(friendship_id, {}).get("created_at", now_iso),
                    "updated_at": now_iso,
                }
                del data["friend_invites"][invite_id]
            self._write(data)
            return invite

    def list_friends(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read()
            friends = []
            for friendship in data["friendships"].values():
                if not friendship.get("active") or user_id not in friendship.get("user_ids", []):
                    continue
                friend_id = next(uid for uid in friendship["user_ids"] if uid != user_id)
                user = data["users"].get(friend_id, {"user_id": friend_id, "email": "", "name": friend_id})
                friends.append(user)
        return sorted(friends, key=lambda user: (user.get("name", ""), user.get("email", "")))

    def remove_friend(self, user_id: str, friend_id: str, now: datetime | None = None) -> None:
        with self._lock:
            data = self._read()
            friendship_id = _friendship_id(user_id, friend_id)
            friendship = data["friendships"].get(friendship_id)
            if not friendship or not friendship.get("active"):
                raise ValueError("That friendship is not active.")
            friendship["active"] = False
            friendship["updated_at"] = _iso(now)
            self._write(data)

    def create_goal(
        self,
        created_by: str,
        description: str,
        schedule_class: str,
        required_periods: int,
        friend_user_ids: list[str],
        target: int,
        current: int = 0,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        description = description.strip()
        if not description:
            raise ValueError("Goal description is required.")
        schedule = _schedule(schedule_class, required_periods)
        target = max(1, int(target))
        current = max(0, int(current))
        now_dt = _now(now)
        now_iso = _iso(now_dt)
        period_start = _period_start(now_dt, schedule["base"]).isoformat()

        with self._lock:
            data = self._read()
            active_friend_ids = {friend["user_id"] for friend in self.list_friends(created_by)}
            invalid = sorted(set(friend_user_ids) - active_friend_ids)
            if invalid:
                raise ValueError("Goals can only be shared with accepted friends.")

            participant_ids = [created_by, *sorted(set(friend_user_ids))]
            goal_id = _new_id("goal")
            goal = {
                "id": goal_id,
                "description": description,
                "schedule_class": schedule_class,
                "required_periods": schedule["required_periods"],
                "created_by": created_by,
                "participant_user_ids": participant_ids,
                "participants": {
                    participant_id: {
                        "target": target,
                        "current": current if participant_id == created_by else 0,
                        "period_start": period_start,
                        "completion_streak": 0,
                        "completion_notifications_enabled": True,
                        "skipped": False,
                        "period_outcomes": {},
                        "left_at": None,
                    }
                    for participant_id in participant_ids
                },
                "created_at": now_iso,
                "archived_at": None,
            }
            data["goals"][goal_id] = goal
            for participant_id in participant_ids:
                _refresh_activity_day(data, participant_id, now_dt.date())
            self._write(data)
            return goal

    def list_goals_for_user(self, user_id: str, now: datetime | None = None) -> list[dict[str, Any]]:
        self.rollover_periods(now)
        with self._lock:
            goals = [
                goal
                for goal in self._read()["goals"].values()
                if _goal_active_for_user(goal, user_id)
            ]
        return sorted(goals, key=lambda goal: goal["created_at"])

    def add_goal_friends(
        self,
        goal_id: str,
        user_id: str,
        friend_user_ids: list[str],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self.rollover_periods(now)
        now_dt = _now(now)
        with self._lock:
            data = self._read()
            goal = data["goals"].get(goal_id)
            if not goal or not _goal_active_for_user(goal, user_id):
                raise ValueError("Goal is not active for this user.")

            active_friend_ids = {friend["user_id"] for friend in self.list_friends(user_id)}
            requested_friend_ids = set(friend_user_ids)
            invalid = sorted(requested_friend_ids - active_friend_ids)
            if invalid:
                raise ValueError("Goals can only be shared with accepted friends.")

            existing_participant_ids = set(goal.get("participants", {}))
            new_participant_ids = sorted(requested_friend_ids - existing_participant_ids)
            if not new_participant_ids:
                return goal

            schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
            period_start = _period_start(now_dt, schedule["base"]).isoformat()
            inviter = goal["participants"][user_id]
            target = max(1, int(inviter.get("target", 1)))

            for participant_id in new_participant_ids:
                goal["participants"][participant_id] = {
                    "target": target,
                    "current": 0,
                    "period_start": period_start,
                    "completion_streak": 0,
                    "completion_notifications_enabled": True,
                    "skipped": False,
                    "period_outcomes": {},
                    "left_at": None,
                }

            goal["participant_user_ids"] = [
                *goal.get("participant_user_ids", []),
                *[
                    participant_id
                    for participant_id in new_participant_ids
                    if participant_id not in goal.get("participant_user_ids", [])
                ],
            ]
            for participant_id in new_participant_ids:
                _refresh_activity_day(data, participant_id, now_dt.date())
            self._write(data)
            return goal

    def update_goal_progress(
        self,
        goal_id: str,
        user_id: str,
        current: int | None = None,
        target: int | None = None,
        delta: int = 0,
        skipped: bool | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self.rollover_periods(now)
        now_dt = _now(now)
        today_key = now_dt.date().isoformat()
        with self._lock:
            data = self._read()
            goal = data["goals"].get(goal_id)
            if not goal or not _goal_active_for_user(goal, user_id):
                raise ValueError("Goal is not active for this user.")
            participant = goal["participants"][user_id]
            before_current = max(0, int(participant.get("current", 0)))
            before_target = max(1, int(participant.get("target", 1)))
            was_complete = before_current >= before_target
            if target is not None:
                participant["target"] = max(1, int(target))
            if skipped is not None:
                participant["skipped"] = bool(skipped)
                if skipped:
                    participant["current"] = 0
            if current is not None:
                participant["current"] = max(0, int(current))
                participant["skipped"] = False
            elif delta:
                participant["current"] = max(0, int(participant.get("current", 0)) + int(delta))
                participant["skipped"] = False
            after_current = max(0, int(participant.get("current", 0)))
            after_target = max(1, int(participant.get("target", 1)))
            is_complete = after_current >= after_target
            notification_event = None
            if (
                is_complete
                and not was_complete
                and participant.get("last_completion_notification_day") != today_key
            ):
                participant["last_completion_notification_day"] = today_key
                notification_event = {
                    "type": "goal_completed",
                    "goal_id": goal_id,
                    "completed_by_user_id": user_id,
                    "day": today_key,
                }
            _refresh_activity_day(data, user_id, now_dt.date())
            self._write(data)
            result = copy.deepcopy(goal)
            if notification_event:
                result["_notification_event"] = notification_event
            return result

    def set_goal_completion_notifications(
        self,
        goal_id: str,
        user_id: str,
        enabled: bool,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self.rollover_periods(now)
        with self._lock:
            data = self._read()
            goal = data["goals"].get(goal_id)
            if not goal or not _goal_active_for_user(goal, user_id):
                raise ValueError("Goal is not active for this user.")
            goal["participants"][user_id]["completion_notifications_enabled"] = bool(enabled)
            self._write(data)
            return goal

    def set_health_data_workflow_target(
        self,
        goal_id: str | None,
        user_id: str,
        enabled: bool,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        self.rollover_periods(now)
        now_iso = _iso(now)
        with self._lock:
            data = self._read()
            selected_goal = None
            if enabled:
                if not goal_id:
                    raise ValueError("Choose a goal for Apple Health import.")
                selected_goal = data["goals"].get(goal_id)
                if not selected_goal or not _goal_active_for_user(selected_goal, user_id):
                    raise ValueError("Goal is not active for this user.")

            for goal in data["goals"].values():
                participant = goal.get("participants", {}).get(user_id)
                if not isinstance(participant, dict):
                    continue
                workflow = participant.get("health_data_workflow")
                if isinstance(workflow, dict) and workflow.get("enabled"):
                    workflow["enabled"] = False
                    workflow["disabled_at"] = now_iso

            if enabled and selected_goal is not None:
                participant = selected_goal["participants"][user_id]
                participant["health_data_workflow"] = {
                    "enabled": True,
                    "provider": "apple_health_steps",
                    "configured_at": now_iso,
                }

            self._write(data)
            return copy.deepcopy(selected_goal) if selected_goal is not None else None

    def leave_goal(self, goal_id: str, user_id: str, now: datetime | None = None) -> None:
        with self._lock:
            data = self._read()
            goal = data["goals"].get(goal_id)
            if not goal or user_id not in goal.get("participants", {}):
                raise ValueError("Goal not found.")
            now_dt = _now(now)
            del goal["participants"][user_id]
            goal["participant_user_ids"] = [
                participant_id
                for participant_id in goal.get("participant_user_ids", [])
                if participant_id != user_id
            ]
            if not goal["participants"]:
                del data["goals"][goal_id]
            _refresh_activity_day(data, user_id, now_dt.date())
            self._write(data)

    def rollover_periods(self, now: datetime | None = None) -> None:
        now_dt = _now(now)
        with self._lock:
            data = self._read()
            changed = False
            for goal in data["goals"].values():
                schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
                current_start = _period_start(now_dt, schedule["base"])
                for user_id, participant in goal.get("participants", {}).items():
                    if participant.get("left_at"):
                        continue
                    stored_start = _parse_dt(participant.get("period_start")) or current_start
                    stored_start = _period_start(stored_start, schedule["base"])
                    while stored_start < current_start:
                        period_end = _next_period_start(stored_start, schedule["base"])
                        fulfilled = _record_period_outcome(goal, participant, stored_start)
                        participant["completion_streak"] = (
                            max(0, int(participant.get("completion_streak", 0))) + 1
                            if fulfilled
                            else 0
                        )
                        _refresh_activity_day(data, user_id, stored_start.date())
                        participant["current"] = 0
                        participant["skipped"] = False
                        participant["period_start"] = period_end.isoformat()
                        stored_start = period_end
                        changed = True
                    if changed:
                        _refresh_activity_day(data, user_id, now_dt.date())
            if changed:
                self._write(data)

    def account_stats(self, user_id: str, now: datetime | None = None) -> dict[str, Any]:
        self.rollover_periods(now)
        now_dt = _now(now)
        with self._lock:
            data = self._read()
            _refresh_activity_day(data, user_id, now_dt.date())
            self._write(data)
            active_goals = sum(1 for goal in data["goals"].values() if _goal_active_for_user(goal, user_id))
            friend_count = len(
                [
                    friendship
                    for friendship in data["friendships"].values()
                    if friendship.get("active") and user_id in friendship.get("user_ids", [])
                ]
            )
            user = data["users"].get(user_id, {})
            stats = _user_stats(data, user_id)
            month_prefix = f"{now_dt.year:04d}-{now_dt.month:02d}-"
            month_days = [
                day
                for date_key, day in stats.get("activity_days", {}).items()
                if date_key.startswith(month_prefix)
            ]
            active_goal_days = sum(max(0, int(day.get("active_goals", 0))) for day in month_days)
            fulfilled_goal_days = sum(max(0, int(day.get("fulfilled_goals", 0))) for day in month_days)
            completion_rate = round((fulfilled_goal_days / active_goal_days) * 100, 1) if active_goal_days else 0.0
            return {
                "active_goals": active_goals,
                "friend_count": friend_count,
                "days_using_app": _days_using_app(user, now_dt),
                "completion_rate": completion_rate,
                "activity_days": dict(sorted(stats.get("activity_days", {}).items())),
            }

    def raw_data(self) -> dict[str, Any]:
        with self._lock:
            return self._read()