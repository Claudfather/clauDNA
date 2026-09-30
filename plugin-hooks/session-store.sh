#!/bin/bash
# Session store hook (R-record, spec §4.4): records session and segment
# boundaries, and in-segment activity, in ${CLAUDNA_STATE_DIR:-~/.claudna}/sessions/.
# Wired for SessionStart, PreCompact and SessionEnd (synchronous), and
# UserPromptSubmit, PostToolUse (Skill) and PostToolUseFailure (async, so no
# prompt waits on it). The event name is $1; the hook payload arrives on stdin.
# PostToolUse also writes skill telemetry for Claudosseum when
# CLAUDNA_TELEMETRY=1 (the store's telemetry.py; it replaced telemetry-emit.sh),
# even with the store itself off.
#
# Invariants (tests/test_session_store_hook.py):
#   - ALWAYS exits 0 and prints nothing — SessionStart stdout would land in the
#     agent's context, and a failing hook must never break the session.
#   - Silent in clauDNA's own children (CLAUDNA_SESSION_CHILD=1), and off when
#     CLAUDNA_SESSION_STORE=0.
#   - Never touches the vault or git beyond one read of the branch; never blocks.
#   - Failures are logged to <state>/hooks/errors.log, one JSON line each (the
#     Python side). Anything Python can't log itself — an ImportError, an
#     interpreter that won't start — lands in <state>/hooks/session-store.stderr,
#     never swallowed silently.
#
# The store runs in the directory form, not `python3 -m`: hooks run in the
# user's project, and -m would let a project's json.py shadow the stdlib.

[ "${CLAUDNA_SESSION_CHILD:-}" = "1" ] && exit 0
TELEMETRY=0
[ "${1:-}" = "PostToolUse" ] && [ "${CLAUDNA_TELEMETRY:-0}" = "1" ] && TELEMETRY=1
[ "${CLAUDNA_SESSION_STORE:-1}" = "0" ] && [ "$TELEMETRY" = "0" ] && exit 0
command -v python3 > /dev/null 2>&1 || exit 0

# shellcheck source=lib/state-dir.sh
. "${BASH_SOURCE[0]%/*}/lib/state-dir.sh"
STATE_DIR="$(claudna_state_dir)"
umask 077
if [ -n "$STATE_DIR" ] && { [ -d "$STATE_DIR/hooks" ] || mkdir -p -m 700 "$STATE_DIR/hooks" 2> /dev/null; }; then
  ERR="$STATE_DIR/hooks/session-store.stderr"
elif [ "$TELEMETRY" = "1" ]; then
  ERR=/dev/null  # no safe state root: telemetry still runs, the store records nothing
else
  exit 0
fi

# Rotate the stderr capture here, not in Python: the case it exists for (the
# store failing to import) is exactly when Python can't rotate it. Same 1 MiB
# limit as fsio.LOG_LIMIT.
if [ -f "$ERR" ] && [ "$(wc -c < "$ERR" 2> /dev/null || echo 0)" -gt 1048576 ]; then
  mv -f "$ERR" "$ERR.old" 2> /dev/null || :
fi

# -S: the store is stdlib-only, so skip site-packages setup (a few ms per call).
PKG="${BASH_SOURCE[0]%/*}/../lib/claudna/session_store"
python3 -S "$PKG" hook "${1:-}" > /dev/null 2>> "$ERR"
exit 0
