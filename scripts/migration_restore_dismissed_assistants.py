#!/usr/bin/env python3
"""Restore Assistant access for accounts blocked by the retired global dismissal.

Run from the repository root. The script previews changes by default; pass
``--apply`` to write them to MongoDB.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from pymongo import MongoClient


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.assistant.state import AssistantState  # noqa: E402
from src.assistant.stories.tutorial import READY_NODE, STANDARD_STORY_ID  # noqa: E402


def load_mongodb_settings(secrets_path: Path) -> tuple[str, str]:
    try:
        with secrets_path.open("rb") as secrets_file:
            secrets = tomllib.load(secrets_file)
    except FileNotFoundError as exc:
        raise ValueError(f"Streamlit secrets file not found: {secrets_path}") from exc
    persistence = secrets.get("persistence")
    if not isinstance(persistence, Mapping) or persistence.get("backend") != "mongodb_native":
        raise ValueError("[persistence] backend must be set to 'mongodb_native' in Streamlit secrets.")
    uri = persistence.get("mongodb_uri")
    database = persistence.get("mongodb_database", "dogether")
    if not isinstance(uri, str) or not uri.strip():
        raise ValueError("[persistence] mongodb_uri must be configured in Streamlit secrets.")
    if not isinstance(database, str) or not database.strip():
        raise ValueError("[persistence] mongodb_database must be a non-empty string.")
    return uri, database


def repaired_assistant_state(value: Any) -> dict[str, Any] | None:
    """Return the normalized replacement for a globally dismissed Assistant state."""
    if not isinstance(value, Mapping) or value.get("status") != "dismissed":
        return None
    state = AssistantState.from_value(value)
    return replace(
        state,
        story=STANDARD_STORY_ID,
        scene=READY_NODE,
        status="completed",
    ).to_dict()


def planned_repairs(users: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return repaired Assistant states keyed by user id for raw Mongo user records."""
    repairs: dict[str, dict[str, Any]] = {}
    for user in users:
        user_id = user.get("_id")
        repaired = repaired_assistant_state(user.get("assistant_state"))
        if isinstance(user_id, str) and user_id and repaired is not None:
            repairs[user_id] = repaired
    return repairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Restore Assistant access for globally dismissed MongoDB accounts."
    )
    parser.add_argument("--apply", action="store_true", help="Write the planned repairs to MongoDB.")
    parser.add_argument(
        "--secrets-path",
        type=Path,
        default=REPOSITORY_ROOT / ".streamlit" / "secrets.toml",
        help="Path to Streamlit secrets TOML (default: %(default)s).",
    )
    args = parser.parse_args(argv)
    try:
        uri, database_name = load_mongodb_settings(args.secrets_path)
    except ValueError as exc:
        parser.error(str(exc))

    client = MongoClient(uri)
    try:
        users = list(
            client[database_name]["users_inventory"].find(
                {"assistant_state.status": "dismissed"},
                {"_id": 1, "assistant_state": 1},
            )
        )
        repairs = planned_repairs(users)
        print(f"Scanned {len(users)} globally dismissed Assistant accounts.")
        print(f"Planned repairs for {len(repairs)} accounts.")
        if not args.apply:
            print("Dry run: no changes written. Re-run with --apply to persist these repairs.")
            return 0

        for user_id, assistant_state in repairs.items():
            client[database_name]["users_inventory"].update_one(
                {"_id": user_id}, {"$set": {"assistant_state": assistant_state}}
            )
        print(f"Applied repairs for {len(repairs)} accounts.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
