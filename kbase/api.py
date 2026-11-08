"""Flask blueprint for /api/v2. See specs/001-atlas-search-agent-lab/contracts/openapi.yaml."""
from __future__ import annotations

import threading
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, jsonify, request
from pymongo.errors import PyMongoError

from kbase.agent.sop_agent import RunError, RunNotFound
from kbase.container import Container
from kbase.memory.base import MemoryUnavailable, MemoryUnsupported
from kbase.memory.models import LONG_TERM_TYPES, MEMORY_TYPES
from kbase.search.pipelines import SearchParams

bp = Blueprint("kbase_v2", __name__, url_prefix="/api/v2")

_container: Container | None = None
_lock = threading.Lock()


def get_container() -> Container:
    global _container
    with _lock:
        if _container is None:
            _container = Container()
        return _container


def set_container(container: Container | None) -> None:
    """Swap the container (tests, or a settings change)."""
    global _container
    with _lock:
        _container = container


def _error(message: str, status: int, code: str):
    return jsonify({"error": message, "code": code}), status


def api(fn: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        try:
            return fn(*args, **kwargs)
        except RunNotFound as exc:
            return _error(f"not found: {exc.args[0] if exc.args else ''}", 404, "not_found")
        except (RunError, ValueError, TypeError) as exc:
            return _error(str(exc), 400, "bad_request")
        except MemoryUnsupported as exc:
            return _error(str(exc), 501, "not_supported")
        except MemoryUnavailable as exc:
            return _error(str(exc), 503, "memory_unavailable")
        except PyMongoError as exc:
            return _error(f"database error: {exc}", 503, "database")
    return wrapper


def _body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("request body must be a JSON object")
    return data


def _int(value: Any, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer") from None


def _float(value: Any, name: str, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number") from None


def search_params(data: dict[str, Any]) -> SearchParams:
    filters = data.get("filters") or {}
    weights = data.get("weights") or {}
    if not isinstance(filters, dict) or not isinstance(weights, dict):
        raise ValueError("filters and weights must be objects")
    return SearchParams(
        query=str(data.get("query") or ""),
        limit=_int(data.get("limit"), "limit") or 10,
        num_candidates=_int(data.get("num_candidates"), "num_candidates"),
        query_model=data.get("query_model") or None,
        category=filters.get("category") or None,
        domain=filters.get("domain") or None,
        vector_weight=_float(weights.get("vector"), "weights.vector", 1.0),
        text_weight=_float(weights.get("text"), "weights.text", 1.0),
        normalization=data.get("normalization") or "sigmoid",
        rerank=bool(data.get("rerank")),
        rerank_model=data.get("rerank_model") or None,
        fuzzy=bool(data.get("fuzzy")),
    )


# -- status ------------------------------------------------------------------------

@bp.get("/health")
@api
def health():
    return jsonify(get_container().health())


@bp.get("/capabilities")
@api
def capabilities():
    refresh = request.args.get("refresh", "false").lower() == "true"
    return jsonify(get_container().kb.capabilities(refresh=refresh))


@bp.get("/facets")
@api
def facets():
    return jsonify(get_container().kb.facets())


# -- search ------------------------------------------------------------------------

@bp.get("/search/methods")
@api
def methods():
    return jsonify({"methods": get_container().kb.methods()})


@bp.post("/search")
@api
def search():
    data = _body()
    return jsonify(get_container().kb.run(data.get("method") or "hybrid_rrf", search_params(data)))


@bp.post("/search/compare")
@api
def compare():
    data = _body()
    names = data.get("methods")
    if names is not None and not isinstance(names, list):
        raise ValueError("methods must be a list")
    return jsonify(get_container().kb.compare(names, search_params(data)))


# -- agent -------------------------------------------------------------------------

@bp.get("/agent/runs")
@api
def list_runs():
    user_id = (request.args.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("user_id is required")
    runs = get_container().agent.list(user_id)
    keep = ("id", "task", "status", "created_at", "updated_at", "procedure", "memory_backend")
    return jsonify({"runs": [{k: r.get(k) for k in keep} for r in runs]})


@bp.post("/agent/runs")
@api
def start_run():
    data = _body()
    run = get_container().agent.start(str(data.get("task") or ""), str(data.get("user_id") or ""),
                                      memory_backend=data.get("memory_backend") or None)
    return jsonify(run), 201


@bp.get("/agent/runs/<run_id>")
@api
def get_run(run_id: str):
    return jsonify(get_container().agent.get(run_id))


@bp.post("/agent/runs/<run_id>/choose")
@api
def choose(run_id: str):
    doc_id = str(_body().get("doc_id") or "").strip()
    if not doc_id:
        raise ValueError("doc_id is required")
    return jsonify(get_container().agent.choose(run_id, doc_id))


@bp.post("/agent/runs/<run_id>/steps/<step_id>")
@api
def confirm(run_id: str, step_id: str):
    data = _body()
    return jsonify(get_container().agent.confirm(run_id, step_id, str(data.get("status") or ""),
                                                 data.get("note") or None))


@bp.post("/agent/runs/<run_id>/messages")
@api
def message(run_id: str):
    return jsonify(get_container().agent.message(run_id, str(_body().get("content") or "")))


@bp.post("/agent/runs/<run_id>/finish")
@api
def finish(run_id: str):
    return jsonify(get_container().agent.finish(run_id))


# -- memory ------------------------------------------------------------------------

def _user(value: Any) -> str:
    user_id = str(value or "").strip()
    if not user_id:
        raise ValueError("user_id is required")
    return user_id


@bp.get("/memory/backends")
@api
def memory_backends():
    c = get_container()
    out = []
    for name in c.memory_backends:
        try:
            out.append({**c.store(name).describe(), "default": name == c.default_memory_backend})
        except Exception as exc:  # noqa: BLE001 - report, do not fail the listing
            out.append({"name": name, "error": str(exc), "default": name == c.default_memory_backend})
    return jsonify({"backends": out})


@bp.get("/memory")
@api
def list_memory():
    c = get_container()
    type_ = request.args.get("type") or None
    if type_ and type_ not in MEMORY_TYPES:
        raise ValueError(f"type must be one of {', '.join(MEMORY_TYPES)}")
    backend = request.args.get("backend") or c.default_memory_backend
    limit = min(max(_int(request.args.get("limit"), "limit") or 50, 1), 200)
    items = c.store(backend).list(_user(request.args.get("user_id")), type_, limit)
    return jsonify({"backend": backend, "items": [i.to_api(with_history=True) for i in items]})


@bp.post("/memory/search")
@api
def search_memory():
    c = get_container()
    data = _body()
    query = str(data.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    types = tuple(data.get("types") or LONG_TERM_TYPES)
    bad = [t for t in types if t not in MEMORY_TYPES]
    if bad:
        raise ValueError(f"unknown memory types: {', '.join(bad)}")
    limit = min(max(_int(data.get("limit"), "limit") or 8, 1), 50)
    result = c.manager(data.get("backend") or None).recall(query, _user(data.get("user_id")), types, limit)
    return jsonify(result.to_api())


@bp.post("/memory")
@api
def write_memory():
    c = get_container()
    data = _body()
    type_ = data.get("type")
    if type_ not in MEMORY_TYPES:
        raise ValueError(f"type must be one of {', '.join(MEMORY_TYPES)}")
    content = str(data.get("content") or "")
    if len(content) > 4000:
        raise ValueError("content must be at most 4000 characters")
    importance = data.get("importance")
    outcome = c.manager(data.get("backend") or None).remember(
        type_=type_, user_id=_user(data.get("user_id")), content=content, label=data.get("label") or None,
        importance=None if importance is None else _float(importance, "importance", 0.5),
        visibility=data.get("visibility") or "private", source={"manual": True})
    return jsonify(outcome.to_api()), 201


@bp.delete("/memory/<memory_id>")
@api
def delete_memory(memory_id: str):
    c = get_container()
    backend = request.args.get("backend") or c.default_memory_backend
    if not c.store(backend).delete(memory_id, _user(request.args.get("user_id"))):
        raise RunNotFound(memory_id)
    return jsonify({"deleted": True, "id": memory_id})


@bp.post("/memory/setup")
@api
def setup_memory():
    c = get_container()
    backend = request.args.get("backend") or c.default_memory_backend
    return jsonify({"backend": backend, "steps": c.store(backend).setup()})
