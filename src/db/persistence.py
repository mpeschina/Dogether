"""Persistence protocol and backend factory for Dogether."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Protocol

import streamlit as st

from .cached_document_persistence import DEFAULT_PERSISTENCE_CACHE_TTL_SECONDS
from .json_persistence import JsonPersistence
from .mongodb_persistence import MongoPersistence
from .mongodb_native_persistence import MongoNativePersistence
from .persistence_helpers import APP_ZONE, SCHEDULES, normalize_email


class Persistence(Protocol):
    def upsert_user(self, user_id: str, email: str, name: str, now: datetime | None = None) -> dict[str, Any]: ...

    def get_user(self, user_id: str) -> dict[str, Any] | None: ...

    def users_by_ids(self, user_ids: list[str]) -> dict[str, dict[str, Any]]: ...

    def find_user_by_email(self, email: str) -> dict[str, Any] | None: ...

    def list_users(self) -> list[dict[str, Any]]: ...

    def create_friend_invite(
        self,
        from_user_id: str,
        from_email: str,
        to_email: str,
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def incoming_friend_invites(self, user_email: str, user_id: str | None = None) -> list[dict[str, Any]]: ...

    def outgoing_friend_invites(self, user_id: str) -> list[dict[str, Any]]: ...

    def respond_friend_invite(
        self,
        invite_id: str,
        user_id: str,
        user_email: str,
        approve: bool,
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def dismissed_friend_suggestion_pairs(self, user_id: str) -> list[list[str]]: ...

    def dismiss_friend_suggestion_pair(
        self,
        user_id: str,
        first_friend_id: str,
        second_friend_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def create_friend_suggestion(
        self,
        suggested_by_user_id: str,
        suggested_user_ids: list[str],
        source_goal_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def incoming_friend_suggestions(self, user_id: str) -> list[dict[str, Any]]: ...

    def outgoing_friend_suggestions(
        self,
        user_id: str,
        include_resolved: bool = False,
    ) -> list[dict[str, Any]]: ...

    def list_friend_suggestions_for_pair(self, first_user_id: str, second_user_id: str) -> list[dict[str, Any]]: ...

    def respond_friend_suggestion(
        self,
        suggestion_id: str,
        user_id: str,
        approve: bool,
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def list_friends(self, user_id: str) -> list[dict[str, Any]]: ...

    def remove_friend(self, user_id: str, friend_id: str, now: datetime | None = None) -> None: ...

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
    ) -> dict[str, Any]: ...

    def list_goals_for_user(self, user_id: str, now: datetime | None = None) -> list[dict[str, Any]]: ...

    def add_goal_friends(
        self,
        goal_id: str,
        user_id: str,
        friend_user_ids: list[str],
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def update_goal_progress(
        self,
        goal_id: str,
        user_id: str,
        current: int | None = None,
        target: int | None = None,
        delta: int = 0,
        skipped: bool | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def set_goal_completion_notifications(
        self,
        goal_id: str,
        user_id: str,
        enabled: bool,
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def set_health_data_workflow_target(
        self,
        goal_id: str | None,
        user_id: str,
        enabled: bool,
        now: datetime | None = None,
    ) -> dict[str, Any] | None: ...

    def leave_goal(self, goal_id: str, user_id: str, now: datetime | None = None) -> None: ...

    def account_stats(self, user_id: str, now: datetime | None = None) -> dict[str, Any]: ...

    def debug_time_offset_seconds(self) -> int: ...

    def add_debug_time_offset(self, seconds: int) -> int: ...

    def reset_debug_time_offset(self) -> None: ...


def create_persistence(
    backend: str = "json",
    *,
    json_path: str = "data/users.json",
    mongodb_uri: str = "",
    mongodb_database: str = "dogether",
    mongodb_collection: str = "users",
    cache_ttl_seconds: float = DEFAULT_PERSISTENCE_CACHE_TTL_SECONDS,
) -> Persistence:
    backend = backend.strip().lower()
    if backend == "json":
        return JsonPersistence(json_path, cache_ttl_seconds=cache_ttl_seconds)
    if backend == "mongodb":
        return MongoPersistence(
            mongodb_uri,
            database=mongodb_database,
            collection=mongodb_collection,
            cache_ttl_seconds=cache_ttl_seconds,
        )
    if backend == "mongodb_native":
        return MongoNativePersistence(
            mongodb_uri,
            database=mongodb_database,
            legacy_collection=mongodb_collection,
            cache_ttl_seconds=cache_ttl_seconds,
        )
    raise ValueError("Unsupported persistence backend. Use 'json', 'mongodb', or 'mongodb_native'.")


def persistence_settings(secrets: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Read persistence settings from Streamlit secrets."""
    secrets = st.secrets if secrets is None else secrets
    persistence = secrets.get("persistence", {})

    return {
        "backend": str(persistence.get("backend", "json")),
        "json_path": str(persistence.get("json_path", "data/users.json")),
        "mongodb_uri": str(persistence.get("mongodb_uri", "")),
        "mongodb_database": str(persistence.get("mongodb_database", "dogether")),
        "mongodb_collection": str(persistence.get("mongodb_collection", "users")),
        "cache_ttl_seconds": float(
            persistence.get("cache_ttl_seconds", DEFAULT_PERSISTENCE_CACHE_TTL_SECONDS)
        ),
    }


@st.cache_resource
def get_persistence(
    backend: str,
    json_path: str,
    mongodb_uri: str,
    mongodb_database: str,
    mongodb_collection: str,
    cache_ttl_seconds: float,
) -> Persistence:
    return create_persistence(
        backend,
        json_path=json_path,
        mongodb_uri=mongodb_uri,
        mongodb_database=mongodb_database,
        mongodb_collection=mongodb_collection,
        cache_ttl_seconds=cache_ttl_seconds,
    )


def get_configured_persistence() -> Persistence:
    return get_persistence(**persistence_settings())
