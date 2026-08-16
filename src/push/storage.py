"""Separate storage for Web Push subscriptions."""
from __future__ import annotations

import copy
import threading
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Any, Mapping, Protocol

import streamlit as st

from src.db.cached_document_persistence import DEFAULT_PERSISTENCE_CACHE_TTL_SECONDS
from src.db.persistence_helpers import _iso, normalize_email


class PushStorage(Protocol):
    def save_subscription(
        self,
        user_id: str,
        user_email: str,
        subscription: dict[str, Any],
        user_agent: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]: ...

    def delete_subscription(self, endpoint: str) -> None: ...

    def delete_subscriptions_for_user(self, user_id: str) -> None: ...

    def subscriptions_for_user(self, user_id: str) -> list[dict[str, Any]]: ...


def _validate_subscription(subscription: dict[str, Any]) -> str:
    endpoint = subscription.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError("Invalid subscription: missing endpoint.")
    keys = subscription.get("keys")
    if not isinstance(keys, dict) or not keys.get("p256dh") or not keys.get("auth"):
        raise ValueError("Invalid subscription: missing keys.")
    return endpoint


def _subscription_record(
    *,
    endpoint: str,
    user_id: str,
    user_email: str,
    subscription: dict[str, Any],
    user_agent: str | None,
    created_at: str,
    updated_at: str,
) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "user_id": user_id,
        "user_email": normalize_email(user_email),
        "subscription": copy.deepcopy(subscription),
        "user_agent": user_agent or "",
        "created_at": created_at,
        "updated_at": updated_at,
    }


