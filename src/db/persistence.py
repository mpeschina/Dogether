"""JSON persistence and domain operations for Dogether."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol
from zoneinfo import ZoneInfo

import streamlit as st

APP_ZONE = ZoneInfo("Europe/Berlin")
UTC = timezone.utc
SCHEDULES = {
    "daily": {"label": "Daily", "base": "day", "required_periods": 1, "aggregate": "day"},
    "weekly": {"label": "Weekly", "base": "week", "required_periods": 1, "aggregate": "week"},
    "daily_x_per_week": {
        "label": "Daily with X per week",
        "base": "day",
        "required_periods": 5,
        "aggregate": "week",
    },
    "weekly_x_per_month": {
        "label": "Weekly with X per month",
        "base": "week",
        "required_periods": 3,
        "aggregate": "month",
    },
}


class Persistence(Protocol):
    def upsert_user(self, user_id: str, email: str, name: str, now: datetime | None = None) -> dict[str, Any]: ...

    def list_goals_for_user(self, user_id: str, now: datetime | None = None) -> list[dict[str, Any]]: ...


class JsonPersistence:
    """Atomic JSON persistence for the Streamlit prototype."""

    _lock = threading.RLock()

    def __init__(self, path: str | Path = "data/users.json") -> None:
        self.path = Path(path)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return _empty_store()

        with self.path.open(encoding="utf-8") as file:
            loaded = json.load(file)

        if not isinstance(loaded, dict):
            return _empty_store()
        return _normalise_store(loaded)

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

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
            if target_user and _active_friendship(data, from_user_id, target_user["user_id"]):
                raise ValueError("You are already friends with that user.")

            for invite in data["friend_invites"].values():
                if (
                    invite.get("from_user_id") == from_user_id
                    and invite.get("to_email") == to_email
                    and invite.get("status") == "pending"
                ):
                    return invite

            invite_id = _new_id("invite")
            invite = {
                "id": invite_id,
                "from_user_id": from_user_id,
                "from_email": from_email,
                "to_email": to_email,
                "status": "pending",
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            data["friend_invites"][invite_id] = invite
            self._write(data)
            return invite

    def incoming_friend_invites(self, user_email: str) -> list[dict[str, Any]]:
        user_email = normalize_email(user_email)
        with self._lock:
            invites = [
                invite
                for invite in self._read()["friend_invites"].values()
                if invite.get("to_email") == user_email and invite.get("status") == "pending"
            ]
        return sorted(invites, key=lambda invite: invite["created_at"])

    def outgoing_friend_invites(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            invites = [
                invite
                for invite in self._read()["friend_invites"].values()
                if invite.get("from_user_id") == user_id and invite.get("status") == "pending"
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
            if invite.get("to_email") != user_email:
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
                        "left_at": None,
                    }
                    for participant_id in participant_ids
                },
                "created_at": now_iso,
                "archived_at": None,
            }
            data["goals"][goal_id] = goal
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

    def update_goal_progress(
        self,
        goal_id: str,
        user_id: str,
        current: int | None = None,
        target: int | None = None,
        delta: int = 0,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self.rollover_periods(now)
        with self._lock:
            data = self._read()
            goal = data["goals"].get(goal_id)
            if not goal or not _goal_active_for_user(goal, user_id):
                raise ValueError("Goal is not active for this user.")
            participant = goal["participants"][user_id]
            if target is not None:
                participant["target"] = max(1, int(target))
            if current is not None:
                participant["current"] = max(0, int(current))
            elif delta:
                participant["current"] = max(0, int(participant.get("current", 0)) + int(delta))
            self._write(data)
            return goal

    def leave_goal(self, goal_id: str, user_id: str, now: datetime | None = None) -> None:
        with self._lock:
            data = self._read()
            goal = data["goals"].get(goal_id)
            if not goal or user_id not in goal.get("participants", {}):
                raise ValueError("Goal not found.")
            goal["participants"][user_id]["left_at"] = _iso(now)
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
                        progress = max(0, int(participant.get("current", 0)))
                        target = max(1, int(participant.get("target", 1)))
                        record = _period_record(
                            goal,
                            user_id,
                            stored_start,
                            period_end,
                            progress,
                            target,
                            schedule,
                        )
                        data["period_records"][record["id"]] = record
                        participant["current"] = 0
                        participant["period_start"] = period_end.isoformat()
                        stored_start = period_end
                        changed = True
            if changed:
                self._write(data)

    def account_stats(self, user_id: str, now: datetime | None = None) -> dict[str, int | float]:
        self.rollover_periods(now)
        with self._lock:
            data = self._read()
            active_goals = sum(1 for goal in data["goals"].values() if _goal_active_for_user(goal, user_id))
            friend_count = len(
                [
                    friendship
                    for friendship in data["friendships"].values()
                    if friendship.get("active") and user_id in friendship.get("user_ids", [])
                ]
            )
            records = [
                record
                for record in data["period_records"].values()
                if record.get("user_id") == user_id
            ]
            completed_periods = sum(1 for record in records if record.get("completed"))
            aggregate = _aggregate_completion_counts(records)
            total_periods = len(records) + aggregate["total"]
            total_completed = completed_periods + aggregate["completed"]
            completion_rate = round((total_completed / total_periods) * 100, 1) if total_periods else 0.0
            return {
                "active_goals": active_goals,
                "friend_count": friend_count,
                "completed_periods": total_completed,
                "recorded_periods": total_periods,
                "completion_rate": completion_rate,
            }

    def raw_data(self) -> dict[str, Any]:
        with self._lock:
            return self._read()


def _empty_store() -> dict[str, Any]:
    return {
        "users": {},
        "friend_invites": {},
        "friendships": {},
        "goals": {},
        "period_records": {},
    }


def _normalise_store(data: dict[str, Any]) -> dict[str, Any]:
    # Old demo files had only {"users": {id: {"count": ..., "text": ...}}}; ignore
    # entries that are not Dogether profiles and initialise missing collections.
    store = _empty_store()
    users = data.get("users", {}) if isinstance(data.get("users"), dict) else {}
    store["users"] = {
        user_id: user
        for user_id, user in users.items()
        if isinstance(user, dict) and "email" in user and "user_id" in user
    }
    for key in ["friend_invites", "friendships", "goals", "period_records"]:
        value = data.get(key, {})
        store[key] = value if isinstance(value, dict) else {}
    return store


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(APP_ZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=APP_ZONE)
    return now.astimezone(APP_ZONE)


def _iso(now: datetime | None = None) -> str:
    return _now(now).astimezone(UTC).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _now(parsed)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _friendship_id(first_user_id: str, second_user_id: str) -> str:
    first, second = sorted([first_user_id, second_user_id])
    return f"friendship_{first}_{second}"


def _find_user_by_email(data: dict[str, Any], email: str) -> dict[str, Any] | None:
    for user in data["users"].values():
        if user.get("email") == normalize_email(email):
            return user
    return None


def _active_friendship(data: dict[str, Any], first_user_id: str, second_user_id: str) -> bool:
    friendship = data["friendships"].get(_friendship_id(first_user_id, second_user_id))
    return bool(friendship and friendship.get("active"))


def _goal_active_for_user(goal: dict[str, Any], user_id: str) -> bool:
    participant = goal.get("participants", {}).get(user_id)
    return bool(participant and not participant.get("left_at") and not goal.get("archived_at"))


def _schedule(schedule_class: str, required_periods: int | None = None) -> dict[str, Any]:
    if schedule_class not in SCHEDULES:
        raise ValueError("Unsupported schedule class.")
    schedule = dict(SCHEDULES[schedule_class])
    if schedule_class in {"daily_x_per_week", "weekly_x_per_month"}:
        schedule["required_periods"] = max(1, int(required_periods or schedule["required_periods"]))
    return schedule


def _period_start(now: datetime, base: str) -> datetime:
    local = _now(now)
    if base == "day":
        return local.replace(hour=0, minute=0, second=0, microsecond=0)
    if base == "week":
        start = local - timedelta(days=local.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"Unsupported period base: {base}")


def _next_period_start(period_start: datetime, base: str) -> datetime:
    if base == "day":
        return period_start + timedelta(days=1)
    if base == "week":
        return period_start + timedelta(weeks=1)
    raise ValueError(f"Unsupported period base: {base}")


def _period_record(
    goal: dict[str, Any],
    user_id: str,
    period_start: datetime,
    period_end: datetime,
    progress: int,
    target: int,
    schedule: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": f"record_{goal['id']}_{user_id}_{period_start.date().isoformat()}",
        "goal_id": goal["id"],
        "user_id": user_id,
        "schedule_class": goal.get("schedule_class", "daily"),
        "required_periods": schedule["required_periods"],
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "progress": progress,
        "target": target,
        "completed": progress >= target,
        "aggregate_key": _aggregate_key(period_start, schedule["aggregate"]),
        "created_at": _iso(),
    }


def _aggregate_key(period_start: datetime, aggregate: str) -> str:
    local = _now(period_start)
    if aggregate == "day":
        return local.date().isoformat()
    if aggregate == "week":
        week_start = _period_start(local, "week")
        return week_start.date().isoformat()
    if aggregate == "month":
        return f"{local.year:04d}-{local.month:02d}"
    raise ValueError(f"Unsupported aggregate: {aggregate}")


def _aggregate_completion_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("schedule_class") not in {"daily_x_per_week", "weekly_x_per_month"}:
            continue
        grouped[(record["goal_id"], record["schedule_class"], record["aggregate_key"])].append(record)

    total = 0
    completed = 0
    for group in grouped.values():
        total += 1
        progress = sum(max(0, int(record.get("progress", 0))) for record in group)
        target = max(1, int(group[0].get("target", 1)))
        required = max(1, int(group[0].get("required_periods", 1)))
        if progress >= target * required:
            completed += 1
    return {"total": total, "completed": completed}


def create_persistence(
    backend: str = "json",
    *,
    json_path: str = "data/users.json",
    mongodb_uri: str = "",
    mongodb_database: str = "dogether",
    mongodb_collection: str = "users",
) -> Persistence:
    backend = backend.strip().lower()
    if backend == "json":
        return JsonPersistence(json_path)
    raise ValueError("Only the json persistence backend is supported in this prototype")


def persistence_settings(secrets: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Read persistence settings from Streamlit secrets."""
    secrets = st.secrets if secrets is None else secrets
    persistence = secrets.get("persistence", {})

    return {
        "backend": str(persistence.get("backend", "json")),
        "json_path": str(persistence.get("json_path", "data/users.json")),
        "mongodb_uri": str(persistence.get("mongodb_uri", "")),
        "mongodb_database": str(persistence.get("mongodb_database", "dogether")),
        "mongodb_collection": str(persistence.get("mongodb_collection", "users")),
    }


@st.cache_resource
def get_persistence(
    backend: str,
    json_path: str,
    mongodb_uri: str,
    mongodb_database: str,
    mongodb_collection: str,
) -> Persistence:
    return create_persistence(
        backend,
        json_path=json_path,
        mongodb_uri=mongodb_uri,
        mongodb_database=mongodb_database,
        mongodb_collection=mongodb_collection,
    )


def get_configured_persistence() -> Persistence:
    return get_persistence(**persistence_settings())
