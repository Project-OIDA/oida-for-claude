#!/usr/bin/env python3
"""OIDA for Claude — session enumeration + ledger + skip queue.

Condensed from control8's `backfill_extract.py` with the MCP/PM coupling removed:
this only discovers Claude Code session files, resolves each session's git repo
(remote -> owner/repo, branch) and time window, and maintains an idempotency
ledger (session_id + content-hash) and a skip queue (sessions that fail to parse,
so a poison file is not retried forever). No LLM, no server calls here.

Porting note: the full backfill_extract.py also classifies Cowork sessions and
splits multi-deliverable work — out of client v1 (repo-scoped CLI only).
"""
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources  # noqa: E402
from redact import redact  # noqa: E402


def _git(cwd, args, timeout=8):
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


_REMOTE_RE = re.compile(
    r"(?:git@(?P<h1>[^:]+):|ssh://(?:[^@/]+@)?(?P<h2>[^/:]+)(?::\d+)?/|https?://(?:[^@/]+@)?(?P<h3>[^/:]+)(?::\d+)?/)"
    r"(?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?/?$")


def _remote_match(remote):
    return _REMOTE_RE.search(remote.strip()) if remote else None


def owner_repo_from_remote(remote):
    m = _remote_match(remote)
    return m.group("repo") if m else None


def host_from_remote(remote):
    """The remote's host, lowercased — `owner/repo` alone is not an identity.
    Two different hosts can serve the same owner/repo, so the allowlist check
    would otherwise fail OPEN for a same-named repo on another host."""
    m = _remote_match(remote)
    if not m:
        return None
    host = m.group("h1") or m.group("h2") or m.group("h3")
    return host.lower() if host else None


def git_info(cwd):
    """{remote, host, owner_repo, branch} for the session's working dir, or {}.

    `remote` is REDACTED: credentialed remotes are common
    (https://oauth2:ghp_…@github.com/acme/app.git) and this value goes into the
    envelope verbatim, so the token would ship with it."""
    if not cwd or not os.path.isdir(cwd):
        return {}
    remote = _git(cwd, ["config", "--get", "remote.origin.url"])
    branch = _git(cwd, ["rev-parse", "--abbrev-ref", "HEAD"])
    info = {}
    if remote:
        info["remote"] = redact(remote)
    host = host_from_remote(remote)
    if host:
        info["host"] = host
    owner_repo = owner_repo_from_remote(remote)
    if owner_repo:
        info["owner_repo"] = owner_repo
    if branch and branch != "HEAD":
        info["branch"] = branch
    return info


# Hosts whose `owner/repo` may be matched against a host-less allowlist entry.
# The designated scopes are GitHub repos, so github.com is the only default;
# GitHub Enterprise deployments add theirs via config.json `gitHosts`.
DEFAULT_GIT_HOSTS = ("github.com",)


def repo_allowed(repo_info, allow, hosts=DEFAULT_GIT_HOSTS):
    """Client-side allowlist gate (the server re-enforces P6 regardless).

    `owner/repo` alone is not a repo identity: a session in gitlab.com/acme/app
    or a personal fork on another host would match a workspace that designated
    acme/app on GitHub — a default-deny gate failing OPEN. So an entry matches
    only if it names the host explicitly (`host/owner/repo`), or if it is
    host-less and the session's host is one we accept for host-less entries."""
    owner_repo = (repo_info or {}).get("owner_repo")
    if not owner_repo:
        return False
    host = (repo_info or {}).get("host")
    allow = {str(a).strip().lower().lstrip("/") for a in (allow or set())}
    if host and f"{host}/{owner_repo}".lower() in allow:
        return True
    if owner_repo.lower() not in allow:
        return False
    # Host-less entry: accept only from a host we treat as the designated one.
    # A session with no resolvable host (no remote) never passes.
    return bool(host) and host in {h.lower() for h in hosts}


def git_email(cwd):
    """The session repo's configured author email.

    No fallback to the process CWD: push.py runs detached with an inherited
    working directory, so `.` is often an unrelated repo — that email would be
    stored as the envelope's author AND passed as git_stats' --author filter,
    silently attributing (or zeroing) another repo's work."""
    return _git(cwd, ["config", "--get", "user.email"]) if cwd else ""


