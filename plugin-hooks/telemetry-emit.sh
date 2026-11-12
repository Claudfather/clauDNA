#!/bin/bash
# Skill telemetry for Claudosseum (PostToolUse, matcher Skill; async).
#
# On by default, each claudna:*
# Skill call appends one line to
# <effective clauDNA root>/telemetry/skill-events.jsonl:
#   {"ts","bot","type":"skill_invocation","source":"vitals",
#    "data":{"skill_slug","duration_ms","success","session_id"}}
# The writer is the session store's telemetry.py (it decodes the Skill payload
# once, with the same code that records skill.invoked); this script only gates
# on opt-outs, so telemetry costs nothing when off. Explicit CLAUDNA_TELEMETRY=1
# also works with the session store off. Always exits 0 and prints nothing. A failure (an ImportError
# included) produces a fixed bounded diagnostic, never arbitrary stderr.
# File-level codes live beside the accepted feed; bootstrap codes live under R/hooks/.
#
# Env vars:
#   CLAUDNA_TELEMETRY       — "0" to disable; defaults on
#   CLAUDNA_TELEMETRY_PATH  — output file
#   BOT_NAME                — bot identity (default: "interactive")

[ "${CLAUDNA_TELEMETRY:-1}" != "0" ] || exit 0
[ "${CLAUDNA_SESSION_CHILD:-0}" != "1" ] || exit 0
[ "${CLAUDNA_SKILL_LOG:-1}" != "0" ] || exit 0
if [ "${CLAUDNA_SESSION_STORE:-1}" = "0" ] && [ "${CLAUDNA_TELEMETRY:-}" != "1" ]; then exit 0; fi
command -v python3 > /dev/null 2>&1 || exit 0
umask 077
. "${BASH_SOURCE[0]%/*}/lib/state-dir.sh"
PKG="${BASH_SOURCE[0]%/*}/../lib/claudna/session_store"
# This read-only resolver is shared with the writer and report default. Never
# redirect an invalid configured consumer or create its outside-root directory.
if ! python3 -B -S "$PKG" telemetry-path >/dev/null 2>/dev/null; then
  claudna_bootstrap_error telemetry_configuration
  exit 0
fi
if ! python3 -B -S "$PKG" telemetry >/dev/null 2>/dev/null; then
  claudna_bootstrap_error telemetry_runtime
fi
exit 0
