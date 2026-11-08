"""Where SOP runs are kept: MongoDB when connected, a dict otherwise."""
from __future__ import annotations

import copy
import threading
from typing import Any

from pymongo import DESCENDING


class InMemoryRunStore:
    name = "inmemory"

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def save(self, run: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._runs[run["id"]] = copy.deepcopy(run)
        return run

    def get(self, run_id: str) -> dict[str, Any] | None:
        run = self._runs.get(run_id)
        return copy.deepcopy(run) if run else None

    def list(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        runs = [r for r in self._runs.values() if r["user_id"] == user_id]
        runs.sort(key=lambda r: r["updated_at"], reverse=True)
        return [copy.deepcopy(r) for r in runs[:limit]]


class MongoRunStore:
    name = "atlas"

    def __init__(self, collection: Any):
        self.collection = collection
        self._indexed = False

    def _ensure_index(self) -> None:
        if not self._indexed:
            self.collection.create_index([("user_id", 1), ("updated_at", DESCENDING)], name="user_updated")
            self._indexed = True

    def save(self, run: dict[str, Any]) -> dict[str, Any]:
        self._ensure_index()
        doc = dict(run)
        doc["_id"] = doc.pop("id")
        self.collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        return run

    @staticmethod
    def _out(doc: dict[str, Any]) -> dict[str, Any]:
        doc = dict(doc)
        doc["id"] = doc.pop("_id")
        return doc

    def get(self, run_id: str) -> dict[str, Any] | None:
        doc = self.collection.find_one({"_id": run_id})
        return self._out(doc) if doc else None

    def list(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        cursor = self.collection.find({"user_id": user_id}, {"trace": 0}).sort("updated_at", DESCENDING).limit(limit)
        return [self._out(d) for d in cursor]
