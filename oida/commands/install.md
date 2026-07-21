---
description: Set up OIDA for Claude on this machine (saves your device key + API URL)
argument-hint: "[device-key]"
---

Set up the OIDA session client on this machine. Use the Bash tool and **never print the full device key back to the transcript** after reading it.

1. **Device key** — use `$ARGUMENTS` if the user passed one; otherwise ask them to paste the key minted in OIDA → Settings → "OIDA for Claude" (shown once, looks like `oida_sess_…`).
2. **API URL** — default to the OIDA production API URL unless the user gives one. <!-- operator: set the real default host before publishing this plugin -->
3. Create `~/.oida/` (mode 700) and write `~/.oida/config.json` (mode 600):
   `{"apiUrl": "<api-url>", "deviceKey": "<device-key>"}`
4. Verify: `curl -fsS -H "Authorization: Bearer <key>" <api-url>/ingest/sessions/allowlist` — report the designated repos, or a clear error if the key/URL is wrong (do not proceed on 401).
5. Confirm to the user: capture now runs automatically at the end of each session (and catches up at session start). `/oida:status` shows state, `/oida:pause` stops it, `/oida:backfill` sends past sessions.

Only sessions in repos designated in the workspace are ever sent; everything else is dropped locally and again server-side.
