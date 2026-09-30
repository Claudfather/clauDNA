#!/bin/bash
# Session store hook (R-record, spec §4.4): records session and segment
# boundaries in ${CLAUDNA_STATE_DIR:-~/.claudna}/sessions/. Wired for
# SessionStart, PreCompact and SessionEnd; the event name is $1, the hook
# payload arrives on stdin.
#
# Invariants (tests/test_session_store_hook.py):
#   - ALWAYS exits 0 and prints nothing — SessionStart stdout would land in the
#     agent's context, and a failing hook must never break the session.
#   - Silent in clauDNA's own children (CLAUDNA_SESSION_CHILD=1), and off when
#     CLAUDNA_SESSION_STORE=0.
#   - Never touches the vault or git beyond one read of the branch; never blocks.
#   - Failures are logged to <state>/hooks/errors.log (the Python side), and
#     anything Python can't log itself (an ImportError, a missing interpreter's
#     noise) is appended there by this wrapper — never swallowed silently.
#
# The store runs in the directory form, not `python3 -m`: hooks run in the
# user's project, and -m would let a project's json.py shadow the stdlib.

[ "${CLAUDNA_SESSION_CHILD:-}" = "1" ] && exit 0
[ "${CLAUDNA_SESSION_STORE:-1}" = "0" ] && exit 0
command -v python3 > /dev/null 2>&1 || exit 0

# shellcheck source=lib/state-dir.sh
. "${BASH_SOURCE[0]%/*}/lib/state-dir.sh"
STATE_DIR="$(claudna_state_dir)"
[ -n "$STATE_DIR" ] || exit 0
umask 077
mkdir -p -m 700 "$STATE_DIR/hooks" 2> /dev/null || exit 0

PKG="${BASH_SOURCE[0]%/*}/../lib/claudna/session_store"
python3 "$PKG" hook "${1:-}" > /dev/null 2>> "$STATE_DIR/hooks/errors.log"
exit 0
