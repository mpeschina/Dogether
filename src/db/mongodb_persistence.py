"""MongoDB persistence backend for Dogether."""
from __future__ import annotations

import copy
from typing import Any

from .document_persistence import DocumentPersistence
from .persistence_helpers import _empty_store, _normalise_store


class MongoPersistence(DocumentPersistence):
    """Document-backed MongoDB persistence.

    The current app logic expects an atomic whole-store read/write model. This
    backend keeps that contract by storing the normalized Dogether store in one
    MongoDB document, while the persistence factory owns the connection setup.
    """

    def __init__(
        self,
        uri: str = "",
        database: str = "dogether",
        collection: str = "users",
        *,
        store_id: str = "app_store",
        mongo_collection: Any | None = None,
    ) -> None:
        self.store_id = store_id
        self.uri = uri
        self.database = database
        self.collection_name = collection
        self._client = None
        self._collection = mongo_collection
        if mongo_collection is None and not uri:
            raise ValueError("MongoDB persistence requires mongodb_uri.")

    @property
    def collection(self) -> Any:
        if self._collection is None:
            from pymongo import MongoClient

            self._client = MongoClient(self.uri)
            self._collection = self._client[self.database][self.collection_name]
        return self._collection

    def _read(self) -> dict[str, Any]:
        document = self.collection.find_one({"_id": self.store_id})
        if not document:
            return _empty_store()
        data = document.get("data", {})
        if not isinstance(data, dict):
            return _empty_store()
        return _normalise_store(copy.deepcopy(data))

    def _write(self, data: dict[str, Any]) -> None:
        store = _normalise_store(copy.deepcopy(data))
        self.collection.replace_one(
            {"_id": self.store_id},
            {"_id": self.store_id, "data": store},
            upsert=True,
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
