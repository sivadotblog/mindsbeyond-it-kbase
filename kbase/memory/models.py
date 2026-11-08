"""Memory records and recall results shared by every backend."""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

MEMORY_TYPES = ("stm", "episodic", "semantic", "procedural", "taxonomic")
LONG_TERM_TYPES = ("episodic", "semantic", "procedural", "taxonomic")
VISIBILITIES = ("private", "org")
DEFAULT_IMPORTANCE = {"stm": 0.3, "episodic": 0.5, "semantic": 0.7, "procedural": 0.8, "taxonomic": 0.4}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


def label_key(label: str | None) -> str | None:
    """Normalize a label so "Cluster Name", "cluster_name" and "cluster-name" match."""
    if not label:
        return None
    key = re.sub(r"[^a-z0-9:]+", " ", label.lower()).strip()
    return key or None


def _aware(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


@dataclass
class MemoryRecord:
    type: str
    user_id: str
    content: str
    label: str | None = None
    agent_id: str | None = "sop-agent"
    visibility: str = "private"
    importance: float = 0.5
    source: dict[str, Any] | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.type not in MEMORY_TYPES:
            raise ValueError(f"memory type must be one of {', '.join(MEMORY_TYPES)}")
        if self.visibility not in VISIBILITIES:
            raise ValueError("visibility must be private or org")
        if not (self.user_id or "").strip():
            raise ValueError("user_id is required")
        if not (self.content or "").strip():
            raise ValueError("content is required")
        self.importance = min(max(float(self.importance), 0.0), 1.0)
        self.created_at = _aware(self.created_at) or utcnow()
        self.updated_at = _aware(self.updated_at) or self.created_at
        self.expires_at = _aware(self.expires_at)

    @property
    def label_key(self) -> str | None:
        return label_key(self.label)

    def to_doc(self) -> dict[str, Any]:
        """Shape stored in MongoDB."""
        doc = asdict(self)
        doc["_id"] = doc.pop("id")
        doc["label_key"] = self.label_key
        return doc

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "MemoryRecord":
        data = dict(doc)
        data["id"] = str(data.pop("_id", data.get("id") or new_id()))
        data.pop("label_key", None)
        data.pop("score", None)
        data.pop("score_parts", None)
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_api(self, *, with_history: bool = False) -> dict[str, Any]:
        out = {
            "id": self.id,
            "type": self.type,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "visibility": self.visibility,
            "label": self.label,
            "content": self.content,
            "importance": round(self.importance, 3),
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
        if with_history:
            out["history"] = [
                {**h, "at": h["at"].isoformat() if isinstance(h.get("at"), datetime) else h.get("at")}
                for h in self.history
            ]
        else:
            out["versions"] = len(self.history) + 1
        return out


@dataclass
class MemoryHit:
    record: MemoryRecord
    score: float
    relevance: float
    recency: float
    importance: float
    why: str = ""

    def to_api(self) -> dict[str, Any]:
        return {
            "record": self.record.to_api(),
            "score": round(self.score, 4),
            "score_parts": {
                "relevance": round(self.relevance, 4),
                "recency": round(self.recency, 4),
                "importance": round(self.importance, 4),
            },
            "why": self.why,
        }


@dataclass
class RecallResult:
    backend: str
    strategy: str
    hits: list[MemoryHit]
    pipeline: list[dict[str, Any]] | None = None
    ms: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_api(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "strategy": self.strategy,
            "hits": [h.to_api() for h in self.hits],
            "pipeline": self.pipeline,
            "ms": self.ms,
            "warnings": self.warnings,
        }
