#!/usr/bin/env python3
"""Create a complete gzip-compressed Atlas archive with mongodump."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.db.persistence_helpers import APP_ZONE  # noqa: E402


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


def backup_filename(now: datetime | None = None) -> str:
    current = now or datetime.now(APP_ZONE)
    current = current.replace(tzinfo=APP_ZONE) if current.tzinfo is None else current.astimezone(APP_ZONE)
    return f"atlas-backup-{current.date().isoformat()}.archive.gz"


def mongodump_command(uri: str, database: str, archive_path: Path) -> list[str]:
    return [
        "mongodump",
        f"--uri={uri}",
        f"--db={database}",
        f"--archive={archive_path}",
        "--gzip",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up the configured MongoDB Atlas database with mongodump.")
    parser.add_argument(
        "--secrets-path",
        type=Path,
        default=REPOSITORY_ROOT / ".streamlit" / "secrets.toml",
        help="Path to Streamlit secrets TOML (default: %(default)s).",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=REPOSITORY_ROOT / "backups",
        help="Directory for the date-named archive (default: %(default)s).",
    )
    args = parser.parse_args(argv)
    try:
        uri, database = load_mongodb_settings(args.secrets_path)
    except ValueError as exc:
        parser.error(str(exc))

    args.output_directory.mkdir(parents=True, exist_ok=True)
    archive_path = args.output_directory / backup_filename()
    if archive_path.exists():
        parser.error(f"Backup already exists: {archive_path}")
    try:
        subprocess.run(mongodump_command(uri, database, archive_path), check=True)
    except FileNotFoundError:
        parser.error("mongodump is not installed. Install MongoDB Database Tools and try again.")
    except subprocess.CalledProcessError as exc:
        archive_path.unlink(missing_ok=True)
        return exc.returncode or 1

    print(f"Created MongoDB archive: {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
