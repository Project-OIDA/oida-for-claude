#!/usr/bin/env bash
# OIDA for Claude — deterministic, out-of-band session capture.
#
# Registered (plugin manifest) on SessionEnd (timely) + SessionStart(startup|resume)
# (catch-up). Unlike control8's auto-eod, there is NO LLM step here: the client only
# captures, redacts and pushes; all extraction happens server-side in OIDA. Flow:
#   1. cheap guards (recursion / pause / throttle / config present / "anything new?")
#   2. plan.py  — enumerate new · quiescent · allowlisted sessions           [~1s, no LLM]
#   3. plan empty -> done (the common case does no network I/O)
#   4. push.py  — build the SessionEnvelope per session, gzip POST, record in the ledger
#
# Prints NOTHING to stdout (SessionStart adds stdout to the live context). Always exits 0
# (fire-and-forget). The push child sets OIDA_CAPTURE=1 so any nested hook bails.

set -u

OIDA_HOME="${HOME}/.oida"
CONFIG="${OIDA_HOME}/config.json"
WORK="${OIDA_HOME}/work"
MARKER="${WORK}/.last-run"
LOG="${WORK}/capture.log"
PLAN="${WORK}/plan.json"
PROJECTS_ROOT="${HOME}/.claude/projects"
MIN_INTERVAL_SEC="${OIDA_MIN_INTERVAL_SEC:-3600}"

# ── guards ────────────────────────────────────────────────────────────────────
[ -n "${OIDA_CAPTURE:-}" ] && exit 0                # recursion guard (we are the push child)
[ -f "${OIDA_HOME}/PAUSED" ] && exit 0              # local opt-out (/oida:pause)
[ -f "${CONFIG}" ] || exit 0                        # not installed yet (/oida:install)
command -v python3 >/dev/null 2>&1 || exit 0

mkdir -p "${WORK}" 2>/dev/null || exit 0

# Min-interval throttle.
if [ -f "${MARKER}" ]; then
  last="$(stat -c %Y "${MARKER}" 2>/dev/null || stat -f %m "${MARKER}" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  [ $((now - last)) -lt "${MIN_INTERVAL_SEC}" ] && exit 0

  # Cheap "anything new?" probe — a transcript touched since the last run.
  newer="$(find "${PROJECTS_ROOT}" -type f -name '*.jsonl' -newer "${MARKER}" \
            -not -path '*/subagents/*' -not -path '*/wf_*' -print -quit 2>/dev/null)"
  [ -z "${newer}" ] && exit 0
fi
touch "${MARKER}" 2>/dev/null                       # claim this run before doing work

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"

# ── 2. deterministic plan (no LLM, no network except the cached allowlist) ──────
if ! OIDA_CONFIG="${CONFIG}" python3 "${PLUGIN_DIR}/lib/plan.py" --out "${PLAN}" --work "${WORK}" >>"${LOG}" 2>&1; then
  echo "$(date): plan failed" >>"${LOG}"; exit 0
fi
count="$(python3 -c "import json,sys;print(len(json.load(open('${PLAN}'))))" 2>/dev/null || echo 0)"
echo "$(date): plan -> ${count} session(s) to push" >>"${LOG}"
[ "${count}" = "0" ] && exit 0

# ── 3. dry-run: log the plan, do not push ───────────────────────────────────────
if [ -n "${OIDA_DRY_RUN:-}" ]; then
  echo "$(date): DRY-RUN — would push:" >>"${LOG}"; cat "${PLAN}" >>"${LOG}"; exit 0
fi

# ── 4. push (deterministic), fully detached ─────────────────────────────────────
if command -v setsid >/dev/null 2>&1; then
  OIDA_CAPTURE=1 setsid python3 "${PLUGIN_DIR}/lib/push.py" --plan "${PLAN}" --work "${WORK}" </dev/null >>"${LOG}" 2>&1 &
else
  OIDA_CAPTURE=1 nohup python3 "${PLUGIN_DIR}/lib/push.py" --plan "${PLAN}" --work "${WORK}" </dev/null >>"${LOG}" 2>&1 &
fi

exit 0
