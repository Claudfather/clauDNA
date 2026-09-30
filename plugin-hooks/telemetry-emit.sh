#!/bin/bash
# Skill telemetry for Claudosseum (PostToolUse, matcher Skill; async).
#
# With CLAUDNA_TELEMETRY=1 (Claudlobby sets it for fleet bots), each claudna:*
# Skill call appends one line to
# ${CLAUDNA_TELEMETRY_PATH:-~/.claude/telemetry/skill-events.jsonl}:
#   {"ts","bot","type":"skill_invocation","source":"vitals",
#    "data":{"skill_slug","duration_ms","success","session_id"}}
# The writer is the session store's telemetry.py (it decodes the Skill payload
# once, with the same code that records skill.invoked); this script only gates
# on the opt-in, so telemetry costs nothing when off and works with the session
# store off. Always exits 0 and prints nothing. A failure (an ImportError
# included) lands in <telemetry file>.stderr, capped at 1 MiB like the store's
# own capture: failing open, never silently (lib/CLAUDE.md).
#
# Env vars:
#   CLAUDNA_TELEMETRY       — "1" to enable, anything else disables
#   CLAUDNA_TELEMETRY_PATH  — output file
#   BOT_NAME                — bot identity (default: "interactive")

[ "${CLAUDNA_TELEMETRY:-0}" = "1" ] || exit 0
command -v python3 > /dev/null 2>&1 || exit 0
umask 077
OUT="${CLAUDNA_TELEMETRY_PATH:-${HOME:+$HOME/.claude/telemetry/skill-events.jsonl}}"
ERR=/dev/null
if [ -n "$OUT" ] && { [ -d "$(dirname "$OUT")" ] || mkdir -p -m 700 "$(dirname "$OUT")" 2> /dev/null; }; then
  ERR="$OUT.stderr"
  if [ -f "$ERR" ] && [ "$(wc -c < "$ERR" 2> /dev/null || echo 0)" -gt 1048576 ]; then
    mv -f "$ERR" "$ERR.old" 2> /dev/null || :
  fi
  { : >> "$ERR"; } 2> /dev/null || ERR=/dev/null  # an unwritable capture must not stop the writer
fi
PKG="${BASH_SOURCE[0]%/*}/../lib/claudna/session_store"
python3 -S "$PKG" telemetry > /dev/null 2>> "$ERR"
exit 0
