"""Parse the generated knowledge base markdown into the same shape as the Atlas documents.

Offline search and the SOP checklist builder both use this, so an article read from disk and an
article read from Atlas look the same to the rest of the code.
"""
from __future__ import annotations

import os
import re
from typing import Any

_CODE_BLOCK = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)
_FIELD = re.compile(r"^\*\*(?P<k>[^*]+)\*\*:\s*(?P<v>.+?)\s*$", re.M)


def _section(md: str, heading: str, level: int = 2) -> str:
    """Return the text under ``## heading`` (or ``###``) up to the next heading of that level or
    higher. Lines inside code fences are never treated as headings."""
    start = re.compile(rf"^#{{{level}}}\s+{re.escape(heading)}")
    stop = re.compile(rf"^#{{1,{level}}}\s")
    body: list[str] = []
    inside = False
    in_fence = False
    for line in md.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not inside:
            if not in_fence and start.match(line):
                inside = True
            continue
        if not in_fence and stop.match(line) and not line.strip().startswith("```"):
            break
        body.append(line)
    return "\n".join(body).strip()


def _commands(block_text: str) -> str:
    """Code block content without comments, blank lines and the shared billing exports."""
    lines = []
    for raw in block_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export MINDSBEYOND_"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _first_code(text: str) -> str:
    m = _CODE_BLOCK.search(text)
    return _commands(m.group(1)) if m else ""


def parse_article(md: str) -> dict[str, Any]:
    """Parse one generated article. Missing parts come back as empty strings."""
    fields = {m.group("k").strip().lower(): m.group("v").strip() for m in _FIELD.finditer(md)}
    title_match = re.search(r"^#\s+(?:How To:\s*)?(.+?)\s*$", md, re.M)
    title = title_match.group(1).strip() if title_match else ""

    prereq_body = _section(md, "Prerequisites")
    prereq_items = [
        re.sub(r"\*\*", "", m.group(1)).strip()
        for m in re.finditer(r"^\s*\d+\.\s+(.+)$", prereq_body, re.M)
    ]
    tooling = ""
    for item in prereq_items:
        if item.lower().startswith("tooling & access:"):
            tooling = item.split(":", 1)[1].strip().rstrip(".")

    step1 = _first_code(_section(md, "Step 1", level=3))
    step2 = _first_code(_section(md, "Step 2", level=3))
    verify = _first_code(_section(md, "Verification", level=2))

    error_match = re.search(r"\*\*Error Message\*\*:\s*`([^`]+)`", md)
    resolution_match = re.search(r"\*\*Resolution\*\*:\s*(.+)", md)

    return {
        "doc_id": fields.get("document id", ""),
        "title": title,
        "category": fields.get("category", ""),
        "domain": fields.get("domain", ""),
        "prerequisites": tooling,
        "prerequisite_items": prereq_items,
        "steps": {"step1": step1, "step2": step2, "verify": verify},
        "troubleshooting": {
            "error": error_match.group(1).strip() if error_match else "",
            "solution": resolution_match.group(1).strip() if resolution_match else "",
        },
        "raw_markdown": md,
    }


def load_articles(md_dir: str) -> list[dict[str, Any]]:
    """Load and parse every ``*.md`` file in ``md_dir``, sorted by file name."""
    if not os.path.isdir(md_dir):
        return []
    docs = []
    for name in sorted(os.listdir(md_dir)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(md_dir, name), encoding="utf-8") as fh:
            doc = parse_article(fh.read())
        if doc["doc_id"]:
            docs.append(doc)
    return docs
