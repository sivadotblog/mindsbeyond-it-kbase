"""Tests for the Atlas service account helper. All HTTP is mocked."""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import requests

from kbase.atlas_admin import AtlasAdmin, AtlasAdminError, connection_uri, grant, main, revoke, runner_ip

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
CLUSTER = {"name": "kbase", "mongoDBVersion": "8.3.1",
           "connectionStrings": {"standardSrv": "mongodb+srv://kbase.abcd.mongodb.net"}}


def resp(status=200, body=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.text = text or json.dumps(body or {})
    r.content = b"x" if body is not None else b""
    r.json.return_value = body if body is not None else {}
    return r


def admin_with(*responses, token_status=200):
    session = MagicMock()
    session.post.return_value = resp(token_status, {"access_token": "tok", "expires_in": 3600})
    session.request.side_effect = list(responses)
    return AtlasAdmin("mdb_sa_id_x", "mdb_sa_sk_y", session=session, clock=lambda: 1000.0), session


class TestClient:
    def test_needs_credentials(self):
        with pytest.raises(AtlasAdminError):
            AtlasAdmin("", "")

    def test_token_cached_and_sent(self):
        admin, session = admin_with(resp(body={"results": []}), resp(body={"results": []}))
        admin.list_projects()
        admin.list_projects()
        assert session.post.call_count == 1
        assert session.post.call_args[1]["auth"] == ("mdb_sa_id_x", "mdb_sa_sk_y")
        headers = session.request.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer tok" and "vnd.atlas" in headers["Accept"]

    def test_token_failure_is_redacted(self):
        admin, _ = admin_with(token_status=401)
        admin.session.post.return_value = resp(401, text="bad client_secret=mdb_sa_sk_y")
        with pytest.raises(AtlasAdminError) as exc:
            admin.token()
        assert "mdb_sa_sk_y" not in str(exc.value) and exc.value.status == 401

    def test_http_error(self):
        admin, _ = admin_with(resp(403, text="forbidden"))
        with pytest.raises(AtlasAdminError, match="403"):
            admin.list_projects()

    def test_resolve_single_project_and_cluster(self):
        admin, _ = admin_with(resp(body={"results": [{"id": "p1", "name": "kb"}]}), resp(body={"results": [CLUSTER]}))
        assert admin.resolve() == ("p1", CLUSTER)

    def test_resolve_needs_project_when_many(self):
        admin, _ = admin_with(resp(body={"results": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]}))
        with pytest.raises(AtlasAdminError, match="ATLAS_PROJECT_ID"):
            admin.resolve()

    def test_resolve_named_cluster(self):
        admin, _ = admin_with(resp(body={"results": [CLUSTER, {"name": "other"}]}),
                              resp(body={"results": [CLUSTER]}))
        assert admin.resolve("p1", "kbase")[1] is CLUSTER
        with pytest.raises(AtlasAdminError, match="not found"):
            admin.resolve("p1", "nope")

    def test_resolve_needs_cluster_when_many(self):
        admin, _ = admin_with(resp(body={"results": [CLUSTER, {"name": "other"}]}))
        with pytest.raises(AtlasAdminError, match="ATLAS_CLUSTER_NAME"):
            admin.resolve("p1")

    def test_create_user_body(self):
        admin, session = admin_with(resp(body={"username": "u"}))
        admin.create_db_user("p1", "kbase", "u", "pw", "kbase", NOW)
        body = session.request.call_args[1]["json"]
        assert body["scopes"] == [{"name": "kbase", "type": "CLUSTER"}]
        assert body["deleteAfterDate"] == "2026-11-08T12:00:00Z"
        assert {r["roleName"] for r in body["roles"]} == {"readWrite", "dbAdmin"}

    def test_delete_and_access_404s(self):
        admin, session = admin_with(resp(404), resp(204), resp(404), resp(body={"ipAddress": "1.2.3.4"}))
        assert admin.delete_db_user("p1", "u") is False
        assert admin.remove_access("p1", "1.2.3.4") is True
        assert admin.has_access_entry("p1", "1.2.3.4") is False
        assert admin.has_access_entry("p1", "1.2.3.4") is True
        assert session.request.call_args_list[0][0][1].endswith("/databaseUsers/admin/u")

    def test_add_access_body(self):
        admin, session = admin_with(resp(body={}))
        admin.add_access("p1", "1.2.3.4", NOW, "comment")
        assert session.request.call_args[1]["json"][0]["ipAddress"] == "1.2.3.4"


