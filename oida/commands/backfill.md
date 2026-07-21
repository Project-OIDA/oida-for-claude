---
description: Backfill past Claude Code sessions to OIDA (dry-run first, then confirm)
argument-hint: "[--push]"
---

Backfill historical sessions to OIDA. **Dry-run gated: never push without explicit confirmation.**

1. **Dry-run first (always).** Build the plan and show what WOULD be sent — do not push yet:
   `OIDA_CONFIG="$HOME/.oida/config.json" python3 "${CLAUDE_PLUGIN_ROOT}/lib/plan.py" --out "$HOME/.oida/work/plan.json" --work "$HOME/.oida/work"`
   Then read `~/.oida/work/plan.json` and list each session (`session_id`, `repo.owner_repo`, `ended_at`, `update`). Report the count.
2. **Confirm.** Proceed to push ONLY if the user passed `--push` in `$ARGUMENTS` or explicitly says to. Otherwise stop here.
3. **Push.**
   `OIDA_CAPTURE=1 OIDA_CONFIG="$HOME/.oida/config.json" python3 "${CLAUDE_PLUGIN_ROOT}/lib/push.py" --plan "$HOME/.oida/work/plan.json" --work "$HOME/.oida/work"`
   Report how many were pushed. The server is idempotent, so a re-run is safe.

Only allowlisted repos appear in the plan; the planner already drops repo-less and undesignated sessions.
