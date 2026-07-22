# What OIDA for Claude captures — and your consent

Plain-language summary for the developer installing this client. Your organization's formal
privacy notice (the *informativa*) is the authoritative document — ask your workspace
admin for it. This page explains what happens on **your** machine and the choices you control.

## Consent: mint your own key

When you set up the client you paste a **device key** you minted in
OIDA → Settings → "OIDA for Claude". At mint time you tick a consent statement (version
`2026-07-22`) and that acknowledgement is recorded against **your** account.

> **Mint your *own* key.** The recorded consent belongs to whoever mints the key. So that the
> record reflects *your* awareness, **mint the key yourself** and paste it here — don't reuse
> a key someone else minted for you. If you can't reach the mint screen, ask your admin for
> access rather than borrowing a key.

## What is captured (only for repos your workspace designates)

- **Every user/assistant turn**, redacted on your machine before anything is sent.
- A **tool-call log**: the tool name (Edit, Bash, Read, …) + a redacted, truncated input.
- **Metrics**: session start/end, active time, git line stats (+/−), commit messages, branch.

## What is **not** captured

- **Tool outputs / results** — command output, file contents read, API responses: dropped on
  your machine, never sent (~90% of a transcript, and the biggest secret surface).
- Anything in a repo **not on your workspace's allowlist** — dropped locally *and* re-checked
  server-side.
- Anything **outside working hours** (default: no capture 20:00–08:00 or weekends;
  timezone/policy set by your workspace).
- Anything while **paused**.

## Redaction is best-effort — don't paste live secrets

Turn text and tool-call inputs are passed through a local pattern-based redactor (API keys,
tokens, connection strings) before leaving your machine. **It is not exhaustive.** Never paste
live secrets into prompts — use a secret manager. If a secret does slip through, use **erase**
(below) and tell your admin.

## Your controls

| You want to… | Do this | Effect |
|---|---|---|
| Pause capture | Workspace "Capture policy" toggle, or `touch ~/.oida/PAUSED` on your machine | Stops immediately |
| Rotate your key | Settings → "Rotate" | Old key stops working; a new one is issued |
| Withdraw consent | Settings → "Withdraw my consent & revoke my keys" | All your keys revoked, future capture stops. **Already-stored knowledge is *not* deleted by this** — use erase |
| Erase a session's data | Per-session erase / ask your admin | Deletes that session's stored transcript + derived knowledge |

Old data also ages out automatically on your plan's retention window (90 / 180 / 365 days).

## How it stays private

- **Deterministic client**: no LLM and no API keys run on your machine — it only captures,
  redacts, and sends. All extraction happens server-side.
- **Allowlist, default deny**: only designated repos are ever captured; a misconfigured client
  cannot bypass this (the server re-checks).
- **Show-once keys**: only a one-way hash is stored server-side; revoke or rotate anytime.
- **No individual evaluation**: OIDA has no per-person analytics or ranking — your git email is
  used only for provenance and to let you erase your own data.

See the repo `README.md` for install/ops and `../project-oida-be-sessions/docs/subprocessors.md`
(via your admin) for who processes the data.
