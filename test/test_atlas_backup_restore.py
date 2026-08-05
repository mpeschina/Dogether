from datetime import datetime, timezone

from scripts.backup_mongodb_atlas import backup_filename, mongodump_command
from scripts.restore_mongodb_atlas import mongorestore_command


def test_backup_filename_uses_the_current_app_date() -> None:
    assert backup_filename(datetime(2026, 8, 5, 12, tzinfo=timezone.utc)) == "atlas-backup-2026-08-05.archive.gz"


def test_mongodump_command_archives_the_configured_database(tmp_path) -> None:
    archive = tmp_path / "atlas-backup-2026-08-05.archive.gz"

    command = mongodump_command("mongodb+srv://example", "dogether", archive)

    assert command == [
        "mongodump",
        "--uri=mongodb+srv://example",
        "--db=dogether",
        f"--archive={archive}",
        "--gzip",
    ]


def test_mongorestore_command_limits_restore_to_the_configured_database_and_replaces_collections(tmp_path) -> None:
    archive = tmp_path / "atlas-backup-2026-08-05.archive.gz"

    command = mongorestore_command("mongodb+srv://example", "dogether", archive)

    assert command == [
        "mongorestore",
        "--uri=mongodb+srv://example",
        "--nsInclude=dogether.*",
        f"--archive={archive}",
        "--gzip",
        "--drop",
    ]
