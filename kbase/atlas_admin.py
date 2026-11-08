"""Short lived Atlas access for CI, from an Atlas service account.

A service account (client id and secret) reaches only the Atlas Administration API, not cluster
data. To run live checks the workflow:

1. mints an OAuth access token with the client credentials,
2. finds the project and cluster (or uses the ones given),
3. creates a database user and an IP access list entry, both with ``deleteAfterDate`` so they
   expire on their own even if the job is killed,
4. writes ``MONGODB_URI`` to ``$GITHUB_ENV`` with the password masked in the log,
5. and in an always run step, deletes both.

Usage::

    MDB_CLIENT=... MDB_SECRET=... python -m kbase.atlas_admin grant --ttl-hours 2 --github-env "$GITHUB_ENV"
    MDB_CLIENT=... MDB_SECRET=... python -m kbase.atlas_admin revoke
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import quote, quote_plus

import requests

from kbase.redact import redact

API_BASE = "https://cloud.mongodb.com"
ACCEPT = "application/vnd.atlas.2023-01-01+json"
IP_SERVICES = ("https://checkip.amazonaws.com", "https://api.ipify.org")
STATE_FILE = ".atlas-access.json"


class AtlasAdminError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class AtlasAdmin:
    def __init__(self, client_id: str, client_secret: str, *, base: str = API_BASE, session: Any = None,
                 clock: Callable[[], float] = time.time):
        if not client_id or not client_secret:
            raise AtlasAdminError("MDB_CLIENT and MDB_SECRET are required")
        self.client_id = client_id
        self.client_secret = client_secret
        self.base = base.rstrip("/")
        self.session = session or requests.Session()
        self.clock = clock
        self._token: str | None = None
        self._expires = 0.0

    def token(self) -> str:
        if self._token and self.clock() < self._expires - 60:
            return self._token
        resp = self.session.post(f"{self.base}/api/oauth/token", auth=(self.client_id, self.client_secret),
                                 data={"grant_type": "client_credentials"},
                                 headers={"Accept": "application/json"}, timeout=30)
        if resp.status_code != 200:
            raise AtlasAdminError(f"token request failed with HTTP {resp.status_code}: {redact(resp.text[:300])}",
                                  resp.status_code)
        body = resp.json()
        self._token = body["access_token"]
        self._expires = self.clock() + float(body.get("expires_in", 3600))
        return self._token

    def _req(self, method: str, path: str, *, ok404: bool = False, **kwargs: Any) -> Any:
        headers = {"Authorization": f"Bearer {self.token()}", "Accept": ACCEPT}
        if "json" in kwargs:
            headers["Content-Type"] = ACCEPT
        resp = self.session.request(method, f"{self.base}/api/atlas/v2{path}", headers=headers, timeout=60, **kwargs)
        if ok404 and resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise AtlasAdminError(f"{method} {path} failed with HTTP {resp.status_code}: {redact(resp.text[:300])}",
                                  resp.status_code)
        return resp.json() if resp.content else {}

    # -- discovery ----------------------------------------------------------------
    def list_projects(self) -> list[dict[str, Any]]:
        return self._req("GET", "/groups", params={"itemsPerPage": 500}).get("results", [])

    def list_clusters(self, project_id: str) -> list[dict[str, Any]]:
        return self._req("GET", f"/groups/{project_id}/clusters").get("results", [])

    def resolve(self, project_id: str | None = None, cluster_name: str | None = None) -> tuple[str, dict[str, Any]]:
        if not project_id:
            projects = self.list_projects()
            if len(projects) != 1:
                names = ", ".join(f"{p.get('name')} ({p.get('id')})" for p in projects) or "none"
                raise AtlasAdminError(f"set ATLAS_PROJECT_ID; the service account sees {len(projects)} projects: {names}")
            project_id = projects[0]["id"]
        clusters = self.list_clusters(project_id)
        if cluster_name:
            match = [c for c in clusters if c.get("name") == cluster_name]
            if not match:
                raise AtlasAdminError(f"cluster {cluster_name} not found in project {project_id}")
            return project_id, match[0]
        if len(clusters) != 1:
            names = ", ".join(c.get("name", "?") for c in clusters) or "none"
            raise AtlasAdminError(f"set ATLAS_CLUSTER_NAME; project {project_id} has {len(clusters)} clusters: {names}")
        return project_id, clusters[0]

    # -- temporary access ---------------------------------------------------------
    def create_db_user(self, project_id: str, cluster_name: str, username: str, password: str, db_name: str,
                       delete_after: datetime) -> dict[str, Any]:
        body = {
            "databaseName": "admin",
            "username": username,
            "password": password,
            "roles": [{"roleName": "readWrite", "databaseName": db_name},
                      {"roleName": "dbAdmin", "databaseName": db_name}],
            "scopes": [{"name": cluster_name, "type": "CLUSTER"}],
            "deleteAfterDate": delete_after.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "description": "Temporary user for the live-smoke GitHub workflow",
        }
        return self._req("POST", f"/groups/{project_id}/databaseUsers", json=body)

    def delete_db_user(self, project_id: str, username: str) -> bool:
        return self._req("DELETE", f"/groups/{project_id}/databaseUsers/admin/{quote(username, safe='')}",
                         ok404=True) is not None

    def has_access_entry(self, project_id: str, ip: str) -> bool:
        return self._req("GET", f"/groups/{project_id}/accessList/{quote(ip, safe='')}", ok404=True) is not None

    def add_access(self, project_id: str, ip: str, delete_after: datetime, comment: str) -> dict[str, Any]:
        body = [{"ipAddress": ip, "comment": comment[:80],
                 "deleteAfterDate": delete_after.strftime("%Y-%m-%dT%H:%M:%SZ")}]
        return self._req("POST", f"/groups/{project_id}/accessList", json=body)

    def remove_access(self, project_id: str, ip: str) -> bool:
        return self._req("DELETE", f"/groups/{project_id}/accessList/{quote(ip, safe='')}", ok404=True) is not None


def runner_ip(session: Any = None) -> str:
    session = session or requests.Session()
    for url in IP_SERVICES:
        try:
            resp = session.get(url, timeout=10)
        except requests.RequestException:
            continue
        ip = resp.text.strip()
        if resp.status_code == 200 and ip.count(".") == 3:
            return ip
    raise AtlasAdminError("could not find this runner's public IP")


def connection_uri(cluster: dict[str, Any], username: str, password: str) -> str:
    srv = (cluster.get("connectionStrings") or {}).get("standardSrv")
    if not srv or not srv.startswith("mongodb+srv://"):
        raise AtlasAdminError("cluster has no standardSrv connection string")
    host = srv[len("mongodb+srv://"):].rstrip("/")
    return (f"mongodb+srv://{quote_plus(username)}:{quote_plus(password)}@{host}/"
            f"?retryWrites=true&w=majority&appName=kb-live-smoke")


def grant(admin: AtlasAdmin, *, project_id: str | None, cluster_name: str | None, db_name: str,
          ttl_hours: float, ip: str, now: datetime | None = None, emit: Callable[[str], None] = print,
          in_actions: bool = False, save: Callable[[dict[str, Any]], None] = lambda s: None,
          ) -> tuple[dict[str, Any], dict[str, str]]:
    """Create the temporary user and access entry. Returns (state, env vars to export).

    ``save`` is called after each change so cleanup still works if a later step fails."""
    now = now or datetime.now(timezone.utc)
    expires = now + timedelta(hours=ttl_hours)
    project_id, cluster = admin.resolve(project_id, cluster_name)
    name = cluster["name"]
    username = f"kb-smoke-{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(24)
    if in_actions:
        emit(f"::add-mask::{password}")
    state: dict[str, Any] = {"project_id": project_id, "cluster": name, "username": username,
                             "ip": ip, "ip_preexisting": True, "expires": expires.isoformat()}
    admin.create_db_user(project_id, name, username, password, db_name, expires)
    save(state)
    emit(f"Created database user {username} on {name}, expires {expires.isoformat()}")
    if admin.has_access_entry(project_id, ip):
        emit(f"Access list already has {ip}; leaving it as it is")
    else:
        state["ip_preexisting"] = False
        save(state)
        admin.add_access(project_id, ip, expires, comment="live-smoke GitHub workflow")
        emit(f"Added {ip} to the access list, expires {expires.isoformat()}")
    uri = connection_uri(cluster, username, password)
    if in_actions:
        emit(f"::add-mask::{uri}")
    env = {"MONGODB_URI": uri, "ATLAS_PROJECT_ID": project_id, "ATLAS_CLUSTER_NAME": name,
           "ATLAS_MONGODB_VERSION": str(cluster.get("mongoDBVersion", ""))}
    return state, env


def revoke(admin: AtlasAdmin, state: dict[str, Any], emit: Callable[[str], None] = print) -> list[str]:
    """Delete what :func:`grant` created. Returns a list of problems (empty when clean)."""
    problems = []
    try:
        gone = admin.delete_db_user(state["project_id"], state["username"])
        emit(f"Deleted database user {state['username']}" if gone else f"User {state['username']} was already gone")
    except AtlasAdminError as exc:
        problems.append(str(exc))
    if not state.get("ip_preexisting"):
        try:
            gone = admin.remove_access(state["project_id"], state["ip"])
            emit(f"Removed {state['ip']} from the access list" if gone else f"{state['ip']} was already gone")
        except AtlasAdminError as exc:
            problems.append(str(exc))
    return problems


def _write_env(path: str, env: dict[str, str]) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        for key, value in env.items():
            fh.write(f"{key}={value}\n")


def main(argv: list[str] | None = None, environ: dict[str, str] | None = None,
         admin_factory: Callable[[str, str], AtlasAdmin] = AtlasAdmin, ip_finder: Callable[[], str] = runner_ip) -> int:
    environ = dict(os.environ if environ is None else environ)
    parser = argparse.ArgumentParser(prog="python -m kbase.atlas_admin")
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("grant", help="create a temporary database user and access entry")
    g.add_argument("--project-id", default=environ.get("ATLAS_PROJECT_ID") or None)
    g.add_argument("--cluster", default=environ.get("ATLAS_CLUSTER_NAME") or None)
    g.add_argument("--db", default=environ.get("DB_NAME", "kbase"))
    g.add_argument("--ttl-hours", type=float, default=2.0)
    g.add_argument("--ip", default=None, help="IP to allow; default is this machine's public IP")
    g.add_argument("--state", default=STATE_FILE)
    g.add_argument("--github-env", default=None, help="file to append MONGODB_URI and friends to")
    r = sub.add_parser("revoke", help="delete what grant created")
    r.add_argument("--state", default=STATE_FILE)
    args = parser.parse_args(argv)

    try:
        admin = admin_factory(environ.get("MDB_CLIENT", ""), environ.get("MDB_SECRET", ""))
        if args.command == "grant":
            if not 0 < args.ttl_hours <= 24:
                raise AtlasAdminError("--ttl-hours must be between 0 and 24")
            def save(state: dict[str, Any]) -> None:
                with open(args.state, "w", encoding="utf-8") as fh:
                    json.dump(state, fh)

            state, env = grant(admin, project_id=args.project_id, cluster_name=args.cluster, db_name=args.db,
                               ttl_hours=args.ttl_hours, ip=args.ip or ip_finder(),
                               in_actions=environ.get("GITHUB_ACTIONS") == "true", save=save)
            if args.github_env:
                _write_env(args.github_env, env)
            print(f"Project {env['ATLAS_PROJECT_ID']}, cluster {env['ATLAS_CLUSTER_NAME']}, "
                  f"MongoDB {env['ATLAS_MONGODB_VERSION'] or 'unknown'}")
            return 0
        if not os.path.exists(args.state):
            print("No access state file; nothing to revoke")
            return 0
        with open(args.state, encoding="utf-8") as fh:
            state = json.load(fh)
        problems = revoke(admin, state)
        for p in problems:
            print(f"::warning::cleanup problem: {p}")
        if not problems:
            os.remove(args.state)
        return 1 if problems else 0
    except AtlasAdminError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