def _head_tail(path):
    first = last = None
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                if first is None:
                    first = obj
                last = obj
    except OSError:
        return None, None
    return first, last


def session_files(cli_roots):
    for root in cli_roots:
        for p in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
            if os.sep + "subagents" + os.sep in p or os.sep + "wf_" in p:
                continue
            yield p


def describe_session(path):
    """Metadata for one session file, or None if it has no parseable content."""
    first, last = _head_tail(path)
    if not first:
        return None
    cwd = first.get("cwd") if isinstance(first.get("cwd"), str) else None
    return {
        "session_id": os.path.splitext(os.path.basename(path))[0],
        "path": path,
        "cwd": cwd,
        "repo": git_info(cwd),
        "started_at": first.get("timestamp") if isinstance(first.get("timestamp"), str) else None,
        "ended_at": last.get("timestamp") if isinstance(last.get("timestamp"), str) else None,
        "mtime": os.path.getmtime(path),
    }


# -- idempotency ledger + skip queue (atomic JSON files under the work dir) -------
def _load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(p, data):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, p)


def content_key(session_id, content_hash):
    return f"{session_id}:{content_hash}"


def load_ledger(work):
    return set(_load_json(os.path.join(work, "ledger.json"), []))


def record_ledger(work, key):
    seen = load_ledger(work)
    seen.add(key)
    _save_json(os.path.join(work, "ledger.json"), sorted(seen))


def load_skip(work):
    return set(_load_json(os.path.join(work, "skip.json"), []))


def record_skip(work, session_id):
    skip = load_skip(work)
    skip.add(session_id)
    _save_json(os.path.join(work, "skip.json"), sorted(skip))


def _self_test():
    assert owner_repo_from_remote("git@github.com:kakashi-ventures/oida.git") == "kakashi-ventures/oida"
    assert owner_repo_from_remote("https://github.com/kakashi-ventures/oida") == "kakashi-ventures/oida"
    assert owner_repo_from_remote("https://github.com/kakashi-ventures/oida.git") == "kakashi-ventures/oida"
    assert owner_repo_from_remote("") is None and owner_repo_from_remote(None) is None
    # The host is part of the repo identity (allowlist must not fail open).
    assert host_from_remote("git@github.com:kva/oida.git") == "github.com"
    assert host_from_remote("https://GitLab.com/kva/oida.git") == "gitlab.com"
    assert host_from_remote("ssh://git@git.internal:2222/kva/oida.git") == "git.internal"
    assert host_from_remote("https://oauth2:ghp_x@github.com/kva/oida.git") == "github.com"
    assert owner_repo_from_remote("https://oauth2:ghp_x@github.com/kva/oida.git") == "kva/oida"
    assert host_from_remote("not-a-remote") is None
    # Host-blind allowlist matching must not fail open.
    allow = {"kva/oida", "github.com/kva/other"}
    assert repo_allowed({"owner_repo": "kva/oida", "host": "github.com"}, allow)
    assert not repo_allowed({"owner_repo": "kva/oida", "host": "gitlab.com"}, allow)
    assert not repo_allowed({"owner_repo": "kva/oida"}, allow)  # no host → no match
    assert repo_allowed({"owner_repo": "kva/oida", "host": "git.acme.dev"}, allow, hosts=("git.acme.dev",))
    assert repo_allowed({"owner_repo": "kva/other", "host": "github.com"}, allow)
    assert not repo_allowed({"owner_repo": "kva/other", "host": "gitlab.com"}, allow)
    assert not repo_allowed({}, allow) and not repo_allowed(None, allow)
    assert not repo_allowed({"owner_repo": "kva/oida", "host": "github.com"}, set())
    assert content_key("s1", "abc") == "s1:abc"
    print("OK self-test: extract (remote parsing / host / allowlist / content key)")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    else:
        print(json.dumps({"cli_roots": sources.claude_code_roots()}, indent=2))
