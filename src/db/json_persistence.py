"""JSON persistence backend for Dogether."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .cached_document_persistence import (
    DEFAULT_PERSISTENCE_CACHE_TTL_SECONDS,
    CachedDocumentPersistence,
)
from .persistence_helpers import _empty_store, _normalise_store


class JsonPersistence(CachedDocumentPersistence):
    """Atomic JSON persistence for Dogether."""

    def __init__(
        self,
        path: str | Path = "data/users.json",
        cache_ttl_seconds: float = DEFAULT_PERSISTENCE_CACHE_TTL_SECONDS,
    ) -> None:
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)
        self.path = Path(path)

    def _read_uncached(self) -> dict[str, Any]:
        if not self.path.exists():
            return _empty_store()

        with self.path.open(encoding="utf-8") as file:
            loaded = json.load(file)

        if not isinstance(loaded, dict):
            return _empty_store()
        return _normalise_store(loaded)

    def _write_uncached(self, data: dict[str, Any]) -> None:
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
