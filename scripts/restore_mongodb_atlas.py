#!/usr/bin/env python3
"""Restore a gzip-compressed MongoDB archive with mongorestore."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.backup_mongodb_atlas import load_mongodb_settings  # noqa: E402


def mongorestore_command(uri: str, database: str, archive_path: Path) -> list[str]:
    return [
        "mongorestore",
        f"--uri={uri}",
        f"--nsInclude={database}.*",
        f"--archive={archive_path}",
        "--gzip",
        "--drop",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore a MongoDB archive into the configured Atlas database.")
    parser.add_argument("backup_file", type=Path, help="Gzip-compressed mongodump archive to restore.")
    parser.add_argument("--apply", action="store_true", help="Replace archived collection contents with mongorestore --drop.")
    parser.add_argument(
        "--confirm-database",
        help="Required with --apply; must exactly match the configured target database.",
    )
    parser.add_argument(
        "--secrets-path",
        type=Path,
        default=REPOSITORY_ROOT / ".streamlit" / "secrets.toml",
        help="Path to Streamlit secrets TOML (default: %(default)s).",
    )
    args = parser.parse_args(argv)
    try:
        uri, database = load_mongodb_settings(args.secrets_path)
    except ValueError as exc:
        parser.error(str(exc))
    if not args.backup_file.is_file():
        parser.error(f"Backup file not found: {args.backup_file}")
    if not args.apply:
        print("Dry run: no changes written. Re-run with --apply and --confirm-database to restore.")
        return 0
    if args.confirm_database != database:
        parser.error("--apply requires --confirm-database with the configured target database name.")

    try:
        subprocess.run(mongorestore_command(uri, database, args.backup_file), check=True)
    except FileNotFoundError:
        parser.error("mongorestore is not installed. Install MongoDB Database Tools and try again.")
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1

    print(f"Restored MongoDB archive into {database}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
