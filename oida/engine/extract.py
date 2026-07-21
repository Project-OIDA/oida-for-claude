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


def _git(cwd, args, timeout=8):
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


_REMOTE_RE = re.compile(r"(?:git@[^:]+:|ssh://[^/]+/|https?://[^/]+/)([^/\s]+/[^/\s]+?)(?:\.git)?/?$")


def owner_repo_from_remote(remote):
    if not remote:
        return None
    m = _REMOTE_RE.search(remote.strip())
    return m.group(1) if m else None


def git_info(cwd):
    """{remote, owner_repo, branch} for the session's working dir, or {}."""
    if not cwd or not os.path.isdir(cwd):
        return {}
    remote = _git(cwd, ["config", "--get", "remote.origin.url"])
    branch = _git(cwd, ["rev-parse", "--abbrev-ref", "HEAD"])
    info = {}
    if remote:
        info["remote"] = remote
    owner_repo = owner_repo_from_remote(remote)
    if owner_repo:
        info["owner_repo"] = owner_repo
    if branch and branch != "HEAD":
        info["branch"] = branch
    return info


def git_email(cwd):
    return _git(cwd or ".", ["config", "--get", "user.email"]) or _git(".", ["config", "--get", "user.email"])


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
    assert content_key("s1", "abc") == "s1:abc"
    print("OK self-test: extract (remote parsing / content key)")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    else:
        print(json.dumps({"cli_roots": sources.claude_code_roots()}, indent=2))
