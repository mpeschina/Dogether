"""Short-lived document cache for persistence backends."""
from __future__ import annotations

import copy
from time import monotonic
from typing import Any

from .document_persistence import DocumentPersistence


DEFAULT_PERSISTENCE_CACHE_TTL_SECONDS = 5.0
DEBUG_PRINT = False


class CachedDocumentPersistence(DocumentPersistence):
    """Cache whole-store reads briefly while keeping writes immediately visible."""

    def __init__(self, cache_ttl_seconds: float = DEFAULT_PERSISTENCE_CACHE_TTL_SECONDS) -> None:
        self.cache_ttl_seconds = float(cache_ttl_seconds)
        self._cached_data: dict[str, Any] | None = None
        self._cached_at: float | None = None

    def _read_uncached(self) -> dict[str, Any]:
        raise NotImplementedError

    def _write_uncached(self, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def _cache_enabled(self) -> bool:
        return self.cache_ttl_seconds > 0

    def _read(self) -> dict[str, Any]:
        if not self._cache_enabled():
            return self._read_uncached()

        now = monotonic()
        if (
            self._cached_data is not None
            and self._cached_at is not None
            and now - self._cached_at <= self.cache_ttl_seconds
        ):
            if DEBUG_PRINT:
                print(f"Read cached (since {now - self._cached_at})")
            return copy.deepcopy(self._cached_data)

        if DEBUG_PRINT:
            print("Read from db")
        data = self._read_uncached()
        self._cached_data = copy.deepcopy(data)
        self._cached_at = now
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self._write_uncached(data)
        if self._cache_enabled():
            if DEBUG_PRINT:
                print(f"Write to cache and db")
            self._cached_data = copy.deepcopy(data)
            self._cached_at = monotonic()
        else:
            self._cached_data = None
            self._cached_at = None
