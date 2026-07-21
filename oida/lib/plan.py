#!/usr/bin/env python3
"""OIDA for Claude — deterministic planner (no LLM, no per-session network I/O).

From all discovered Claude Code sessions, keep those that are:
  - NEW or CHANGED   (cheap session_id:mtime:size signature not in the ledger),
  - QUIESCENT        (untouched for >= 30 min — not still being written),
  - ALLOWLISTED      (repo owner/repo is in the org's designated set), and
  - not in the skip queue.
Writes plan.json = the session descriptors push.py will build + send. The allowlist
is fetched from GET /ingest/sessions/allowlist and cached ~1h; on a network miss we
fall back to the last cache (stale-but-safe — the server re-enforces P6 anyway).
"""
import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
import extract  # noqa: E402
import sources  # noqa: E402

QUIESCENT_SEC = 30 * 60
ALLOWLIST_TTL_SEC = 3600


def load_config():
    path = os.environ.get("OIDA_CONFIG") or os.path.join(os.path.expanduser("~"), ".oida", "config.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _fetch_allowlist(config):
    url = config["apiUrl"].rstrip("/") + "/ingest/sessions/allowlist"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + config["deviceKey"]})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return list(json.loads(r.read().decode("utf-8")).get("repos", []))
    except Exception:
        return None


def get_allowlist(config, work):
    cache = os.path.join(work, "allowlist.json")
    try:
        if time.time() - os.path.getmtime(cache) < ALLOWLIST_TTL_SEC:
            with open(cache, encoding="utf-8") as f:
                return set(json.load(f).get("repos", []))
    except OSError:
        pass
    repos = _fetch_allowlist(config)
    if repos is not None:
        try:
            with open(cache, "w", encoding="utf-8") as f:
                json.dump({"repos": sorted(repos), "at": time.time()}, f)
        except OSError:
            pass
        return set(repos)
    try:  # network miss -> last cache (stale is safer than dropping; server re-checks scope)
        with open(cache, encoding="utf-8") as f:
            return set(json.load(f).get("repos", []))
    except OSError:
        return set()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)
    os.makedirs(args.work, exist_ok=True)

    config = load_config()
    allow = get_allowlist(config, args.work)
    ledger = extract.load_ledger(args.work)
    skip = extract.load_skip(args.work)
    now = time.time()

    plan = []
    for path in extract.session_files(sources.claude_code_roots()):
        try:
            mtime = os.path.getmtime(path)
            size = os.path.getsize(path)
        except OSError:
            continue
        if now - mtime < QUIESCENT_SEC:
            continue  # still active
        desc = extract.describe_session(path)
        if not desc or desc["session_id"] in skip:
            continue
        owner_repo = (desc.get("repo") or {}).get("owner_repo")
        if not owner_repo or owner_repo not in allow:
            continue  # repo-less or not designated (client gate; server re-enforces P6)
        desc["ledger_key"] = extract.content_key(desc["session_id"], f"{int(mtime)}:{size}")
        if desc["ledger_key"] in ledger:
            continue  # unchanged since last successful push
        # A prior push of this session under a different signature -> this is an edit.
        prefix = desc["session_id"] + ":"
        desc["update"] = any(k.startswith(prefix) for k in ledger)
        plan.append(desc)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(plan, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
