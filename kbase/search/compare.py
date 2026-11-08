"""Agreement between the result lists of several search methods."""
from __future__ import annotations

from itertools import combinations
from typing import Any


def _ids(result: dict[str, Any]) -> list[str]:
    return [r["doc_id"] for r in result.get("results", [])]


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def agreement(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Pairwise Jaccard, a consensus list and ANN recall when both vector methods ran.

    Only methods with ``status == "ok"`` take part.
    """
    ok = {name: r for name, r in results.items() if r.get("status") == "ok"}
    pairs = []
    for a, b in combinations(sorted(ok), 2):
        ia, ib = _ids(ok[a]), _ids(ok[b])
        pairs.append({
            "a": a,
            "b": b,
            "jaccard": round(jaccard(ia, ib), 3),
            "common": sorted(set(ia) & set(ib)),
        })

    seen: dict[str, dict[str, Any]] = {}
    for name, r in ok.items():
        for item in r.get("results", []):
            entry = seen.setdefault(item["doc_id"], {
                "doc_id": item["doc_id"], "title": item.get("title", ""), "methods": [], "ranks": [],
            })
            entry["methods"].append(name)
            entry["ranks"].append(item["rank"])
    consensus = []
    for entry in seen.values():
        if len(entry["methods"]) < 2:
            continue
        consensus.append({
            "doc_id": entry["doc_id"],
            "title": entry["title"],
            "methods": sorted(entry["methods"]),
            "avg_rank": round(sum(entry["ranks"]) / len(entry["ranks"]), 2),
        })
    consensus.sort(key=lambda e: (-len(e["methods"]), e["avg_rank"]))

    out: dict[str, Any] = {"pairs": pairs, "consensus": consensus[:10]}
    if "vector_ann" in ok and "vector_enn" in ok:
        enn = _ids(ok["vector_enn"])
        ann = set(_ids(ok["vector_ann"]))
        out["ann_recall"] = round(len(ann & set(enn)) / len(enn), 3) if enn else None
    return out
