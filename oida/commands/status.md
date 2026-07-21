---
description: Show OIDA for Claude status — config, pause state, last run, pending sessions
---

Report the OIDA session-client status. Use the Bash tool; never print the device key.

- **Configured?** does `~/.oida/config.json` exist? Show `apiUrl` only (never `deviceKey`).
- **Paused?** does `~/.oida/PAUSED` exist? (toggle with `/oida:pause`)
- **Last capture run:** mtime of `~/.oida/work/.last-run`; show the tail of `~/.oida/work/capture.log`.
- **Pushed so far:** number of entries in `~/.oida/work/ledger.json`.
- **Allowlisted repos (cached):** the `repos` in `~/.oida/work/allowlist.json`.
- **Pending (dry-run, do NOT push):**
  `OIDA_DRY_RUN=1 OIDA_CONFIG="$HOME/.oida/config.json" python3 "${CLAUDE_PLUGIN_ROOT}/lib/plan.py" --out "$HOME/.oida/work/plan.json" --work "$HOME/.oida/work"`
  then report how many sessions would be pushed.

Summarize concisely in a few lines.