class JsonPushStorage:
    """JSON-file backed push-subscription table for local deployments."""

    def __init__(self, path: str | Path = "data/push_subscriptions.json") -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        with self.path.open(encoding="utf-8") as file:
            loaded = json.load(file)
        if not isinstance(loaded, dict):
            return {}
        return {key: value for key, value in loaded.items() if isinstance(value, dict)}

    def _write(self, data: dict[str, dict[str, Any]]) -> None:
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

    def save_subscription(
        self,
        user_id: str,
        user_email: str,
        subscription: dict[str, Any],
        user_agent: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        endpoint = _validate_subscription(subscription)
        with self._lock:
            data = self._read()
            now_iso = _iso(now)
            existing = data.get(endpoint, {})
            record = _subscription_record(
                endpoint=endpoint,
                user_id=user_id,
                user_email=user_email,
                subscription=subscription,
                user_agent=user_agent,
                created_at=str(existing.get("created_at") or now_iso),
                updated_at=now_iso,
            )
            data[endpoint] = record
            self._write(data)
            return record

    def delete_subscription(self, endpoint: str) -> None:
        with self._lock:
            data = self._read()
            if endpoint in data:
                del data[endpoint]
                self._write(data)

    def delete_subscriptions_for_user(self, user_id: str) -> None:
        for record in self.subscriptions_for_user(user_id):
            self.delete_subscription(record["endpoint"])

    def subscriptions_for_user(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                copy.deepcopy(record)
                for record in self._read().values()
                if record.get("user_id") == user_id and isinstance(record.get("subscription"), dict)
            ]


class MongoPushStorage:
    """MongoDB collection backed push-subscription table."""

    def __init__(
        self,
        uri: str = "",
        database: str = "dogether",
        collection: str = "push_subscriptions",
        *,
        mongo_collection: Any | None = None,
        cache_ttl_seconds: float = DEFAULT_PERSISTENCE_CACHE_TTL_SECONDS,
    ) -> None:
        self.uri = uri
        self.database = database
        self.collection_name = collection
        self._client = None
        self._collection = mongo_collection
        self.cache_ttl_seconds = float(cache_ttl_seconds)
        self._cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
        self._cache_lock = threading.RLock()
        self._cache_revision = 0
        if mongo_collection is None and not uri:
            raise ValueError("MongoDB push storage requires mongodb_uri.")

    @property
    def collection(self) -> Any:
        if self._collection is None:
            from pymongo import MongoClient

            self._client = MongoClient(self.uri)
            self._collection = self._client[self.database][self.collection_name]
        return self._collection

    def save_subscription(
        self,
        user_id: str,
        user_email: str,
        subscription: dict[str, Any],
        user_agent: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        endpoint = _validate_subscription(subscription)
        now_iso = _iso(now)
        existing = self.collection.find_one({"_id": endpoint}) or {}
        record = _subscription_record(
            endpoint=endpoint,
            user_id=user_id,
            user_email=user_email,
            subscription=subscription,
            user_agent=user_agent,
            created_at=str(existing.get("created_at") or now_iso),
            updated_at=now_iso,
        )
        self.collection.replace_one({"_id": endpoint}, {"_id": endpoint, **record}, upsert=True)
        self._cache_clear()
        return record

    def delete_subscription(self, endpoint: str) -> None:
        self.collection.delete_one({"_id": endpoint})
        self._cache_clear()

    def delete_subscriptions_for_user(self, user_id: str) -> None:
        for record in self.subscriptions_for_user(user_id):
            self.delete_subscription(record["endpoint"])

    def subscriptions_for_user(self, user_id: str) -> list[dict[str, Any]]:
        cache_key = ("subscriptions_for_user", user_id)

        def load_records() -> list[dict[str, Any]]:
            records = []
            for document in self.collection.find({"user_id": user_id}):
                record = dict(document)
                record.pop("_id", None)
                if isinstance(record.get("subscription"), dict):
                    records.append(record)
            return records

        return self._read_cached(cache_key, load_records)

    def _cache_get(self, key: tuple[str, str]) -> list[dict[str, Any]] | None:
        if self.cache_ttl_seconds <= 0:
            return None
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is None:
                return None
            cached_at, value = cached
            if monotonic() - cached_at > self.cache_ttl_seconds:
                self._cache.pop(key, None)
                return None
            return copy.deepcopy(value)

    def _read_cached(self, key: tuple[str, str], loader) -> list[dict[str, Any]]:
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        with self._cache_lock:
            revision = self._cache_revision
        value = loader()
        if self.cache_ttl_seconds > 0:
            with self._cache_lock:
                if revision == self._cache_revision:
                    self._cache[key] = (monotonic(), copy.deepcopy(value))
        return value

    def _cache_clear(self) -> None:
        with self._cache_lock:
            self._cache_revision += 1
            self._cache.clear()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()


def create_push_storage(
    backend: str = "json",
    *,
    json_path: str = "data/push_subscriptions.json",
    mongodb_uri: str = "",
    mongodb_database: str = "dogether",
    mongodb_collection: str = "push_subscriptions",
    cache_ttl_seconds: float = DEFAULT_PERSISTENCE_CACHE_TTL_SECONDS,
) -> PushStorage:
    backend = backend.strip().lower()
    if backend == "json":
        return JsonPushStorage(json_path)
    if backend == "mongodb":
        return MongoPushStorage(
            mongodb_uri,
            database=mongodb_database,
            collection=mongodb_collection,
            cache_ttl_seconds=cache_ttl_seconds,
        )
    raise ValueError("Unsupported push storage backend. Use 'json' or 'mongodb'.")


def push_storage_settings(secrets: Mapping[str, Any] | None = None) -> dict[str, Any]:
    secrets = st.secrets if secrets is None else secrets
    persistence = secrets.get("persistence", {})
    push = secrets.get("push", {})
    persistence_backend = str(persistence.get("backend", "json"))
    default_backend = "mongodb" if persistence_backend.strip().lower() == "mongodb_native" else persistence_backend

    return {
        "backend": str(push.get("backend", default_backend)),
        "json_path": str(push.get("json_path", "data/push_subscriptions.json")),
        "mongodb_uri": str(push.get("mongodb_uri", persistence.get("mongodb_uri", ""))),
        "mongodb_database": str(push.get("mongodb_database", persistence.get("mongodb_database", "dogether"))),
        "mongodb_collection": str(push.get("mongodb_collection", "push_subscriptions")),
        "cache_ttl_seconds": float(
            push.get("cache_ttl_seconds", persistence.get("cache_ttl_seconds", DEFAULT_PERSISTENCE_CACHE_TTL_SECONDS))
        ),
    }


@st.cache_resource
def get_push_storage(
    backend: str,
    json_path: str,
    mongodb_uri: str,
    mongodb_database: str,
    mongodb_collection: str,
    cache_ttl_seconds: float,
) -> PushStorage:
    return create_push_storage(
        backend,
        json_path=json_path,
        mongodb_uri=mongodb_uri,
        mongodb_database=mongodb_database,
        mongodb_collection=mongodb_collection,
        cache_ttl_seconds=cache_ttl_seconds,
    )
