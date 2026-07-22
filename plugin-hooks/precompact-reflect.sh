#!/bin/bash
# PreCompact hook: auto-invoke /claudna:capture before context compaction.
#
# On first compaction attempt per session, blocks compaction and instructs
# Claude to run /claudna:capture first (a bare capture distills the session).
# On the second attempt (after capture has run), allows compaction to proceed.
#
# Filename, the CLAUDNA_PRECOMPACT_REFLECT opt-out, and the marker keep their
# historical names for now; the hook restructure (SessionEnd + stacking) is #203.
#
# Env vars:
#   CLAUDNA_PRECOMPACT_REFLECT  — "0" to disable (default: enabled)
#   CLAUDE_SESSION_ID           — session identifier (set by Claude Code)

set -euo pipefail

# Opt-out check: disabled when explicitly set to "0"
if [ "${CLAUDNA_PRECOMPACT_REFLECT:-1}" = "0" ]; then
    exit 0
fi

# Read hook input from stdin
EVENT=$(cat)

# Extract session ID for the marker file
SESSION_ID=""
if command -v jq &>/dev/null; then
    SESSION_ID=$(printf '%s' "$EVENT" | jq -r '.session_id // empty' 2>/dev/null || true)
fi
SESSION_ID="${SESSION_ID:-${CLAUDE_SESSION_ID:-}}"

# Validate before the id becomes part of a filesystem path below. A value
# bearing '/' (or other path metacharacters) could point the marker outside
# the marker dir. Claude Code generates a UUID here, so a value outside this
# charset is malformed — treat it like a missing id and fail-open.
case "$SESSION_ID" in
    *[!A-Za-z0-9._-]*) SESSION_ID="" ;;
esac

# No stable session ID available — fail-open to avoid infinite block loop
# ($$ changes per subprocess invocation, so marker files would never match)
if [ -z "$SESSION_ID" ]; then
    exit 0
fi

MARKER_DIR="${TMPDIR:-/tmp}"
MARKER="${MARKER_DIR}/claudna-reflected-${SESSION_ID}"

if [ -f "$MARKER" ]; then
    # Capture already ran this session — allow compaction
    rm -f "$MARKER"
    exit 0
fi

# First compaction attempt — block and request capture
touch "$MARKER"
printf '{"decision":"block","reason":"Run /claudna:capture to distill session learnings before compacting. Then run /compact again."}\n'
