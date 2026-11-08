"""The interface every memory backend implements."""
from __future__ import annotations

from typing import Any, Protocol

from kbase.memory.models import MemoryRecord, RecallResult


class MemoryUnsupported(Exception):
    """The backend cannot do this operation. The message says why."""


class MemoryUnavailable(Exception):
    """The backend is configured but cannot be reached or built."""


class MemoryStore(Protocol):
    name: str
    capabilities: dict[str, bool]

    def write(self, record: MemoryRecord) -> MemoryRecord: ...

    def update(self, record: MemoryRecord) -> MemoryRecord: ...

    def find_by_label(self, user_id: str, type_: str, label: str) -> MemoryRecord | None: ...

    def list(self, user_id: str, type_: str | None = None, limit: int = 50) -> list[MemoryRecord]: ...

    def recall(self, query: str, user_id: str, types: tuple[str, ...], limit: int = 8) -> RecallResult: ...

    def delete(self, memory_id: str, user_id: str) -> bool: ...

    def setup(self) -> list[str]: ...

    def describe(self) -> dict[str, Any]: ...
