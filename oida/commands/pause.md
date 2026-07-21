---
description: Pause or resume OIDA session capture on this machine
argument-hint: "[on|off]"
---

Toggle OIDA session capture on this machine using the Bash tool.

- Interpret `$ARGUMENTS`: `off` / `resume` → **resume**; anything else (or empty) → **pause**.
- **Pause:** `mkdir -p "$HOME/.oida" && touch "$HOME/.oida/PAUSED"` — confirm capture is stopped until resumed. Nothing is captured or sent while paused.
- **Resume:** `rm -f "$HOME/.oida/PAUSED"` — confirm capture will run again at the next session end.

This is a local, machine-level switch. (Org-wide pause / off-hours are enforced server-side in a later phase.)
