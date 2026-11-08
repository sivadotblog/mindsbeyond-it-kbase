"""Live checks against a real cluster. Used by the manual live-smoke workflow.

``setup`` seeds the knowledge base and builds every index, then waits for them to be queryable.
``run`` checks each search method, rerank, memory and one agent run, and writes a markdown report.
A method the cluster does not support is reported as unsupported, not as a failure.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

from kbase.search.methods import METHODS
from kbase.search.pipelines import SearchParams

QUERY = "private endpoint connection timeout"
EXPECT = "KB-0016"
SMOKE_USER = "live-smoke"


@dataclass
class Check:
    name: str
    status: str  # pass | fail | unsupported | skipped
    detail: str = ""
    ms: float | None = None


def search_checks(kb: Any, query: str = QUERY, expect: str = EXPECT) -> list[Check]:
    checks = []
    plans = [(m, False) for m in METHODS] + [("vector_ann", True), ("hybrid_rrf", True)]
    for method, rerank in plans:
        name = f"{method}{' + rerank' if rerank else ''}"
        extra = {"domain": "Troubleshooting"} if method == "vector_filtered" else {}
        out = kb.run(method, SearchParams(query=query, limit=5, rerank=rerank, **extra))
        if out["status"] == "unsupported":
            checks.append(Check(name, "unsupported", out.get("reason") or "", out.get("ms")))
            continue
        if out["status"] != "ok":
            checks.append(Check(name, "fail", out.get("reason") or "error", out.get("ms")))
            continue
        ids = [r["doc_id"] for r in out["results"]]
        warn = "; ".join(out.get("warnings") or [])
        if expect in ids:
            checks.append(Check(name, "pass", f"{expect} at rank {ids.index(expect) + 1}" + (f" ({warn})" if warn else ""),
                                out.get("ms")))
        else:
            checks.append(Check(name, "fail", f"{expect} not in top 5: {ids}" + (f" ({warn})" if warn else ""),
                                out.get("ms")))
    return checks


def memory_checks(container: Any, *, wait_seconds: float = 30.0, sleep: Callable[[float], None] = time.sleep,
                  backend: str | None = None) -> list[Check]:
    label = f"memory {backend or container.default_memory_backend}"
    try:
        manager = container.manager(backend)
    except Exception as exc:  # noqa: BLE001
        return [Check(label, "skipped", str(exc))]
    checks = []
    try:
        out = manager.remember_fact(SMOKE_USER, "smoke cluster", "kbase-smoke")
        checks.append(Check(f"{label} write", "pass", f"{out.op} {out.record.id}"))
    except Exception as exc:  # noqa: BLE001
        return [Check(f"{label} write", "fail", str(exc))]
    deadline = time.monotonic() + wait_seconds
    result = None
    while True:
        result = manager.recall("smoke cluster", SMOKE_USER, ("semantic",), 5)
        if result.hits or time.monotonic() >= deadline:
            break
        sleep(3)
    status = "pass" if result.hits else "fail"
    checks.append(Check(f"{label} recall", status, f"{len(result.hits)} hits via {result.strategy}", result.ms))
    cleanup_memory(manager)
    return checks


def cleanup_memory(manager: Any) -> int:
    """Delete the smoke user's memories. Best effort: Agent Engine has no delete."""
    removed = 0
    try:
        for rec in manager.store.list(SMOKE_USER, None, 200):
            removed += bool(manager.store.delete(rec.id, SMOKE_USER))
    except Exception:  # noqa: BLE001
        pass
    return removed


def agent_checks(container: Any) -> list[Check]:
    try:
        run = container.agent.start(QUERY, SMOKE_USER)
    except Exception as exc:  # noqa: BLE001
        return [Check("agent start", "fail", str(exc))]
    chosen = (run.get("procedure") or {}).get("doc_id")
    checks = [Check("agent start", "pass" if chosen == EXPECT else "fail",
                    f"status {run['status']}, chose {chosen}, search {run['search'].get('method')}")]
    try:
        done = container.agent.finish(run["id"])
        checks.append(Check("agent finish", "pass", f"{len(done['memory_writes'])} memory writes"))
    except Exception as exc:  # noqa: BLE001
        checks.append(Check("agent finish", "fail", str(exc)))
    return checks


