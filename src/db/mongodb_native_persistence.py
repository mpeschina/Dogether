"""MongoDB persistence backend using native collections and targeted updates."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
from time import monotonic
from typing import Any, Iterable

from .persistence_helpers import (
    ACTIVITY_DAYS_REPAIR_VERSION,
    _completion_reactions,
    _correct_period_outcome,
    _days_using_app,
    _empty_store,
    _friendship_id,
    _goal_active_for_user,
    _iso,
    _new_id,
    _normalise_friend_pair,
    _normalise_goal_participants,
    _normalise_store,
    _normalise_user_profile,
    _now,
    _parse_dt,
    _period_start,
    _record_period_outcome,
    _refresh_activity_day,
    _repair_activity_days,
    _schedule,
    _validate_goal_completion_reaction,
    _next_period_start,
    normalize_email,
)

MIGRATION_ID = "native_mongo_v1"


class MongoNativePersistence:
    """MongoDB persistence that stores each domain record in its own collection."""

    def __init__(
        self,
        uri: str = "",
        database: str = "dogether",
        *,
        legacy_collection: str = "users",
        mongo_database: Any | None = None,
        cache_ttl_seconds: float = 0,
    ) -> None:
        self.uri = uri
        self.database_name = database
        self.legacy_collection = legacy_collection
        self.cache_ttl_seconds = float(cache_ttl_seconds)
        self._cache: dict[tuple[Any, ...], tuple[float, Any]] = {}
        self._client = None
        self._database = mongo_database
        if mongo_database is None and not uri:
            raise ValueError("MongoDB native persistence requires mongodb_uri.")
        self._ensure_indexes()
        self._migrate_legacy_store()

    @property
    def database(self) -> Any:
        if self._database is None:
            from pymongo import MongoClient

            self._client = MongoClient(self.uri)
            self._database = self._client[self.database_name]
        return self._database

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def _users_inventory_collection(self) -> Any:
        return self.database["users_inventory"]

    def _friend_invites_collection(self) -> Any:
        return self.database["friend_invites"]

    def _friendships_collection(self) -> Any:
        return self.database["friendships"]

    def _friend_suggestions_collection(self) -> Any:
        return self.database["friend_suggestions"]

    def _goals_collection(self) -> Any:
        return self.database["goals"]

    def _user_stats_collection(self) -> Any:
        return self.database["user_stats"]

    def _debug_collection(self) -> Any:
        return self.database["debug"]

    def _migrations_collection(self) -> Any:
        return self.database["migrations"]

    def _legacy_collection(self) -> Any:
        return self.database[self.legacy_collection]

    def _cache_enabled(self) -> bool:
        return self.cache_ttl_seconds > 0

    def _cache_get(self, key: tuple[Any, ...]) -> Any | None:
        if not self._cache_enabled():
            return None
        cached = self._cache.get(key)
        if cached is None:
            return None
        cached_at, value = cached
        if monotonic() - cached_at > self.cache_ttl_seconds:
            self._cache.pop(key, None)
            return None
        return copy.deepcopy(value)

    def _cache_set(self, key: tuple[Any, ...], value: Any) -> Any:
        if self._cache_enabled():
            self._cache[key] = (monotonic(), copy.deepcopy(value))
        return value

    def _cache_clear(self) -> None:
        self._cache.clear()

    def _read_cached(self, key: tuple[Any, ...], loader):
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        return self._cache_set(key, loader())

    def _ensure_indexes(self) -> None:
        self._users_inventory_collection().create_index("email")
        self._friend_invites_collection().create_index([("status", 1), ("to_user_id", 1)])
        self._friend_invites_collection().create_index([("status", 1), ("to_email", 1)])
        self._friend_invites_collection().create_index([("from_user_id", 1), ("status", 1)])
        self._friendships_collection().create_index([("user_ids", 1), ("active", 1)])
        self._friend_suggestions_collection().create_index("status")
        self._friend_suggestions_collection().create_index("suggested_by_user_id")
        self._friend_suggestions_collection().create_index("suggested_user_ids")
        self._goals_collection().create_index("participant_user_ids")
        self._goals_collection().create_index("created_at")
        self._goals_collection().create_index("archived_at")

    def _migrate_legacy_store(self) -> None:
        migrations = self._migrations_collection()
        if migrations.find_one({"_id": MIGRATION_ID}):
            return

        legacy = self._legacy_collection().find_one({"_id": "app_store"})
        if legacy and isinstance(legacy.get("data"), dict):
            store = _normalise_store(copy.deepcopy(legacy["data"]))
            for document_id, document in store["users"].items():
                self._users_inventory_collection().replace_one(
                    {"_id": document_id},
                    {"_id": document_id, **copy.deepcopy(document)},
                    upsert=True,
                )
            for collection, documents in [
                (self._friend_invites_collection(), store["friend_invites"]),
                (self._friend_suggestions_collection(), store["friend_suggestions"]),
                (self._friendships_collection(), store["friendships"]),
                (self._goals_collection(), store["goals"]),
                (self._user_stats_collection(), store["user_stats"]),
            ]:
                for document_id, document in documents.items():
                    collection.replace_one({"_id": document_id}, {"_id": document_id, **copy.deepcopy(document)}, upsert=True)
            self._debug_collection().replace_one(
                {"_id": "debug"},
                {"_id": "debug", **copy.deepcopy(store.get("debug", {"time_offset_seconds": 0}))},
                upsert=True,
            )

        migrations.replace_one(
            {"_id": MIGRATION_ID},
            {"_id": MIGRATION_ID, "completed_at": _iso(), "source_collection": self.legacy_collection},
            upsert=True,
        )

    def _strip_id(self, document: dict[str, Any] | None) -> dict[str, Any] | None:
        if not document:
            return None
        result = copy.deepcopy(document)
        result.pop("_id", None)
        return result

    def _strip_many(self, documents: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._strip_id(document) or {} for document in documents]

    def _user_goal_query(self, user_id: str) -> dict[str, Any]:
        return {
            "participant_user_ids": user_id,
            "archived_at": None,
            f"participants.{user_id}.left_at": None,
        }

    def _active_goals_for_user(self, user_id: str) -> list[dict[str, Any]]:
        def load_goals() -> list[dict[str, Any]]:
            goals = self._strip_many(self._goals_collection().find(self._user_goal_query(user_id)))
            _normalise_goal_participants({goal["id"]: goal for goal in goals if "id" in goal})
            return [goal for goal in goals if _goal_active_for_user(goal, user_id)]

        return self._read_cached(("active_goals_for_user", user_id), load_goals)

    def _refresh_activity_day_for_user(self, user_id: str, day: Any) -> None:
        stats = self._user_stats_for_user(user_id)
        data = {
            "users": {},
            "friend_invites": {},
            "friend_suggestions": {},
            "friendships": {},
            "goals": {goal["id"]: goal for goal in self._active_goals_for_user(user_id)},
            "user_stats": {user_id: stats},
            "debug": {"time_offset_seconds": 0},
        }
        before = copy.deepcopy(data["user_stats"][user_id])
        _refresh_activity_day(data, user_id, day)
        updated = data["user_stats"][user_id]
        if updated != before:
            self._user_stats_collection().replace_one({"_id": user_id}, {"_id": user_id, **updated}, upsert=True)
            self._cache_clear()

    def _user_stats_for_user(self, user_id: str) -> dict[str, Any]:
        def load_stats() -> dict[str, Any]:
            return self._strip_id(self._user_stats_collection().find_one({"_id": user_id})) or {"activity_days": {}}

        return self._read_cached(("user_stats", user_id), load_stats)

    def _repair_activity_days_for_user(self, user_id: str, now: datetime) -> dict[str, Any]:
        stats = self._user_stats_for_user(user_id)
        if stats.get("activity_days_repair_version") == ACTIVITY_DAYS_REPAIR_VERSION:
            return stats
        data = {
            "users": {},
            "friend_invites": {},
            "friend_suggestions": {},
            "friendships": {},
            "goals": {goal["id"]: goal for goal in self._active_goals_for_user(user_id)},
            "user_stats": {user_id: stats},
            "debug": {"time_offset_seconds": 0},
        }
        _repair_activity_days(data, user_id, now)
        updated = data["user_stats"][user_id]
        self._user_stats_collection().replace_one({"_id": user_id}, {"_id": user_id, **updated}, upsert=True)
        self._cache_clear()
        return updated

    def _rollover_goal_participant(self, goal: dict[str, Any], user_id: str, now: datetime) -> dict[str, Any]:
        if not _goal_active_for_user(goal, user_id):
            return goal
        participant = goal["participants"][user_id]
        schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
        current_start = _period_start(now, schedule["base"])
        stored_start = _parse_dt(participant.get("period_start")) or current_start
        stored_start = _period_start(stored_start, schedule["base"])
        changed = False
        affected_days = []
        while stored_start < current_start:
            period_end = _next_period_start(stored_start, schedule["base"])
            fulfilled = _record_period_outcome(goal, participant, stored_start)
            participant["completion_streak"] = (
                max(0, int(participant.get("completion_streak", 0))) + 1 if fulfilled else 0
            )
            participant["current"] = 0
            participant["skipped"] = False
            participant["period_start"] = period_end.isoformat()
            affected_days.append(stored_start.date())
            stored_start = period_end
            changed = True
        if changed:
            self._goals_collection().update_one(
                {"_id": goal["id"]},
                {"$set": {f"participants.{user_id}": participant}},
            )
            self._cache_clear()
            for affected_day in affected_days:
                self._refresh_activity_day_for_user(user_id, affected_day)
            self._refresh_activity_day_for_user(user_id, now.date())
        return goal

    def _rollover_user_goals(self, user_id: str, now: datetime | None = None) -> list[dict[str, Any]]:
        now_dt = _now(now)
        goals = self._active_goals_for_user(user_id)
        return [self._rollover_goal_participants(goal, now_dt) for goal in goals]

    def _rollover_goal_participants(self, goal: dict[str, Any], now: datetime) -> dict[str, Any]:
        for participant_id in list(goal.get("participants", {})):
            self._rollover_goal_participant(goal, participant_id, now)
        return goal

    def upsert_user(self, user_id: str, email: str, name: str, now: datetime | None = None) -> dict[str, Any]:
        now_iso = _iso(now)
        normalized_email = normalize_email(email)
        existing = self.get_user(user_id) or {}
        user = dict(existing)
        user.update(
            {
                "user_id": user_id,
                "email": normalized_email,
                "name": name.strip() or normalized_email,
                "created_at": existing.get("created_at", now_iso),
                "last_seen_at": existing.get("last_seen_at", now_iso),
            }
        )
        user.setdefault("dismissed_friend_suggestion_pairs", [])
        if user != existing:
            self._users_inventory_collection().update_one({"_id": user_id}, {"$set": user}, upsert=True)
            self._cache_clear()
        return user

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        def load_user() -> dict[str, Any] | None:
            user = self._strip_id(self._users_inventory_collection().find_one({"_id": user_id}))
            return _normalise_user_profile(user) if user else None

        return self._read_cached(("user", user_id), load_user)

    def users_by_ids(self, user_ids: list[str]) -> dict[str, dict[str, Any]]:
        unique_ids = tuple(sorted(set(user_ids)))
        if not unique_ids:
            return {}

        def load_users() -> dict[str, dict[str, Any]]:
            users = self._strip_many(self._users_inventory_collection().find({"_id": {"$in": list(unique_ids)}}))
            return {user["user_id"]: _normalise_user_profile(user) for user in users if "user_id" in user}

        return self._read_cached(("users_by_ids", unique_ids), load_users)

    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        normalized_email = normalize_email(email)

        def load_user() -> dict[str, Any] | None:
            user = self._strip_id(self._users_inventory_collection().find_one({"email": normalized_email}))
            return _normalise_user_profile(user) if user else None

        return self._read_cached(("user_by_email", normalized_email), load_user)

    def list_users(self) -> list[dict[str, Any]]:
        def load_users() -> list[dict[str, Any]]:
            users = [
                _normalise_user_profile(user)
                for user in self._strip_many(self._users_inventory_collection().find({}))
                if "user_id" in user and "email" in user
            ]
            return sorted(users, key=lambda user: (user.get("name", ""), user.get("email", "")))

        return self._read_cached(("list_users",), load_users)

    def debug_time_offset_seconds(self) -> int:
        def load_offset() -> int:
            debug = self._strip_id(self._debug_collection().find_one({"_id": "debug"})) or {}
            return int(debug.get("time_offset_seconds", 0))

        return self._read_cached(("debug_time_offset_seconds",), load_offset)

    def add_debug_time_offset(self, seconds: int) -> int:
        current = self.debug_time_offset_seconds()
        updated = max(0, current + int(seconds))
        self._debug_collection().update_one({"_id": "debug"}, {"$set": {"time_offset_seconds": updated}}, upsert=True)
        self._cache_clear()
        return updated

    def reset_debug_time_offset(self) -> None:
        self._debug_collection().update_one({"_id": "debug"}, {"$set": {"time_offset_seconds": 0}}, upsert=True)
        self._cache_clear()

    def create_friend_invite(self, from_user_id: str, from_email: str, to_email: str, now: datetime | None = None) -> dict[str, Any]:
        to_email = normalize_email(to_email)
        from_email = normalize_email(from_email)
        if not to_email or "@" not in to_email:
            raise ValueError("Enter a valid email address.")
        if to_email == from_email:
            raise ValueError("You cannot invite yourself.")
        target_user = self.find_user_by_email(to_email)
        if not target_user:
            raise ValueError("No user found with that email address.")
        if self._active_friendship(from_user_id, target_user["user_id"]):
            raise ValueError("You are already friends with that user.")
        existing = self._strip_id(
            self._friend_invites_collection().find_one(
                {"from_user_id": from_user_id, "to_email": to_email, "status": "pending"}
            )
        )
        if existing:
            if existing.get("to_user_id") != target_user["user_id"]:
                existing["to_user_id"] = target_user["user_id"]
                self._friend_invites_collection().update_one({"_id": existing["id"]}, {"$set": {"to_user_id": target_user["user_id"]}})
                self._cache_clear()
            return existing
        now_iso = _iso(now)
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
        self._friend_invites_collection().replace_one({"_id": invite_id}, {"_id": invite_id, **invite}, upsert=True)
        self._cache_clear()
        return invite

    def incoming_friend_invites(self, user_email: str, user_id: str | None = None) -> list[dict[str, Any]]:
        user_email = normalize_email(user_email)

        def load_invites() -> list[dict[str, Any]]:
            queries = [{"status": "pending", "to_email": user_email}]
            if user_id is not None:
                queries.insert(0, {"status": "pending", "to_user_id": user_id})
            invites_by_id = {}
            for query in queries:
                for invite in self._strip_many(self._friend_invites_collection().find(query)):
                    invites_by_id[invite["id"]] = invite
            return sorted(invites_by_id.values(), key=lambda invite: invite["created_at"])

        return self._read_cached(("incoming_friend_invites", user_email, user_id), load_invites)

    def outgoing_friend_invites(self, user_id: str) -> list[dict[str, Any]]:
        def load_invites() -> list[dict[str, Any]]:
            invites = self._strip_many(self._friend_invites_collection().find({"from_user_id": user_id, "status": "pending"}))
            visible = [
                invite
                for invite in invites
                if (invite.get("to_user_id") and self.get_user(invite["to_user_id"]))
                or self.find_user_by_email(invite.get("to_email", "")) is not None
            ]
            return sorted(visible, key=lambda invite: invite["created_at"])

        return self._read_cached(("outgoing_friend_invites", user_id), load_invites)

    def _active_friendship(self, first_user_id: str, second_user_id: str) -> bool:
        return bool(self._friendships_collection().find_one({"_id": _friendship_id(first_user_id, second_user_id), "active": True}))

    def respond_friend_invite(self, invite_id: str, user_id: str, user_email: str, approve: bool, now: datetime | None = None) -> dict[str, Any]:
        invite = self._strip_id(self._friend_invites_collection().find_one({"_id": invite_id}))
        if not invite or invite.get("status") != "pending":
            raise ValueError("This invite is no longer pending.")
        user_email = normalize_email(user_email)
        if invite.get("to_user_id") and invite.get("to_user_id") != user_id:
            raise ValueError("This invite is not addressed to your account.")
        if not invite.get("to_user_id") and invite.get("to_email") != user_email:
            raise ValueError("This invite is not addressed to your account.")
        now_iso = _iso(now)
        invite["status"] = "accepted" if approve else "declined"
        invite["updated_at"] = now_iso
        if approve:
            friendship_id = _friendship_id(invite["from_user_id"], user_id)
            from_user = self.get_user(invite["from_user_id"]) or {}
            to_user = self.get_user(user_id) or {}
            existing_friendship = self._strip_id(self._friendships_collection().find_one({"_id": friendship_id})) or {}
            friendship = {
                "id": friendship_id,
                "user_ids": sorted([invite["from_user_id"], user_id]),
                "emails": sorted([
                    normalize_email(from_user.get("email", invite["from_email"])),
                    normalize_email(to_user.get("email", user_email)),
                ]),
                "active": True,
                "created_at": existing_friendship.get("created_at", now_iso),
                "updated_at": now_iso,
            }
            self._friendships_collection().replace_one({"_id": friendship_id}, {"_id": friendship_id, **friendship}, upsert=True)
            self._friend_invites_collection().delete_one({"_id": invite_id})
            self._cache_clear()
        else:
            self._friend_invites_collection().update_one({"_id": invite_id}, {"$set": {"status": "declined", "updated_at": now_iso}})
            self._cache_clear()
        return invite

    def dismissed_friend_suggestion_pairs(self, user_id: str) -> list[list[str]]:
        user = self.get_user(user_id) or {}
        return [list(pair) for pair in user.get("dismissed_friend_suggestion_pairs", [])]

    def dismiss_friend_suggestion_pair(self, user_id: str, first_friend_id: str, second_friend_id: str, now: datetime | None = None) -> dict[str, Any]:
        pair = _normalise_friend_pair([first_friend_id, second_friend_id])
        if pair is None:
            raise ValueError("Select two different friends to dismiss.")
        user = self.get_user(user_id)
        if not user:
            raise ValueError("User was not found.")
        dismissed_pairs = user.setdefault("dismissed_friend_suggestion_pairs", [])
        if tuple(pair) not in {tuple(existing_pair) for existing_pair in dismissed_pairs}:
            dismissed_pairs.append(pair)
        user["updated_at"] = _iso(now)
        self._users_inventory_collection().update_one(
            {"_id": user_id},
            {"$set": {"dismissed_friend_suggestion_pairs": dismissed_pairs, "updated_at": user["updated_at"]}},
        )
        self._cache_clear()
        return user

    def create_friend_suggestion(self, suggested_by_user_id: str, suggested_user_ids: list[str], source_goal_id: str | None = None, now: datetime | None = None) -> dict[str, Any]:
        suggested_user_ids = sorted(set(suggested_user_ids))
        if len(suggested_user_ids) != 2:
            raise ValueError("Select exactly two users to suggest.")
        if suggested_by_user_id in suggested_user_ids:
            raise ValueError("You cannot suggest yourself.")
        if not self.get_user(suggested_by_user_id):
            raise ValueError("Suggestion creator was not found.")
        missing_user_ids = [uid for uid in suggested_user_ids if not self.get_user(uid)]
        if missing_user_ids:
            raise ValueError("Suggested users must exist.")
        if self._active_friendship(suggested_user_ids[0], suggested_user_ids[1]):
            raise ValueError("Those users are already friends.")
        existing_suggestions = self._strip_many(self._friend_suggestions_collection().find({"suggested_user_ids": suggested_user_ids}))
        for suggestion in existing_suggestions:
            if suggestion.get("status") == "pending":
                return suggestion
            if suggestion.get("status") == "declined" and suggestion.get("suggested_by_user_id") == suggested_by_user_id and suggestion.get("source_goal_id") == source_goal_id:
                raise ValueError("This suggestion was already declined.")
        now_iso = _iso(now)
        suggestion_id = _new_id("suggestion")
        suggestion = {
            "id": suggestion_id,
            "suggested_by_user_id": suggested_by_user_id,
            "suggested_user_ids": suggested_user_ids,
            "source_goal_id": source_goal_id,
            "responses": {uid: "pending" for uid in suggested_user_ids},
            "status": "pending",
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        self._friend_suggestions_collection().replace_one({"_id": suggestion_id}, {"_id": suggestion_id, **suggestion}, upsert=True)
        self._cache_clear()
        return suggestion

    def incoming_friend_suggestions(self, user_id: str) -> list[dict[str, Any]]:
        def load_suggestions() -> list[dict[str, Any]]:
            suggestions = [
                suggestion
                for suggestion in self._strip_many(self._friend_suggestions_collection().find({"status": "pending", "suggested_user_ids": user_id}))
                if suggestion.get("responses", {}).get(user_id) == "pending"
            ]
            return sorted(suggestions, key=lambda suggestion: suggestion["created_at"])

        return self._read_cached(("incoming_friend_suggestions", user_id), load_suggestions)

    def accepted_pending_friend_suggestions(self, user_id: str) -> list[dict[str, Any]]:
        def load_suggestions() -> list[dict[str, Any]]:
            suggestions = [
                suggestion
                for suggestion in self._strip_many(self._friend_suggestions_collection().find({"status": "pending", "suggested_user_ids": user_id}))
                if suggestion.get("responses", {}).get(user_id) == "accepted"
            ]
            return sorted(suggestions, key=lambda suggestion: suggestion["created_at"])

        return self._read_cached(("accepted_pending_friend_suggestions", user_id), load_suggestions)

    def outgoing_friend_suggestions(self, user_id: str, include_resolved: bool = False) -> list[dict[str, Any]]:
        def load_suggestions() -> list[dict[str, Any]]:
            suggestions = self._strip_many(self._friend_suggestions_collection().find({"suggested_by_user_id": user_id}))
            if not include_resolved:
                suggestions = [suggestion for suggestion in suggestions if suggestion.get("status") == "pending"]
            return sorted(suggestions, key=lambda suggestion: suggestion["created_at"])

        return self._read_cached(("outgoing_friend_suggestions", user_id, include_resolved), load_suggestions)

    def list_friend_suggestions_for_pair(self, first_user_id: str, second_user_id: str) -> list[dict[str, Any]]:
        suggested_user_ids = tuple(sorted([first_user_id, second_user_id]))

        def load_suggestions() -> list[dict[str, Any]]:
            suggestions = self._strip_many(self._friend_suggestions_collection().find({"suggested_user_ids": list(suggested_user_ids)}))
            return sorted(suggestions, key=lambda suggestion: suggestion["created_at"])

        return self._read_cached(("friend_suggestions_for_pair", suggested_user_ids), load_suggestions)

    def respond_friend_suggestion(self, suggestion_id: str, user_id: str, approve: bool, now: datetime | None = None) -> dict[str, Any]:
        suggestion = self._strip_id(self._friend_suggestions_collection().find_one({"_id": suggestion_id}))
        if not suggestion or suggestion.get("status") != "pending":
            raise ValueError("This suggestion is no longer pending.")
        if user_id not in suggestion.get("suggested_user_ids", []):
            raise ValueError("This suggestion is not addressed to your account.")
        if suggestion.get("responses", {}).get(user_id) != "pending":
            raise ValueError("You have already responded to this suggestion.")
        now_iso = _iso(now)
        suggestion["responses"][user_id] = "accepted" if approve else "declined"
        suggestion["updated_at"] = now_iso
        if not approve:
            suggestion["status"] = "declined"
        elif all(response == "accepted" for response in suggestion["responses"].values()):
            first_user_id, second_user_id = suggestion["suggested_user_ids"]
            friendship_id = _friendship_id(first_user_id, second_user_id)
            first_user = self.get_user(first_user_id) or {}
            second_user = self.get_user(second_user_id) or {}
            existing_friendship = self._strip_id(self._friendships_collection().find_one({"_id": friendship_id})) or {}
            friendship = {
                "id": friendship_id,
                "user_ids": sorted([first_user_id, second_user_id]),
                "emails": sorted([normalize_email(first_user.get("email", "")), normalize_email(second_user.get("email", ""))]),
                "active": True,
                "created_at": existing_friendship.get("created_at", now_iso),
                "updated_at": now_iso,
            }
            self._friendships_collection().replace_one({"_id": friendship_id}, {"_id": friendship_id, **friendship}, upsert=True)
            suggestion["status"] = "accepted"
        self._friend_suggestions_collection().update_one(
            {"_id": suggestion_id},
            {"$set": {"responses": suggestion["responses"], "status": suggestion["status"], "updated_at": now_iso}},
        )
        self._cache_clear()
        return suggestion

    def list_friends(self, user_id: str) -> list[dict[str, Any]]:
        def load_friends() -> list[dict[str, Any]]:
            friendships = self._strip_many(self._friendships_collection().find({"user_ids": user_id, "active": True}))
            friend_ids = [next(uid for uid in friendship["user_ids"] if uid != user_id) for friendship in friendships]
            friends = list(self.users_by_ids(friend_ids).values())
            return sorted(friends, key=lambda user: (user.get("name", ""), user.get("email", "")))

        return self._read_cached(("friends", user_id), load_friends)

    def remove_friend(self, user_id: str, friend_id: str, now: datetime | None = None) -> None:
        friendship_id = _friendship_id(user_id, friend_id)
        friendship = self._strip_id(self._friendships_collection().find_one({"_id": friendship_id, "active": True}))
        if not friendship:
            raise ValueError("That friendship is not active.")
        self._friendships_collection().update_one({"_id": friendship_id}, {"$set": {"active": False, "updated_at": _iso(now)}})
        self._cache_clear()

    def create_goal(self, created_by: str, description: str, schedule_class: str, required_periods: int, friend_user_ids: list[str], target: int, current: int = 0, now: datetime | None = None) -> dict[str, Any]:
        description = description.strip()
        if not description:
            raise ValueError("Goal description is required.")
        schedule = _schedule(schedule_class, required_periods)
        target = max(1, int(target))
        current = max(0, int(current))
        now_dt = _now(now)
        now_iso = _iso(now_dt)
        active_friend_ids = {friend["user_id"] for friend in self.list_friends(created_by)}
        invalid = sorted(set(friend_user_ids) - active_friend_ids)
        if invalid:
            raise ValueError("Goals can only be shared with accepted friends.")
        participant_ids = [created_by, *sorted(set(friend_user_ids))]
        period_start = _period_start(now_dt, schedule["base"]).isoformat()
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
                    "completion_notifications_max_per_day": 3,
                    "completion_notification_counts": {},
                    "skipped": False,
                    "period_outcomes": {},
                    "left_at": None,
                }
                for participant_id in participant_ids
            },
            "created_at": now_iso,
            "archived_at": None,
        }
        self._goals_collection().replace_one({"_id": goal_id}, {"_id": goal_id, **goal}, upsert=True)
        self._cache_clear()
        for participant_id in participant_ids:
            self._refresh_activity_day_for_user(participant_id, now_dt.date())
        return goal

    def list_goals_for_user(self, user_id: str, now: datetime | None = None) -> list[dict[str, Any]]:
        goals = self._rollover_user_goals(user_id, now)
        return sorted(goals, key=lambda goal: goal["created_at"])

    def add_goal_friends(self, goal_id: str, user_id: str, friend_user_ids: list[str], now: datetime | None = None) -> dict[str, Any]:
        now_dt = _now(now)
        goal = self._strip_id(self._goals_collection().find_one({"_id": goal_id}))
        if not goal or not _goal_active_for_user(goal, user_id):
            raise ValueError("Goal is not active for this user.")
        self._rollover_goal_participants(goal, now_dt)
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
        set_fields = {}
        for participant_id in new_participant_ids:
            participant = {
                "target": target,
                "current": 0,
                "period_start": period_start,
                "completion_streak": 0,
                "completion_notifications_enabled": True,
                "completion_notifications_max_per_day": 3,
                "completion_notification_counts": {},
                "skipped": False,
                "period_outcomes": {},
                "left_at": None,
            }
            goal["participants"][participant_id] = participant
            set_fields[f"participants.{participant_id}"] = participant
        goal["participant_user_ids"] = [
            *goal.get("participant_user_ids", []),
            *[participant_id for participant_id in new_participant_ids if participant_id not in goal.get("participant_user_ids", [])],
        ]
        set_fields["participant_user_ids"] = goal["participant_user_ids"]
        self._goals_collection().update_one({"_id": goal_id}, {"$set": set_fields})
        self._cache_clear()
        for participant_id in new_participant_ids:
            self._refresh_activity_day_for_user(participant_id, now_dt.date())
        return goal

    def update_goal_progress(self, goal_id: str, user_id: str, current: int | None = None, target: int | None = None, delta: int = 0, skipped: bool | None = None, now: datetime | None = None) -> dict[str, Any]:
        now_dt = _now(now)
        today_key = now_dt.date().isoformat()
        goal = self._strip_id(self._goals_collection().find_one({"_id": goal_id}))
        if not goal or not _goal_active_for_user(goal, user_id):
            raise ValueError("Goal is not active for this user.")
        self._rollover_goal_participants(goal, now_dt)
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
        if is_complete and not was_complete and participant.get("last_completion_notification_day") != today_key:
            participant["last_completion_notification_day"] = today_key
            notification_event = {"type": "goal_completed", "goal_id": goal_id, "completed_by_user_id": user_id, "day": today_key}
        self._goals_collection().update_one({"_id": goal_id}, {"$set": {f"participants.{user_id}": participant}})
        self._users_inventory_collection().update_one({"_id": user_id}, {"$set": {"last_seen_at": _iso(now)}})
        self._cache_clear()
        self._refresh_activity_day_for_user(user_id, now_dt.date())
        result = copy.deepcopy(goal)
        if notification_event:
            result["_notification_event"] = notification_event
        return result

    def correct_goal_period_progress(
        self,
        goal_id: str,
        user_id: str,
        period_start: datetime,
        current: int,
        target: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_dt = _now(now)
        corrected_dt = _now(period_start)
        goal = self._strip_id(self._goals_collection().find_one({"_id": goal_id}))
        if not goal or not _goal_active_for_user(goal, user_id):
            raise ValueError("Goal is not active for this user.")
        self._rollover_goal_participants(goal, now_dt)

        schedule = _schedule(goal.get("schedule_class", "daily"), goal.get("required_periods"))
        corrected_start = _period_start(corrected_dt, schedule["base"])
        current_start = _period_start(now_dt, schedule["base"])
        if corrected_start >= current_start:
            raise ValueError("Only older goal periods can be corrected.")

        retained_periods = 0
        cursor = corrected_start
        while cursor < current_start:
            retained_periods += 1
            cursor = _next_period_start(cursor, schedule["base"])
        if retained_periods > 370:
            raise ValueError("That goal period is no longer retained.")

        participant = goal["participants"][user_id]
        affected_days = _correct_period_outcome(
            goal,
            participant,
            corrected_start,
            current=current,
            target=target,
        )
        self._goals_collection().update_one({"_id": goal_id}, {"$set": {f"participants.{user_id}": participant}})
        self._users_inventory_collection().update_one({"_id": user_id}, {"$set": {"last_seen_at": _iso(now)}})
        self._cache_clear()
        for affected_day in affected_days:
            self._refresh_activity_day_for_user(user_id, affected_day)
        return copy.deepcopy(goal)

    def set_goal_completion_notifications(self, goal_id: str, user_id: str, enabled: bool, now: datetime | None = None) -> dict[str, Any]:
        goal = self._strip_id(self._goals_collection().find_one({"_id": goal_id}))
        if not goal or not _goal_active_for_user(goal, user_id):
            raise ValueError("Goal is not active for this user.")
        goal["participants"][user_id]["completion_notifications_enabled"] = bool(enabled)
        self._goals_collection().update_one(
            {"_id": goal_id},
            {"$set": {f"participants.{user_id}.completion_notifications_enabled": bool(enabled)}},
        )
        self._cache_clear()
        return goal

    def set_goal_completion_notification_limit(self, goal_id: str, user_id: str, max_per_day: int, now: datetime | None = None) -> dict[str, Any]:
        goal = self._strip_id(self._goals_collection().find_one({"_id": goal_id}))
        if not goal or not _goal_active_for_user(goal, user_id):
            raise ValueError("Goal is not active for this user.")
        limit = max(1, int(max_per_day))
        goal["participants"][user_id]["completion_notifications_max_per_day"] = limit
        self._goals_collection().update_one(
            {"_id": goal_id},
            {"$set": {f"participants.{user_id}.completion_notifications_max_per_day": limit}},
        )
        self._cache_clear()
        return goal

    def claim_goal_completion_notification(self, goal_id: str, user_id: str, day: str, now: datetime | None = None) -> bool:
        goal = self._strip_id(self._goals_collection().find_one({"_id": goal_id}))
        if not goal or not _goal_active_for_user(goal, user_id):
            return False
        participant = goal["participants"][user_id]
        if not participant.get("completion_notifications_enabled", True):
            return False
        max_per_day = max(1, int(participant.get("completion_notifications_max_per_day", 3) or 3))
        counts = participant.setdefault("completion_notification_counts", {})
        current_count = max(0, int(counts.get(day, 0) or 0))
        if current_count >= max_per_day:
            return False
        counts[day] = current_count + 1
        for count_day in sorted(counts)[:-370]:
            del counts[count_day]
        self._goals_collection().update_one(
            {"_id": goal_id},
            {"$set": {f"participants.{user_id}.completion_notification_counts": counts}},
        )
        self._cache_clear()
        return True

    def set_goal_completion_reaction(
        self,
        goal_id: str,
        completed_user_id: str,
        reacting_user_id: str,
        emote: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_iso = _iso(now)
        now_dt = _now(now)
        goal = self._strip_id(self._goals_collection().find_one({"_id": goal_id}))
        if not goal:
            raise ValueError("Goal is not active for this user.")
        self._rollover_goal_participants(goal, now_dt)
        participant, period_key = _validate_goal_completion_reaction(
            goal,
            completed_user_id,
            reacting_user_id,
            emote,
            now_dt,
        )
        reactions = _completion_reactions(participant)
        period_reactions = reactions.setdefault(period_key, {})
        if not isinstance(period_reactions, dict):
            period_reactions = {}
            reactions[period_key] = period_reactions
        if not str(emote).strip():
            period_reactions.pop(reacting_user_id, None)
            if not period_reactions:
                reactions.pop(period_key, None)
        else:
            period_reactions[reacting_user_id] = {"emote": emote, "reacted_at": now_iso}
        for reaction_period_key in sorted(reactions)[:-370]:
            del reactions[reaction_period_key]
        self._goals_collection().update_one(
            {"_id": goal_id},
            {"$set": {f"participants.{completed_user_id}.completion_reactions": reactions}},
        )
        self._cache_clear()
        return copy.deepcopy(goal)

    def claim_goal_reaction_notification(
        self,
        goal_id: str,
        user_id: str,
        reacting_user_id: str,
        now: datetime | None = None,
    ) -> bool:
        now_dt = _now(now)
        goal = self._strip_id(self._goals_collection().find_one({"_id": goal_id}))
        user = self._strip_id(self._users_inventory_collection().find_one({"_id": user_id}))
        if not goal or not user or not _goal_active_for_user(goal, user_id):
            return False
        timestamps = user.get("reaction_notification_timestamps")
        timestamps = timestamps if isinstance(timestamps, dict) else {}
        last_sent_at = _parse_dt(timestamps.get(reacting_user_id))
        if last_sent_at is not None and now_dt - last_sent_at < timedelta(hours=2):
            return False
        sent_at = _iso(now_dt)
        timestamps[reacting_user_id] = sent_at
        self._users_inventory_collection().update_one(
            {"_id": user_id},
            {"$set": {"reaction_notification_timestamps": timestamps}},
        )
        self._cache_clear()
        return True

    def set_health_data_workflow_target(self, goal_id: str | None, user_id: str, enabled: bool, now: datetime | None = None) -> dict[str, Any] | None:
        now_iso = _iso(now)
        selected_goal = None
        if enabled:
            if not goal_id:
                raise ValueError("Choose a goal for Apple Health import.")
            selected_goal = self._strip_id(self._goals_collection().find_one({"_id": goal_id}))
            if not selected_goal or not _goal_active_for_user(selected_goal, user_id):
                raise ValueError("Goal is not active for this user.")
        for goal in self._active_goals_for_user(user_id):
            workflow = goal.get("participants", {}).get(user_id, {}).get("health_data_workflow")
            if isinstance(workflow, dict) and workflow.get("enabled"):
                self._goals_collection().update_one(
                    {"_id": goal["id"]},
                    {"$set": {f"participants.{user_id}.health_data_workflow.enabled": False, f"participants.{user_id}.health_data_workflow.disabled_at": now_iso}},
                )
                self._cache_clear()
        if enabled and selected_goal is not None:
            workflow = {"enabled": True, "provider": "apple_health_steps", "configured_at": now_iso}
            selected_goal["participants"][user_id]["health_data_workflow"] = workflow
            self._goals_collection().update_one({"_id": selected_goal["id"]}, {"$set": {f"participants.{user_id}.health_data_workflow": workflow}})
            self._cache_clear()
        return copy.deepcopy(selected_goal) if selected_goal is not None else None

    def leave_goal(self, goal_id: str, user_id: str, now: datetime | None = None) -> None:
        now_dt = _now(now)
        goal = self._strip_id(self._goals_collection().find_one({"_id": goal_id}))
        if not goal or user_id not in goal.get("participants", {}):
            raise ValueError("Goal not found.")
        del goal["participants"][user_id]
        goal["participant_user_ids"] = [participant_id for participant_id in goal.get("participant_user_ids", []) if participant_id != user_id]
        if not goal["participants"]:
            self._goals_collection().delete_one({"_id": goal_id})
            self._cache_clear()
        else:
            self._goals_collection().update_one(
                {"_id": goal_id},
                {"$set": {"participants": goal["participants"], "participant_user_ids": goal["participant_user_ids"]}},
            )
            self._cache_clear()
        self._refresh_activity_day_for_user(user_id, now_dt.date())

    def account_stats(self, user_id: str, now: datetime | None = None) -> dict[str, Any]:
        now_dt = _now(now)
        self._rollover_user_goals(user_id, now_dt)
        stats = self._repair_activity_days_for_user(user_id, now_dt)
        before = copy.deepcopy(stats)
        self._refresh_activity_day_for_user(user_id, now_dt.date())
        stats = self._user_stats_for_user(user_id) or before
        active_goals = self._goals_collection().count_documents(self._user_goal_query(user_id))
        friend_count = self._friendships_collection().count_documents({"user_ids": user_id, "active": True})
        user = self.get_user(user_id) or {}
        month_prefix = f"{now_dt.year:04d}-{now_dt.month:02d}-"
        month_days = [day for date_key, day in stats.get("activity_days", {}).items() if date_key.startswith(month_prefix)]
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
        store = _empty_store()
        store["users"] = {
            document.get("user_id", document.get("_id")): self._strip_id(document)
            for document in self._users_inventory_collection().find({})
        }
        store["friend_invites"] = {
            document.get("id", document.get("_id")): self._strip_id(document)
            for document in self._friend_invites_collection().find({})
        }
        store["friend_suggestions"] = {
            document.get("id", document.get("_id")): self._strip_id(document)
            for document in self._friend_suggestions_collection().find({})
        }
        store["friendships"] = {
            document.get("id", document.get("_id")): self._strip_id(document)
            for document in self._friendships_collection().find({})
        }
        store["goals"] = {
            document.get("id", document.get("_id")): self._strip_id(document)
            for document in self._goals_collection().find({})
        }
        store["user_stats"] = {
            document.get("id", document.get("_id")): self._strip_id(document)
            for document in self._user_stats_collection().find({})
        }
        debug = self._strip_id(self._debug_collection().find_one({"_id": "debug"}))
        if debug:
            store["debug"] = debug
        return _normalise_store(store)