class TestHelpers:
    def test_runner_ip_falls_back(self):
        session = MagicMock()
        session.get.side_effect = [requests.ConnectionError("x"), resp(200, text="5.6.7.8\n")]
        assert runner_ip(session) == "5.6.7.8"

    def test_runner_ip_fails(self):
        session = MagicMock()
        session.get.return_value = resp(500, text="oops")
        with pytest.raises(AtlasAdminError):
            runner_ip(session)

    def test_connection_uri_escapes(self):
        uri = connection_uri(CLUSTER, "kb-smoke", "a/b+c")
        assert uri.startswith("mongodb+srv://kb-smoke:a%2Fb%2Bc@kbase.abcd.mongodb.net/?")

    def test_connection_uri_missing(self):
        with pytest.raises(AtlasAdminError):
            connection_uri({"name": "x"}, "u", "p")


class FakeAdmin:
    def __init__(self, has_ip=False, fail_delete=False):
        self.calls = []
        self.has_ip = has_ip
        self.fail_delete = fail_delete

    def resolve(self, project_id, cluster_name):
        return "p1", CLUSTER

    def create_db_user(self, *a):
        self.calls.append(("user", a))

    def has_access_entry(self, project_id, ip):
        return self.has_ip

    def add_access(self, *a, **k):
        self.calls.append(("ip", a))

    def delete_db_user(self, project_id, username):
        if self.fail_delete:
            raise AtlasAdminError("boom")
        self.calls.append(("del-user", username))
        return True

    def remove_access(self, project_id, ip):
        self.calls.append(("del-ip", ip))
        return False


class TestGrantRevoke:
    def test_grant_masks_and_exports(self):
        out, saved = [], []
        admin = FakeAdmin()
        state, env = grant(admin, project_id=None, cluster_name=None, db_name="kbase", ttl_hours=2, ip="1.2.3.4",
                           now=NOW, emit=out.append, in_actions=True, save=lambda s: saved.append(dict(s)))
        assert out[0].startswith("::add-mask::") and any(line.startswith("::add-mask::mongodb+srv") for line in out)
        assert env["MONGODB_URI"].startswith("mongodb+srv://kb-smoke-") and env["ATLAS_MONGODB_VERSION"] == "8.3.1"
        assert state["ip_preexisting"] is False and len(saved) == 2
        assert [c[0] for c in admin.calls] == ["user", "ip"]

    def test_grant_keeps_existing_ip(self):
        admin = FakeAdmin(has_ip=True)
        state, _ = grant(admin, project_id="p1", cluster_name="kbase", db_name="kbase", ttl_hours=1,
                         ip="1.2.3.4", emit=lambda s: None)
        assert state["ip_preexisting"] is True and [c[0] for c in admin.calls] == ["user"]

    def test_revoke(self):
        admin = FakeAdmin()
        msgs = []
        problems = revoke(admin, {"project_id": "p1", "username": "u", "ip": "1.2.3.4", "ip_preexisting": False},
                          emit=msgs.append)
        assert problems == [] and "already gone" in msgs[1]

    def test_revoke_preexisting_ip_untouched_and_problems(self):
        admin = FakeAdmin(fail_delete=True)
        problems = revoke(admin, {"project_id": "p1", "username": "u", "ip": "x", "ip_preexisting": True},
                          emit=lambda s: None)
        assert problems == ["boom"] and admin.calls == []


class TestCli:
    def test_grant_then_revoke(self, tmp_path):
        state = tmp_path / "state.json"
        env_file = tmp_path / "env"
        admin = FakeAdmin()
        environ = {"MDB_CLIENT": "c", "MDB_SECRET": "s", "GITHUB_ACTIONS": "true"}
        code = main(["grant", "--state", str(state), "--github-env", str(env_file)], environ,
                    admin_factory=lambda c, s: admin, ip_finder=lambda: "9.9.9.9")
        assert code == 0 and json.loads(state.read_text())["ip"] == "9.9.9.9"
        assert "MONGODB_URI=mongodb+srv://" in env_file.read_text()
        assert main(["revoke", "--state", str(state)], environ, admin_factory=lambda c, s: admin) == 0
        assert not state.exists()

    def test_revoke_without_state(self, tmp_path):
        assert main(["revoke", "--state", str(tmp_path / "none.json")], {"MDB_CLIENT": "c", "MDB_SECRET": "s"},
                    admin_factory=lambda c, s: FakeAdmin()) == 0

    def test_revoke_with_problems_keeps_state(self, tmp_path):
        state = tmp_path / "s.json"
        state.write_text(json.dumps({"project_id": "p", "username": "u", "ip": "x", "ip_preexisting": True}))
        code = main(["revoke", "--state", str(state)], {}, admin_factory=lambda c, s: FakeAdmin(fail_delete=True))
        assert code == 1 and state.exists()

    def test_bad_ttl_and_missing_credentials(self, tmp_path):
        assert main(["grant", "--ttl-hours", "48", "--state", str(tmp_path / "s")], {"MDB_CLIENT": "c", "MDB_SECRET": "s"},
                    admin_factory=lambda c, s: FakeAdmin(), ip_finder=lambda: "1.1.1.1") == 2
        assert main(["grant", "--state", str(tmp_path / "s")], {}, ip_finder=lambda: "1.1.1.1") == 2
