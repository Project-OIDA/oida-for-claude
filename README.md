# OIDA for Claude

Standalone clients that capture your AI-coding sessions and push them to your
[OIDA](https://github.com/Project-OIDA) workspace, so the *reasoning* behind
your work — not just the commits and PRs — becomes part of your organization's
epistemic memory.

**This repo is scaffolded (Phase B2).** The plugin structure, manifests, hooks,
and the deterministic capture engine are in place; a few pieces are marked as
porting pointers (see below) and the production API host must be set before
publishing.

## What it is

A Claude Code plugin (`oida/`) that, at the end of every session:

1. **captures** the transcript from `~/.claude/projects`,
2. **redacts** it locally (secrets, tokens, connection strings — see `engine/redact.py`),
3. keeps only sessions whose git repo is on your workspace's **allowlist**, and
4. **pushes** a compact envelope to `POST /ingest/sessions`.

It is **fully deterministic**: no API keys and no LLM run on your machine. All
extraction happens server-side in OIDA's existing pipeline, which verifies quotes
against the real transcript text. The client only captures, redacts, and sends.

### Deliberate reduction

The envelope carries every user/assistant turn (redacted) + a tool-call log (tool
name + a redacted, truncated input) + git/time metrics. **`tool_result` bodies are
dropped** — ~90% of transcript bytes and the biggest secret-leak surface.

## Install

```
/plugin marketplace add Project-OIDA/oida-for-claude
/plugin install oida
/oida:install        # paste the device key you minted in OIDA → Settings → "OIDA for Claude"
```

Then capture is automatic. `/oida:status` shows state, `/oida:pause` stops it,
`/oida:backfill` sends past sessions (dry-run gated).

Config lives in `~/.oida/config.json` (`{apiUrl, deviceKey}`, mode 600).

## Layout

```
.claude-plugin/marketplace.json   marketplace entry
oida/
  .claude-plugin/plugin.json      plugin manifest
  hooks/hooks.json                SessionEnd + SessionStart(startup|resume), async
  hooks/capture.sh                guards (recursion/pause/throttle/quiescence) → plan → push (no LLM)
  lib/plan.py                     deterministic planner: new · quiescent · allowlisted · ledger-deduped
  lib/push.py                     build SessionEnvelope · gzip POST · backoff · ledger on 2xx
  engine/sources.py               cross-OS/WSL discovery of Claude data roots
  engine/transcript.py            JSONL → {turns, tool_calls}; drops tool_result; redacts every string
  engine/redact.py                secret/PII redaction patterns (+ oida_sess_ device tokens)
  engine/metrics.py               git line stats, active-time, commit messages
  engine/extract.py               session enumeration, git-repo resolution, ledger + skip queue
  commands/                       /oida:install · status · backfill · pause
```

## Privacy & security posture

**Before you install, read [`docs/CONSENT.md`](docs/CONSENT.md)** — what is (and isn't)
captured, your controls (pause / rotate / withdraw / erase), and why you should **mint your
own device key**. Your organization's formal privacy notice is the authoritative document.

- **Redaction is local and best-effort.** The server treats the transcript as
  already-clean, so keep `engine/redact.py` current with new credential shapes.
- **Allowlist, default deny.** Only repos your workspace designates are captured;
  the server re-enforces this (a lying client cannot bypass it).
- **Show-once device keys.** Only a hash is stored server-side; revoke anytime in
  Settings.
- **At-least-once, idempotent.** The server dedupes on `session_id` + content
  hash, so retries never double-ingest.

## Tests

The pure engine modules self-test without network or a real transcript:

```
for m in sources redact transcript metrics extract; do python3 oida/engine/$m.py --self-test; done
```

## Porting pointers (remaining before GA)

- `commands/install.md` — set the real default `apiUrl` host.
- `engine/extract.py` — Cowork (Claude Desktop) sessions are discovered but out of
  client v1 (repo-scoped CLI only); Codex CLI support is Phase C.
- Consent screen at key mint + per-plan caps + server-authoritative pause/off-hours shipped
  in Phase D (see [`docs/CONSENT.md`](docs/CONSENT.md)).
