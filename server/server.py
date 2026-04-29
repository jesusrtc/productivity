#!/usr/bin/env python3
"""
repo-server: minimal git-over-HTTP push receiver.

Stores each remote repo as a regular (non-bare) git repo under $REPO_ROOT/<name>.
A push from the `repo` CLI arrives as a git bundle of new commits only; the
server fetches from the bundle and fast-forwards the target branch, then resets
the working tree so the on-disk folder always reflects the latest commit.

Endpoints
  GET  /health
  GET  /repos/<name>/head?branch=<branch>          -> {"sha": "<sha>"|null}
  POST /repos/<name>/push?branch=<b>&base=<sha>    body: git bundle bytes
                                                   -> {"sha": "<new_sha>"}

Configuration (env)
  HOST       bind host       default 127.0.0.1
  PORT       bind port       default 4000
  REPO_ROOT  storage root    default ./repos
  MAX_BUNDLE max upload size default 2 GiB
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "4000"))
REPO_ROOT = Path(os.environ.get("REPO_ROOT", "./repos")).resolve()
MAX_BUNDLE = int(os.environ.get("MAX_BUNDLE", str(2 * 1024 * 1024 * 1024)))

REPO_ROOT.mkdir(parents=True, exist_ok=True)

ENDPOINTS = [
    {
        "method": "GET",
        "path": "/",
        "description": "this index (HTML for browsers, JSON otherwise)",
    },
    {
        "method": "GET",
        "path": "/health",
        "description": "liveness probe",
        "returns": {"ok": True},
    },
    {
        "method": "GET",
        "path": "/repos",
        "description": "list repos known to the server",
        "returns": {"repos": [{"name": "demo", "branches": ["main"]}]},
    },
    {
        "method": "GET",
        "path": "/repos/<name>/head",
        "query": {"branch": "branch name (default: main)"},
        "description": "current sha of <branch> on the server",
        "returns": {"repo": "<name>", "branch": "<branch>", "sha": "<sha-or-null>"},
    },
    {
        "method": "POST",
        "path": "/repos/<name>/push",
        "query": {
            "branch": "branch to update (default: main)",
            "base": "expected current sha on server (empty for initial push)",
        },
        "body": "git bundle bytes (Content-Type: application/x-git-bundle)",
        "description": "fast-forward <branch> by applying the bundle; "
                       "stored at $REPO_ROOT/<name>",
        "returns": {"repo": "<name>", "branch": "<branch>", "sha": "<new-sha>"},
    },
]


_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_SHA_RE = re.compile(r"^[0-9a-f]{4,64}$")

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(name: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(name, threading.Lock())


def _safe_name(name: str) -> str:
    if not _NAME_RE.match(name or "") or ".." in name:
        raise ValueError(f"invalid repo name: {name!r}")
    return name


def _safe_branch(branch: str) -> str:
    if not _BRANCH_RE.match(branch or "") or ".." in branch or branch.endswith((".lock", "/", ".")):
        raise ValueError(f"invalid branch name: {branch!r}")
    return branch


def _safe_sha(sha: str | None) -> str | None:
    if sha is None or sha == "":
        return None
    if not _SHA_RE.match(sha):
        raise ValueError(f"invalid sha: {sha!r}")
    return sha


def _repo_path(name: str) -> Path:
    return REPO_ROOT / _safe_name(name)


def _git(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={r.returncode}): "
            f"{r.stderr.decode(errors='replace').strip()}"
        )
    return r


def _list_repos() -> list[dict]:
    out = []
    if not REPO_ROOT.exists():
        return out
    for entry in sorted(REPO_ROOT.iterdir()):
        if not entry.is_dir() or not (entry / ".git").exists():
            continue
        try:
            _safe_name(entry.name)
        except ValueError:
            continue
        r = _git(
            ["for-each-ref", "--format=%(refname:short)", "refs/heads/"],
            cwd=entry, check=False,
        )
        branches = (
            [b for b in r.stdout.decode().splitlines() if b]
            if r.returncode == 0 else []
        )
        out.append({"name": entry.name, "branches": branches})
    return out


def _render_index_html() -> bytes:
    rows = []
    for ep in ENDPOINTS:
        method = ep["method"]
        path = ep["path"]
        desc = ep.get("description", "")
        extra_lines = []
        if "query" in ep:
            for k, v in ep["query"].items():
                extra_lines.append(f"<div class=q>?{k}=<i>{v}</i></div>")
        if "body" in ep:
            extra_lines.append(f"<div class=q>body: {ep['body']}</div>")
        if "returns" in ep:
            extra_lines.append(
                f"<div class=q>returns: <code>{json.dumps(ep['returns'])}</code></div>"
            )
        rows.append(
            f"<tr><td><span class=m m-{method}>{method}</span></td>"
            f"<td><code>{path}</code><div class=d>{desc}</div>"
            f"{''.join(extra_lines)}</td></tr>"
        )
    html = (
        "<!doctype html><meta charset=utf-8>"
        "<title>repo-server</title>"
        "<style>"
        "body{font:14px/1.5 -apple-system,system-ui,sans-serif;max-width:800px;"
        "margin:2em auto;padding:0 1em;color:#222}"
        "h1{font-size:1.4em;margin:0 0 .2em}"
        "p.sub{color:#666;margin:0 0 1.5em}"
        "table{border-collapse:collapse;width:100%}"
        "td{padding:.6em .5em;border-top:1px solid #eee;vertical-align:top}"
        "code{background:#f4f4f4;padding:1px 5px;border-radius:3px}"
        ".m{display:inline-block;font-weight:600;font-size:.78em;"
        "padding:2px 7px;border-radius:3px;color:#fff}"
        ".m-GET{background:#0a7}.m-POST{background:#06c}"
        ".d{color:#555;margin-top:3px}"
        ".q{color:#888;font-size:.9em;margin-top:2px}"
        "a{color:#06c}"
        "</style>"
        "<h1>repo-server</h1>"
        f"<p class=sub>Listening on {HOST}:{PORT} &middot; "
        f"<code>REPO_ROOT={REPO_ROOT}</code> &middot; "
        f"<a href='/repos'>/repos</a> &middot; "
        f"<a href='/health'>/health</a></p>"
        "<table>" + "".join(rows) + "</table>"
    )
    return html.encode()


def _branch_head(repo: Path, branch: str) -> str | None:
    if not (repo / ".git").exists():
        return None
    r = _git(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=repo, check=False)
    if r.returncode != 0:
        return None
    return r.stdout.decode().strip()


def _ensure_repo(repo: Path, branch: str) -> None:
    if (repo / ".git").exists():
        return
    repo.mkdir(parents=True, exist_ok=True)
    _git(["init", "--quiet", "-b", branch], cwd=repo)
    # Allow updating the currently checked-out branch on push.
    _git(["config", "receive.denyCurrentBranch", "updateInstead"], cwd=repo)


def _apply_bundle(repo: Path, branch: str, bundle: Path, expected_base: str | None) -> str:
    _ensure_repo(repo, branch)

    current = _branch_head(repo, branch)
    if (current or "") != (expected_base or ""):
        raise RuntimeError(
            f"server has {branch} at {current!r} but client expected base {expected_base!r}; "
            f"pull or rebase before pushing"
        )

    _git(["bundle", "verify", str(bundle)], cwd=repo)

    tmp_ref = f"refs/repo-incoming/{branch}"
    try:
        _git(
            ["fetch", "--quiet", str(bundle), f"+refs/heads/{branch}:{tmp_ref}"],
            cwd=repo,
        )
        new_sha = _git(["rev-parse", "--verify", tmp_ref], cwd=repo).stdout.decode().strip()

        if current is None:
            _git(["update-ref", f"refs/heads/{branch}", new_sha], cwd=repo)
        else:
            ff = _git(
                ["merge-base", "--is-ancestor", current, new_sha], cwd=repo, check=False
            )
            if ff.returncode != 0:
                raise RuntimeError(
                    f"non-fast-forward: server head {current} is not an ancestor of {new_sha}"
                )
            _git(
                ["update-ref", f"refs/heads/{branch}", new_sha, current], cwd=repo
            )
    finally:
        _git(["update-ref", "-d", tmp_ref], cwd=repo, check=False)

    # Make HEAD track the pushed branch and refresh the working tree.
    head_ref = _git(["symbolic-ref", "--quiet", "HEAD"], cwd=repo, check=False)
    if head_ref.returncode != 0 or head_ref.stdout.decode().strip() != f"refs/heads/{branch}":
        _git(["symbolic-ref", "HEAD", f"refs/heads/{branch}"], cwd=repo)
    _git(["reset", "--hard", "--quiet", branch], cwd=repo)

    return new_sha


class Handler(BaseHTTPRequestHandler):
    server_version = "RepoServer/0.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(
            f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}\n"
        )

    def _send_json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code: int, msg: str) -> None:
        self._send_json(code, {"error": msg})

    def _send_html(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _wants_html(self) -> bool:
        return "text/html" in (self.headers.get("Accept") or "")

    def _route(self):
        u = urlparse(self.path)
        parts = [p for p in u.path.split("/") if p]
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        return parts, q

    def do_GET(self) -> None:
        try:
            parts, q = self._route()
            if parts == []:
                if self._wants_html():
                    self._send_html(200, _render_index_html())
                else:
                    self._send_json(200, {
                        "service": "repo-server",
                        "host": HOST,
                        "port": PORT,
                        "repo_root": str(REPO_ROOT),
                        "endpoints": ENDPOINTS,
                    })
                return
            if parts == ["health"]:
                self._send_json(200, {"ok": True})
                return
            if parts == ["repos"]:
                self._send_json(200, {"repos": _list_repos()})
                return
            if len(parts) == 3 and parts[0] == "repos" and parts[2] == "head":
                name = _safe_name(parts[1])
                branch = _safe_branch(q.get("branch", "main"))
                with _lock_for(name):
                    sha = _branch_head(_repo_path(name), branch)
                self._send_json(200, {"repo": name, "branch": branch, "sha": sha})
                return
            self._err(404, f"unknown path: {self.path}")
        except ValueError as e:
            self._err(400, str(e))
        except Exception as e:
            self._err(500, f"server error: {e}")

    def do_POST(self) -> None:
        bundle_path: Path | None = None
        try:
            parts, q = self._route()
            if not (len(parts) == 3 and parts[0] == "repos" and parts[2] == "push"):
                self._err(404, f"unknown path: {self.path}")
                return

            name = _safe_name(parts[1])
            branch = _safe_branch(q.get("branch", "main"))
            base = _safe_sha(q.get("base"))

            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                self._err(400, "empty body")
                return
            if length > MAX_BUNDLE:
                self._err(413, f"bundle too large (>{MAX_BUNDLE} bytes)")
                return

            with tempfile.NamedTemporaryFile(suffix=".bundle", delete=False) as f:
                bundle_path = Path(f.name)
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(1 << 16, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
                if remaining > 0:
                    self._err(400, "client disconnected mid-upload")
                    return

            with _lock_for(name):
                new_sha = _apply_bundle(_repo_path(name), branch, bundle_path, base)
            self._send_json(200, {"repo": name, "branch": branch, "sha": new_sha})

        except ValueError as e:
            self._err(400, str(e))
        except RuntimeError as e:
            self._err(409, str(e))
        except Exception as e:
            self._err(500, f"server error: {e}")
        finally:
            if bundle_path is not None:
                try:
                    bundle_path.unlink()
                except OSError:
                    pass


def main() -> int:
    print(
        f"repo-server listening on http://{HOST}:{PORT} (REPO_ROOT={REPO_ROOT})",
        file=sys.stderr,
    )
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
