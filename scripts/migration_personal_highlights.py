#!/usr/bin/env python3
"""Backfill Personal Highlights from native MongoDB goal progress.

Run from the repository root. The script previews changes by default; pass
``--apply`` to write them to MongoDB.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from copy import deepcopy
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Iterable, Mapping

from pymongo import MongoClient


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.db.persistence_helpers import APP_ZONE  # noqa: E402


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _valid_iso_timestamp(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return None
    return value


def _outcome_timestamp(period_key: Any) -> str | None:
    if not isinstance(period_key, str):
        return None
    try:
        period_date = date.fromisoformat(period_key)
    except ValueError:
        return None
    return datetime.combine(period_date, time.min, tzinfo=APP_ZONE).isoformat()


def _existing_repetitions(record: Any) -> int:
    return _positive_int(record.get("repetitions")) if isinstance(record, Mapping) else 0


def _goal_candidates(goal: Mapping[str, Any]) -> Iterable[tuple[str, str, int, str]]:
    """Yield (user id, goal id, repetitions, period-start timestamp) candidates."""
    goal_id = goal.get("id", goal.get("_id"))
    participants = goal.get("participants")
    if not isinstance(goal_id, str) or not goal_id or not isinstance(participants, Mapping):
        return

    for user_id, participant in participants.items():
        if not isinstance(user_id, str) or not user_id or not isinstance(participant, Mapping):
            continue
        if participant.get("left_at"):
            continue

        current_target = _positive_int(participant.get("target"))
        current_timestamp = _valid_iso_timestamp(participant.get("period_start"))
        current_repetitions = _positive_int(participant.get("current"))
        if current_target > 1 and current_repetitions and current_timestamp:
            yield user_id, goal_id, current_repetitions, current_timestamp

        outcomes = participant.get("period_outcomes")
        if not isinstance(outcomes, Mapping):
            continue
        for period_key, outcome in outcomes.items():
            if not isinstance(outcome, Mapping):
                continue
            target = _positive_int(outcome.get("target", participant.get("target")))
            repetitions = _positive_int(outcome.get("current"))
            timestamp = _outcome_timestamp(period_key)
            if target > 1 and repetitions and timestamp:
                yield user_id, goal_id, repetitions, timestamp


def planned_personal_highlight_updates(
    goals: Iterable[Mapping[str, Any]], users: Iterable[Mapping[str, Any]]
) -> dict[str, dict[str, dict[str, Any]]]:
    """Return strictly improved personal-best records, grouped by existing user."""
    existing_users = {
        str(user["_id"]): user
        for user in users
        if isinstance(user, Mapping) and isinstance(user.get("_id"), str) and user["_id"]
    }
    candidates: dict[tuple[str, str], tuple[int, str]] = {}
    for goal in goals:
        for user_id, goal_id, repetitions, achieved_at in _goal_candidates(goal):
            if user_id not in existing_users:
                continue
            candidate_key = (user_id, goal_id)
            prior = candidates.get(candidate_key)
            if prior is None or repetitions > prior[0] or (repetitions == prior[0] and achieved_at < prior[1]):
                candidates[candidate_key] = (repetitions, achieved_at)

    updates: dict[str, dict[str, dict[str, Any]]] = {}
    for (user_id, goal_id), (repetitions, achieved_at) in candidates.items():
        personal_bests = existing_users[user_id].get("personal_bests", {})
        existing = personal_bests.get(goal_id) if isinstance(personal_bests, Mapping) else None
        if repetitions > _existing_repetitions(existing):
            updates.setdefault(user_id, {})[goal_id] = {
                "repetitions": repetitions,
                "achieved_at": achieved_at,
            }
    return updates


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
    if not isinstance(uri, str) or not uri.strip():
        raise ValueError("[persistence] mongodb_uri must be configured in Streamlit secrets.")
    database = persistence.get("mongodb_database", "dogether")
    if not isinstance(database, str) or not database.strip():
        raise ValueError("[persistence] mongodb_database must be a non-empty string.")
    return uri, database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Personal Highlights from MongoDB goals.")
    parser.add_argument("--apply", action="store_true", help="Write the planned updates to MongoDB.")
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
        database = client[database_name]
        users = list(database["users_inventory"].find({}, {"_id": 1, "personal_bests": 1}))
        goals = list(database["goals"].find({"archived_at": None}))
        updates = planned_personal_highlight_updates(goals, users)
        record_count = sum(len(records) for records in updates.values())
        print(f"Scanned {len(goals)} active goals and {len(users)} users.")
        print(f"Planned {record_count} Personal Highlight records for {len(updates)} users.")

        if not args.apply:
            print("Dry run: no changes written. Re-run with --apply to persist these updates.")
            return 0

        for user_id, records in updates.items():
            database["users_inventory"].update_one(
                {"_id": user_id},
                {"$set": {f"personal_bests.{goal_id}": deepcopy(record) for goal_id, record in records.items()}},
            )
        print(f"Applied {record_count} Personal Highlight records for {len(updates)} users.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