def render(caps: dict[str, Any], checks: list[Check]) -> str:
    lines = ["## Live smoke report", "",
             f"- Mode: {caps.get('mode')}",
             f"- MongoDB version: {caps.get('server_version') or 'unknown'}",
             f"- autoEmbed query format: {caps.get('query_format')}", ""]
    if caps.get("indexes"):
        lines += ["| Index | Type | Status | Queryable |", "|---|---|---|---|"]
        lines += [f"| {i['name']} | {i.get('type', '')} | {i.get('status')} | {i.get('queryable')} |"
                  for i in caps["indexes"]]
        lines.append("")
    icons = {"pass": "PASS", "fail": "FAIL", "unsupported": "UNSUPPORTED", "skipped": "SKIPPED"}
    lines += ["| Check | Result | Detail | ms |", "|---|---|---|---|"]
    for c in checks:
        detail = c.detail.replace("|", "/")
        lines.append(f"| {c.name} | {icons[c.status]} | {detail} | {'' if c.ms is None else c.ms} |")
    counts = {k: sum(1 for c in checks if c.status == k) for k in icons}
    lines += ["", f"{counts['pass']} passed, {counts['fail']} failed, {counts['unsupported']} unsupported, "
                  f"{counts['skipped']} skipped."]
    return "\n".join(lines) + "\n"


def wait_for_indexes(collections: list[Any], timeout: float, sleep: Callable[[float], None] = time.sleep,
                     clock: Callable[[], float] = time.monotonic) -> list[str]:
    """Wait until every search index on the collections is queryable. Returns the ones that are not."""
    deadline = clock() + timeout
    while True:
        pending = []
        for coll in collections:
            for ix in coll.list_search_indexes():
                if not ix.get("queryable"):
                    pending.append(f"{coll.name}.{ix.get('name')} ({ix.get('status')})")
        if not pending or clock() >= deadline:
            return pending
        sleep(10)


def wait_for_connection(client: Any, timeout: float = 180, sleep: Callable[[float], None] = time.sleep,
                        clock: Callable[[], float] = time.monotonic) -> None:
    """New database users and access entries take a little while to apply."""
    deadline = clock() + timeout
    while True:
        try:
            client.admin.command("ping")
            return
        except Exception:  # noqa: BLE001
            if clock() >= deadline:
                raise
            sleep(10)


def main(argv: list[str] | None = None, container_factory: Callable[[], Any] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m kbase.smoke")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("setup", help="seed data, build indexes, wait for them")
    s.add_argument("--wait", type=float, default=600)
    s.add_argument("--skip-seed", action="store_true")
    r = sub.add_parser("run", help="run the checks and write a report")
    r.add_argument("--report", default="smoke-report.md")
    args = parser.parse_args(argv)

    if container_factory is None:  # pragma: no cover - real wiring
        from kbase.container import Container
        container_factory = Container
    container = container_factory()
    if container.settings.offline:
        print("::error::MONGODB_URI is not set; the smoke run needs a live cluster", file=sys.stderr)
        return 2
    wait_for_connection(container.client)

    if args.command == "setup":
        if not args.skip_seed:
            import app as kb_app
            import generate_kbase
            generate_kbase.generate_markdown_files()
            generate_kbase.insert_into_mongodb()
            print("Seeded 50 articles")
            print(kb_app.create_search_indexes())
        print("\n".join(container.store("atlas").setup()))
        s = container.settings
        pending = wait_for_indexes([container.db[s.collection_name], container.db[s.memory_collection]], args.wait)
        if pending:
            print("::warning::indexes still building: " + ", ".join(pending))
        return 0

    caps = container.kb.capabilities(refresh=True)
    checks = search_checks(container.kb)
    for backend in container.memory_backends:
        if backend != "inmemory":
            checks += memory_checks(container, backend=backend)
    checks += agent_checks(container)
    try:
        cleanup_memory(container.manager())
    except Exception:  # noqa: BLE001
        pass
    report = render(caps, checks)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(report)
    return 1 if any(c.status == "fail" for c in checks) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
