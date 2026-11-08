"""Remove secret looking values from free text before it is stored or shown.

The agent never asks for secrets, but people paste things into notes. This is a safety net, not a
guarantee, so it errs on the side of masking too much.
"""
from __future__ import annotations

import re

MASK = "[REDACTED]"

_SECRET_WORDS = r"(?:pass(?:word|wd)?|pwd|secret|token|api[_-]?key|apikey|private[_-]?key|client[_-]?secret|access[_-]?key)"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # PEM blocks
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), MASK),
    # user:password@ in connection strings
    (re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<user>[^:/\s@]+):(?P<pw>[^@\s]+)@", re.I),
     r"\g<scheme>\g<user>:" + MASK + "@"),
    # key=value, key: value, KEY="value"
    (re.compile(r"(?P<k>\b[\w.-]*" + _SECRET_WORDS + r"[\w.-]*\b\s*[:=]\s*)(?P<q>[\"']?)(?P<v>[^\s\"',;]+)(?P=q)", re.I),
     r"\g<k>\g<q>" + MASK + r"\g<q>"),
    # Authorization headers
    (re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.I), r"\1 " + MASK),
    # Well known token prefixes
    (re.compile(r"\bmdb_sa_sk_[A-Za-z0-9_-]+"), MASK),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}"), MASK),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), MASK),
    (re.compile(r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}"), MASK),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), MASK),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), MASK),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), MASK),
    # JWT
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), MASK),
]


def redact(text: str | None) -> str:
    """Return ``text`` with secret looking values replaced by ``[REDACTED]``."""
    if not text:
        return text or ""
    out = text
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    return out


def contains_secret(text: str | None) -> bool:
    """True when :func:`redact` would change ``text``."""
    return bool(text) and redact(text) != text


_SECRET_VAR = re.compile(r"(KEY|SECRET|PASS|PWD|TOKEN|CREDENTIAL|URI|CONN)", re.I)


def is_secret_name(name: str) -> bool:
    """True for variable names that must never be filled in from memory (``DB_PASS``, ``API_KEY``,
    and connection strings such as ``MONGODB_URI``, which usually carry a password)."""
    return bool(_SECRET_VAR.search(name or ""))
