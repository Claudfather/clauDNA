#!/bin/bash
# Session store hook (R-record, spec §4.4): records session and segment
# boundaries, and in-segment activity, in ${CLAUDNA_STATE_DIR:-~/.claudna}/sessions/.
# Wired for SessionStart, PreCompact and SessionEnd (synchronous), and
# UserPromptSubmit, PostToolUse (Skill) and PostToolUseFailure (async, so no
# prompt waits on it). The event name is $1; the hook payload arrives on stdin.
#
# Invariants (tests/test_session_store_hook.py):
#   - ALWAYS exits 0 and prints nothing — SessionStart stdout would land in the
#     agent's context, and a failing hook must never break the session.
#   - Silent in clauDNA's own children (CLAUDNA_SESSION_CHILD=1), and off when
#     CLAUDNA_SESSION_STORE=0.
#   - Never touches the vault or git beyond one read of the branch; never blocks.
#   - Attributable diagnostics stay in sessions/<sid>/hooks/. Without native
#     identity/import availability, only fixed bootstrap codes are retained.
# Directory invocation prevents project modules from shadowing the stdlib.

[ "${CLAUDNA_SESSION_CHILD:-}" = "1" ] && exit 0
[ "${CLAUDNA_SESSION_STORE:-1}" = "0" ] && exit 0
. "${BASH_SOURCE[0]%/*}/lib/state-dir.sh"
STATE_DIR="$(claudna_state_dir)"
[ -n "$STATE_DIR" ] || exit 0
command -v python3 >/dev/null 2>&1 || { claudna_bootstrap_error session_store_runtime; exit 0; }
umask 077
EVENT=$(cat)
SID=""
if command -v jq >/dev/null 2>&1; then
  SID=$(printf '%s' "$EVENT" | claudna_event_session_id 2>/dev/null) || SID=""
fi
OWNER="$(claudna_session_dir "$SID")"
ERR=/dev/null
if [ -n "$OWNER" ] && { [ -d "$OWNER/hooks" ] || mkdir -p -m 700 "$OWNER/hooks" 2>/dev/null; }; then
  ERR="$OWNER/hooks/session-store.stderr"
  if [ -f "$ERR" ] && [ "$(wc -c < "$ERR" 2>/dev/null || echo 0)" -gt 1048576 ]; then
    mv -f "$ERR" "$ERR.old" 2>/dev/null || :
  fi
  { : >> "$ERR"; } 2>/dev/null || ERR=/dev/null
fi
PKG="${BASH_SOURCE[0]%/*}/../lib/claudna/session_store"
if ! printf '%s' "$EVENT" | python3 -B -S "$PKG" hook "$@" >/dev/null 2>> "$ERR"; then
  claudna_bootstrap_error session_store_runtime
fi
exit 0
