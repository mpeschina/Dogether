"""Persistence backends for per-user application state."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping, Protocol

import streamlit as st


class Persistence(Protocol):
    def get_user(self, user_id: str) -> dict[str, Any]: ...

    def save_user(self, user_id: str, state: dict[str, Any]) -> None: ...


def _normalise_state(state: dict[str, Any] | None) -> dict[str, Any]:
    state = state or {}
    return {
        "count": max(0, int(state.get("count", 0))),
        "text": str(state.get("text", "")),
    }


class JsonPersistence:
    """JSON persistence for local development."""

    _lock = threading.RLock()

    def __init__(self, path: str | Path = "data/users.json") -> None:
        self.path = Path(path)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"users": {}}

        with self.path.open(encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict) or not isinstance(data.get("users"), dict):
            raise ValueError(f"Invalid persistence file format: {self.path}")

        return data

    def get_user(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            return _normalise_state(self._read()["users"].get(user_id))

    def save_user(self, user_id: str, state: dict[str, Any]) -> None:
        with self._lock:
            data = self._read()
            data["users"][user_id] = _normalise_state(state)
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


class MongoPersistence:
    """MongoDB persistence suitable for Atlas."""

    def __init__(
        self,
        uri: str,
        database: str = "dogether",
        collection: str = "users",
    ) -> None:
        if not uri:
            raise ValueError("A MongoDB URI is required for the mongodb backend")

        from pymongo import MongoClient

        self.client = MongoClient(uri)
        self.collection = self.client[database][collection]

    def get_user(self, user_id: str) -> dict[str, Any]:
        return _normalise_state(self.collection.find_one({"_id": user_id}))

    def save_user(self, user_id: str, state: dict[str, Any]) -> None:
        self.collection.update_one(
            {"_id": user_id},
            {"$set": _normalise_state(state)},
            upsert=True,
        )


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
    if backend == "mongodb":
        return MongoPersistence(mongodb_uri, mongodb_database, mongodb_collection)
    raise ValueError(f"Unsupported persistence backend: {backend}")


def persistence_settings(
    secrets: Mapping[str, Any] | None = None,
) -> dict[str, str]:
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
