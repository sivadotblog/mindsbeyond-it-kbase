"""Tests for secret redaction."""
import pytest

from kbase.redact import MASK, contains_secret, is_secret_name, redact

SECRETS = [
    ("password=hunter2", "hunter2"),
    ("DB_PASS: 's3cr3t!'", "s3cr3t!"),
    ("mongodb+srv://app:Pa55word@kbase.mongodb.net/db", "Pa55word"),
    ("Authorization: Bearer abcdefghijklmnop", "abcdefghijklmnop"),
    ("client secret is mdb_sa_sk_AbC123xyz", "mdb_sa_sk_AbC123xyz"),
    ("key sk-ant-api03-abcdefghij", "sk-ant-api03-abcdefghij"),
    ("token ghp_abcdefghijklmnopqrstuvwxyz123456", "ghp_abcdefghijklmnopqrstuvwxyz123456"),
    ("aws AKIAABCDEFGHIJKLMNOP here", "AKIAABCDEFGHIJKLMNOP"),
    ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcdefghijk", "eyJhbGciOiJIUzI1NiJ9"),
    ("-----BEGIN PRIVATE KEY-----\nMIIabc\n-----END PRIVATE KEY-----", "MIIabc"),
    ("api_key=\"abc123\"", "abc123"),
]


@pytest.mark.parametrize("text,secret", SECRETS)
def test_masks_secret(text, secret):
    out = redact(text)
    assert secret not in out and MASK in out


@pytest.mark.parametrize("text", ["our cluster is kbase-prod", "port 10260 refused", "", None])
def test_leaves_normal_text(text):
    assert redact(text) == (text or "")
    assert not contains_secret(text)


def test_keeps_user_in_uri():
    assert redact("mongodb://alice:pw@h/") == f"mongodb://alice:{MASK}@h/"


@pytest.mark.parametrize("name,expected", [("DB_PASS", True), ("API_KEY", True), ("MONGODB_URI", True),
                                           ("CLUSTER", False), ("ATLAS_PROJECT_ID", False), ("", False)])
def test_secret_names(name, expected):
    assert is_secret_name(name) is expected
